# Tiny MQTT 3.1.1 subscriber (QoS 0), just enough to receive sensor values.
import errno
import socket
import time

_NO_DATA = (errno.EAGAIN, errno.ETIMEDOUT)
_MAX_PACKET = 4096  # larger packets are skipped instead of risking MemoryError
_MAX_PER_CHECK = 20  # don't let a message flood starve the main loop
_CONNACK = {1: "bad protocol version", 2: "client id rejected", 3: "server unavailable",
            4: "bad user name or password", 5: "not authorised"}


def _str(s):
    b = s.encode() if isinstance(s, str) else s
    return bytes((len(b) >> 8, len(b) & 0xFF)) + b


def _since(t):
    d = time.ticks_diff(time.ticks_ms(), t)
    return d if d >= 0 else 1 << 29  # see timeutil.since()


class MQTTClient:
    def __init__(self, host, port=1883, client_id="pico-eink", user=None, password=None,
                 keepalive=60, callback=None):
        self.host, self.port = host, port
        self.client_id, self.user, self.password = client_id, user, password
        self.keepalive = keepalive
        self.cb = callback
        self.sock = None
        self.sub_refused = []  # topics the broker refused (ACL, invalid)
        self._pid = 0
        self._subs = {}  # packet id -> topic
        self._last_tx = 0
        self._last_rx = 0

    def _send(self, ptype, body=b""):
        n = len(body)
        hdr = bytearray((ptype,))
        while True:
            b = n & 0x7F
            n >>= 7
            hdr.append(b | (0x80 if n else 0))
            if not n:
                break
        self.sock.write(hdr + body)
        self._last_tx = time.ticks_ms()

    def _read(self, n):
        buf = bytearray(n)
        pos = 0
        while pos < n:
            chunk = self.sock.recv(min(512, n - pos))
            if not chunk:
                raise OSError("mqtt: connection closed")
            buf[pos:pos + len(chunk)] = chunk
            pos += len(chunk)
        return buf

    def _skip(self, n):
        while n:
            chunk = self.sock.recv(min(512, n))
            if not chunk:
                raise OSError("mqtt: connection closed")
            n -= len(chunk)

    def connect(self):
        addr = socket.getaddrinfo(self.host, self.port)[0][-1]
        self.sock = socket.socket()
        self.sock.settimeout(10)
        self.sock.connect(addr)
        flags = 0x02  # clean session
        payload = _str(self.client_id)
        if self.user:
            flags |= 0x80
            payload += _str(self.user)
            if self.password:
                flags |= 0x40
                payload += _str(self.password)
        self._send(0x10, _str("MQTT") + bytes((4, flags, self.keepalive >> 8, self.keepalive & 0xFF)) + payload)
        ack = self._read(4)
        if ack[0] != 0x20:
            raise OSError("mqtt: unexpected reply 0x%02x to CONNECT" % ack[0])
        if ack[3]:
            raise OSError("mqtt: connect refused: %s" % _CONNACK.get(ack[3], ack[3]))
        self._last_rx = time.ticks_ms()

    def subscribe(self, topic):
        self._pid = self._pid % 65535 + 1
        self._subs[self._pid] = topic
        self._send(0x82, bytes((self._pid >> 8, self._pid & 0xFF)) + _str(topic) + b"\x00")

    def check(self):
        """Handle pending packets and send keepalive pings.

        Doesn't block when nothing is waiting; once a packet has started
        arriving, reading the rest can block up to the 10 s socket timeout.
        Raises OSError if the connection is closed or silent for too long.
        """
        for _ in range(_MAX_PER_CHECK):
            self.sock.settimeout(0)
            try:
                h = self.sock.recv(1)
            except OSError as e:
                if e.args[0] not in _NO_DATA:
                    raise
                h = None
            finally:
                self.sock.settimeout(10)
            if h is None:
                break
            if not h:
                raise OSError("mqtt: connection closed")
            self._last_rx = time.ticks_ms()
            self._packet(h[0])
        # The broker answers every PINGREQ, so silence for 1.5 keepalive
        # periods means the connection is half-open (e.g. broker restarted).
        if _since(self._last_rx) > self.keepalive * 1500:
            raise OSError("mqtt: no reply from broker for %d s" % (self.keepalive * 3 // 2))
        if _since(self._last_tx) > self.keepalive * 500:
            self._send(0xC0)  # PINGREQ at half the keepalive interval

    def _packet(self, b0):
        n, shift = 0, 0
        while True:
            b = self._read(1)[0]
            n |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
        if n > _MAX_PACKET:
            print("mqtt: skipping %d byte packet (limit %d)" % (n, _MAX_PACKET))
            self._skip(n)
            return
        body = self._read(n) if n else b""
        t = b0 & 0xF0
        if t == 0x90:  # SUBACK
            topic = self._subs.pop((body[0] << 8) | body[1], "?")
            if any(rc == 0x80 for rc in body[2:]):
                print("mqtt: broker refused subscription to", topic)
                self.sub_refused.append(topic)
            return
        if t != 0x30:  # PINGRESP etc.: nothing to do
            return
        tl = (body[0] << 8) | body[1]
        pos = 2 + tl
        qos = (b0 >> 1) & 3
        if qos:
            if qos == 1:
                self._send(0x40, bytes(body[pos:pos + 2]))  # PUBACK
            pos += 2
        if self.cb:
            try:
                self.cb(bytes(body[2:2 + tl]).decode(), bytes(body[pos:]))
            except Exception as e:  # a bad message must not kill the connection
                print("mqtt: error handling message:", repr(e))

    def close(self):
        if self.sock:
            try:
                self._send(0xE0)
            except OSError as e:
                print("mqtt: disconnect failed", repr(e))
            self.sock.close()
            self.sock = None
