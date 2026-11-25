# User-defined sensor values from Home Assistant (REST) or MQTT.
import json
import time

from timeutil import since


class Sensor:
    def __init__(self, spec):
        self.entity = spec.get("entity")
        self.attribute = spec.get("attribute")
        self.topic = spec.get("topic")
        self.key = spec.get("key")
        self.source = spec.get("source") or ("mqtt" if self.topic else "ha")
        self.name = spec.get("name") or self.entity or self.topic or "Sensor"
        self.unit = spec.get("unit")
        self.max_age = spec.get("max_age")  # seconds, MQTT only; None = never expire
        self.err = None  # short problem description shown on screen
        try:
            self.decimals = int(spec.get("decimals", 1))
        except (TypeError, ValueError):
            print("config: sensor %r: decimals must be a number" % self.name)
            self.decimals = 1
        self.auto_unit = None
        self.text = None  # formatted value, None = no data
        self.updated = None  # ticks_ms of the last value
        self._warned = False

    def display_unit(self):
        return self.unit if self.unit is not None else (self.auto_unit or "")

    def _fmt(self, v):
        if v is None:
            return None
        if isinstance(v, bool):
            return "on" if v else "off"
        try:
            f = float(v)
        except (TypeError, ValueError):
            s = str(v).strip()
            return None if s in ("", "unavailable", "unknown") else s
        return ("{:.%df}" % self.decimals).format(f)

    def set(self, raw):
        """Store a new raw value. Returns True if the displayed text changed."""
        txt = self._fmt(raw)
        changed = txt != self.text
        self.text = txt
        self.updated = time.ticks_ms()
        return changed

    def clear(self, err=None):
        """Drop the value (shown as "--"). Returns True if the display changes."""
        changed = self.text is not None or self.err != err
        self.text = None
        self.err = err
        return changed

    def _warn_once(self, msg):
        if not self._warned:
            self._warned = True
            print("mqtt: %s (sensor %r, topic %s)" % (msg, self.name, self.topic))

    def set_payload(self, payload):
        try:
            s = payload.decode()
        except Exception:
            self._warn_once("payload is not UTF-8")
            return False
        if not self.key:
            return self.set(s)
        try:
            v = json.loads(s)
            for k in self.key.split("."):
                v = v[int(k)] if isinstance(v, list) else v[k]
        except ValueError:
            self._warn_once("payload is not JSON but a key is configured")
            return False
        except (KeyError, IndexError, TypeError):
            # partial updates may legitimately lack the key; a typo shows up here too
            self._warn_once("key %r not in payload" % self.key)
            return False
        self.err = None
        return self.set(v)


class SensorHub:
    def __init__(self, specs, ha_url=None, ha_token=None, mqtt=None):
        self.sensors = [Sensor(s) for s in (specs or [])[:3]]
        self.ha = [s for s in self.sensors if s.source == "ha"]
        self.mq = [s for s in self.sensors if s.source == "mqtt"]
        self.ha_url = (ha_url or "").rstrip("/")
        self.ha_token = ha_token or ""
        self.mqtt_cfg = mqtt or {}
        self.client = None
        self.changed = False
        self.ha_error = False
        self.mqtt_error = False
        self.mqtt_down_since = None  # ticks_ms when the MQTT connection was lost
        self._by_topic = {}
        self._validate()
        for s in self.mq:
            self._by_topic.setdefault(s.topic, []).append(s)

    def _validate(self):
        def disable(group, err):
            for s in group:
                s.err = err
                print("config: sensor %r disabled: %s" % (s.name, err))
            group.clear()

        if self.ha and not self.ha_url:
            disable(self.ha, "no HA_URL")
        elif self.ha and not self.ha_token:
            disable(self.ha, "no HA_TOKEN")
        if self.mq and not self.mqtt_cfg.get("host"):
            disable(self.mq, "no MQTT_HOST")
        for s in self.mq:
            if "+" in s.topic or "#" in s.topic:
                print("config: sensor %r: wildcard topics are not supported" % s.name)
                s.err = "wildcard topic"
        self.config_error = any(s.err for s in self.sensors)

    @property
    def error(self):
        return self.ha_error or self.mqtt_error or self.config_error

    def poll_ha(self, get_json):
        hdr = {"Authorization": "Bearer " + self.ha_token}
        err = False
        for s in self.ha:
            try:
                j = get_json("%s/api/states/%s" % (self.ha_url, s.entity), hdr)
                attrs = j.get("attributes") or {}
                if s.attribute:
                    raw = attrs.get(s.attribute)
                else:
                    raw = j.get("state")
                    unit = attrs.get("unit_of_measurement")
                    if unit != s.auto_unit:
                        s.auto_unit = unit
                        self.changed = True
                if s.err:
                    s.err = None
                    self.changed = True
                if s.set(raw):
                    self.changed = True
            except MemoryError:
                raise  # handled (counted, eventually reboot) by the app
            except Exception as e:
                status = getattr(e, "status", None)
                if status == 401:
                    msg = "bad HA token"
                elif status == 404:
                    msg = "not in HA"
                else:
                    msg = None  # transient: keep value until it expires
                print("ha:", s.entity, repr(e))
                if msg and s.clear(msg):
                    self.changed = True
                err = True
        self.ha_error = err

    def expire(self, ha_max_age_s):
        """Blank values that are too old to trust (source failing silently)."""
        for s in self.ha:
            if since(s.updated) > ha_max_age_s * 1000 and s.clear(s.err or "offline"):
                self.changed = True
        lost = self.mqtt_down_since is not None and since(self.mqtt_down_since) > 300_000
        for s in self.mq:
            stale = s.max_age and s.updated is not None and since(s.updated) > s.max_age * 1000
            if (lost or stale) and s.clear(s.err or ("offline" if lost else "stale")):
                self.changed = True

    def _on_msg(self, topic, payload):
        for s in self._by_topic.get(topic, ()):
            if s.set_payload(payload):
                self.changed = True

    def mqtt_connect(self):
        from mqtt import MQTTClient
        import machine
        import binascii
        c = self.mqtt_cfg
        cid = "pico-eink-" + binascii.hexlify(machine.unique_id()).decode()
        try:
            self.client = MQTTClient(c["host"], c.get("port") or 1883, cid,
                                     c.get("user") or None, c.get("password") or None,
                                     callback=self._on_msg)
            self.client.connect()
            for t in self._by_topic:
                self.client.subscribe(t)
            print("mqtt: connected, %d topic(s)" % len(self._by_topic))
            self.mqtt_error = False
            self.mqtt_down_since = None
        except MemoryError:
            self.mqtt_lost()
            raise
        except Exception as e:
            print("mqtt: connect failed", repr(e))
            self.mqtt_lost()

    def mqtt_poll(self):
        if not self.client:
            return
        try:
            self.client.check()
        except Exception as e:
            print("mqtt:", repr(e))
            self.mqtt_lost()
            return
        for t in self.client.sub_refused:
            for s in self._by_topic.get(t, ()):
                if s.clear("sub refused"):
                    self.changed = True
            self.mqtt_error = True
        self.client.sub_refused = []

    def mqtt_lost(self):
        self.mqtt_close()
        self.mqtt_error = True
        if self.mqtt_down_since is None:
            self.mqtt_down_since = time.ticks_ms()

    def mqtt_close(self):
        if self.client:
            try:
                self.client.close()
            except Exception as e:
                print("mqtt: close failed", repr(e))
        self.client = None
