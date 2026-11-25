# Driver for the Waveshare 2.9" e-paper V2 panel (SSD1680-class controller)
# as fitted to the Pico-CapTouch-ePaper-2.9.
#
# Drawing happens on a landscape 296x128 framebuffer where colour 1 = black
# and 0 = white. show() rotates the buffer into the panel's native portrait
# RAM layout, does a full or partial refresh and puts the panel into deep
# sleep. A busy timeout raises OSError (e.g. loose FPC cable).
from machine import Pin, SPI
import framebuf
import time

WIDTH = 296
HEIGHT = 128
_LINE_BYTES = HEIGHT // 8  # bytes per panel gate line (128 px)

# Partial-refresh waveform from Waveshare's Pico_ePaper-2.9.py (MIT licence):
# 153 bytes LUT, then 0x3F, gate voltage, VSH, VSH2, VSL, VCOM.
_LUT_PARTIAL = bytes((
    0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x80, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x40, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x00, 0x00, 0x00,
    0x22, 0x17, 0x41, 0xB0, 0x32, 0x36,
))


class EPD:
    def __init__(self, rst=12, dc=8, cs=9, busy=13, sck=10, mosi=11, flip=False):
        # SPI first: on rp2 SPI1 claims GP8 as its default MISO, which is the
        # DC pin here. Creating the Pin objects afterwards re-muxes it to GPIO.
        self.spi = SPI(1, baudrate=4_000_000, polarity=0, phase=0,
                       sck=Pin(sck), mosi=Pin(mosi))
        self.rst = Pin(rst, Pin.OUT, value=1)
        self.dc = Pin(dc, Pin.OUT, value=0)
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.busy = Pin(busy, Pin.IN, Pin.PULL_UP)

        self.buf = bytearray(WIDTH * HEIGHT // 8)
        self.fb = framebuf.FrameBuffer(self.buf, WIDTH, HEIGHT, framebuf.MONO_VLSB)
        self._out = bytearray(len(self.buf))
        self._prev = None  # last frame on the panel (panel byte order)
        self.flip = flip

        # Per-byte translation: invert (panel RAM uses 1 = white) and, for the
        # 180° rotated orientation, reverse the bit order as well.
        lut = bytearray(256)
        for i in range(256):
            v = i
            if flip:
                r = 0
                for _ in range(8):
                    r = (r << 1) | (v & 1)
                    v >>= 1
                v = r
            lut[i] = ~v & 0xFF
        self._lut = lut

    # --- low level -------------------------------------------------------
    def _cmd(self, c, data=None):
        self.dc(0)
        self.cs(0)
        self.spi.write(bytes((c,)))
        self.cs(1)
        if data is not None:
            self.dc(1)
            self.cs(0)
            self.spi.write(data)
            self.cs(1)

    def _wait(self, timeout_ms=10_000):
        t0 = time.ticks_ms()
        while self.busy.value():  # high = busy
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                raise OSError("epd: busy timeout")
            time.sleep_ms(10)

    def _reset(self):
        self.rst(1)
        time.sleep_ms(50)
        self.rst(0)
        time.sleep_ms(2)
        self.rst(1)
        time.sleep_ms(50)

    def _cursor(self):
        self._cmd(0x4E, b"\x00")
        self._cmd(0x4F, b"\x00\x00")

    def init(self):
        self._reset()
        self._wait()
        self._cmd(0x12)  # software reset
        self._wait()
        self._config()

    def _config(self):
        self._cmd(0x01, b"\x27\x01\x00")  # 296 gate lines
        self._cmd(0x11, b"\x03")  # data entry: X+, Y+
        self._cmd(0x44, bytes((0, _LINE_BYTES - 1)))
        self._cmd(0x45, bytes((0, 0, (WIDTH - 1) & 0xFF, (WIDTH - 1) >> 8)))
        self._cmd(0x3C, b"\x05")  # border waveform
        self._cmd(0x21, b"\x00\x80")  # display update control
        self._cmd(0x18, b"\x80")  # use internal temperature sensor
        self._cursor()
        self._wait()

    def sleep(self):
        self._cmd(0x10, b"\x01")  # deep sleep mode 1 (RAM retained)

    # --- frame handling --------------------------------------------------
    def _prepare(self):
        # Landscape MONO_VLSB byte (page j, column x) holds 8 vertical pixels.
        # The panel is portrait: gate line = landscape x (WIDTH-1-x if
        # flipped), 16 source bytes per line, MSB first. Unflipped, source
        # byte k covers landscape rows 127-8k..120-8k, i.e. page 15-k with the
        # bit order already matching, hence the reversed j loop. Flipped, the
        # pages run forwards and the LUT reverses the bits instead. Same
        # mapping as Waveshare's landscape driver (data entry mode 0x07).
        src, out, lut = self.buf, self._out, self._lut
        i = 0
        if self.flip:
            for x in range(WIDTH - 1, -1, -1):
                for j in range(_LINE_BYTES):
                    out[i] = lut[src[j * WIDTH + x]]
                    i += 1
        else:
            for x in range(WIDTH):
                for j in range(_LINE_BYTES - 1, -1, -1):
                    out[i] = lut[src[j * WIDTH + x]]
                    i += 1

    def show(self, partial=False):
        """Refresh the panel with the current framebuffer, then deep sleep.

        Full refresh (~2 s, flashes) uses the panel's built-in waveform.
        Partial refresh (~0.5 s, no flash) only works on top of a frame shown
        earlier; it may leave slight ghosting, so mix in full refreshes.
        """
        self._prepare()
        try:
            if partial and self._prev is not None:
                self._show_partial()
            else:
                self.init()
                self._cmd(0x24, self._out)  # B/W RAM
                self._cursor()
                self._cmd(0x26, self._out)  # "previous" RAM, keep in sync
                # full update: clock + analog on, load temperature and OTP
                # waveform, display (mode 1), then power down
                self._cmd(0x22, b"\xF7")
                self._cmd(0x20)
                self._wait()
            self.sleep()
        except Exception:
            self._prev = None  # unknown panel content -> next refresh is full
            raise
        if self._prev is None:
            self._prev = bytearray(len(self._out))
        self._prev[:] = self._out

    def _show_partial(self):
        # Sequence follows Waveshare's display_Partial(). Instead of relying on
        # the panel's "previous" RAM surviving deep sleep, we rewrite it from
        # our copy of the last frame.
        self._reset()  # wakes the controller from deep sleep
        self._wait()
        self._config()
        lut = _LUT_PARTIAL
        self._cmd(0x32, lut[:153])
        self._wait()
        self._cmd(0x3F, lut[153:154])
        self._cmd(0x03, lut[154:155])  # gate voltage
        self._cmd(0x04, lut[155:158])  # source voltages VSH, VSH2, VSL
        self._cmd(0x2C, lut[158:159])  # VCOM
        # display option register, values from Waveshare's display_Partial()
        self._cmd(0x37, b"\x00\x00\x00\x00\x00\x40\x00\x00\x00\x00")
        self._cmd(0x3C, b"\x80")  # border waveform
        self._cmd(0x22, b"\xC0")  # enable clock + analog
        self._cmd(0x20)
        self._wait()
        self._cursor()
        self._cmd(0x26, self._prev)
        self._cursor()
        self._cmd(0x24, self._out)
        self._cmd(0x22, b"\x0F")  # display with the loaded (partial) LUT
        self._cmd(0x20)
        self._wait()
