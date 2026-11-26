# Weather + home sensor display for Pico W + Waveshare Pico-CapTouch-ePaper-2.9
import gc
import sys
import time

import machine


def _fatal(e, delay_s=30):
    """Log the error (console + crash.txt), wait, reboot."""
    sys.print_exception(e)
    try:
        with open("crash.txt", "w") as f:
            sys.print_exception(e, f)
    except Exception as e2:
        print("cannot write crash.txt", repr(e2))
    print("restarting in %d s (Ctrl-C to stop)" % delay_s)
    time.sleep(delay_s)
    machine.reset()


try:
    import demo
    import timeutil as tu
    import ui
    from epd import EPD
    from sensors import SensorHub
    from timeutil import since
    from touch import Touch
except Exception as e:  # broken or missing app file: reboot instead of idling at the REPL
    _fatal(e)

CONFIG_ERROR = None
try:
    import config
except ImportError as e:
    config = None
    if "'config'" in str(e):
        print("config: no config.py")
    else:  # config.py itself imports something missing
        CONFIG_ERROR = repr(e)
except Exception as e:  # syntax error etc. in config.py
    config = None
    CONFIG_ERROR = repr(e)


def C(name, default=None):
    """Config value; `default` if config.py or the name is missing or the
    value is None. Falsy values such as 0 or False are kept."""
    v = getattr(config, name, None) if config else None
    return default if v is None else v


WIND_LABEL = {"kmh": "km/h", "ms": "m/s", "mph": "mph", "kn": "kn"}


class Watchdog:
    """Software watchdog: reboots the board if the main loop stops running.

    The RP2040 hardware watchdog allows at most ~8.3 s, less than legitimate
    blocking calls here (WiFi connect, HTTPS, display refresh), so a hard
    timer interrupt checks a heartbeat instead. Hard IRQs run even while the
    main code is stuck inside a blocking C call.
    """

    def __init__(self, timeout_s):
        self.timeout = timeout_s * 1000
        self.beat = time.ticks_ms()
        self.timer = None
        if not timeout_s:
            return
        try:
            self.timer = machine.Timer(period=10_000, callback=self._check, hard=True)
        except TypeError:
            self.timer = machine.Timer(period=10_000, callback=self._check)
        except Exception as e:
            print("watchdog: unavailable", repr(e))

    def feed(self):
        self.beat = time.ticks_ms()

    def _check(self, _t):  # IRQ context: no allocation
        if time.ticks_diff(time.ticks_ms(), self.beat) > self.timeout:
            machine.reset()

    def stop(self):
        if self.timer:
            self.timer.deinit()


class App:
    def __init__(self, wd):
        self.wd = wd
        self.epd = EPD(flip=C("FLIP_DISPLAY", True))
        self.touch = Touch()
        self.has_weather = C("LATITUDE") is not None and C("LONGITUDE") is not None
        reason = self._demo_reason()
        self.demo = reason is not None
        self.page = 0
        self.page_since = None
        self.weather = None
        self.weather_ok_at = None  # ticks_ms of the last successful fetch
        self.weather_error = False
        self.wifi_hint = None  # short WiFi problem text, None = fine
        self.wifi_fails = 0
        self.mem_errors = 0
        self.draw_fails = 0
        self.dirty = True
        self.last_draw = None
        self.partials = 0  # partial refreshes since the last full one
        self.timers = {}
        self._last_err = None
        if self.demo:
            self.hub = SensorHub(demo.SENSORS)
            self.demo_step = 0
        else:
            mqtt = {"host": C("MQTT_HOST"), "port": C("MQTT_PORT", 1883),
                    "user": C("MQTT_USER"), "password": C("MQTT_PASSWORD")}
            self.hub = SensorHub(C("SENSORS", []), C("HA_URL"), C("HA_TOKEN"), mqtt)
        print("mode:", "demo (%s)" % reason if self.demo else "config error" if CONFIG_ERROR else "live")

    def _demo_reason(self):
        """Why demo mode is used, or None for live mode."""
        if CONFIG_ERROR:
            return None
        if config is None:
            return "no config.py"
        if C("DEMO_MODE", False):
            return "DEMO_MODE = True"
        if not C("WIFI_SSID"):
            return "WIFI_SSID is empty"
        if not self.has_weather and not C("SENSORS"):
            return "no LATITUDE/LONGITUDE and no SENSORS"
        return None

    # --- scheduling helpers ---------------------------------------------
    def due(self, key, interval_s):
        """True (and restart the timer) if `key` is unset or interval_s has passed."""
        if since(self.timers.get(key)) >= interval_s * 1000:
            self.timers[key] = time.ticks_ms()
            return True
        return False

    def retry_in(self, key, interval_s, retry_s):
        """Make `key` due again after retry_s instead of the full interval."""
        self.timers[key] = time.ticks_add(time.ticks_ms(), -(interval_s - retry_s) * 1000)

    # --- data -------------------------------------------------------------
    def update(self):
        try:
            if self.demo:
                self._update_demo()
            else:
                self._update_live()
            self.mem_errors = 0
        except MemoryError:
            # heap fragmentation (e.g. after TLS) - a reboot is the only cure
            self.mem_errors += 1
            gc.collect()
            print("memory error %d, free %d" % (self.mem_errors, gc.mem_free()))
            if self.mem_errors >= 3:
                raise
        if self.hub.changed:
            self.hub.changed = False
            self.dirty = True
        err = self.error_state()
        if err != self._last_err:  # show/clear "!" and hints right away
            self._last_err = err
            self.dirty = True

    def error_state(self):
        if self.demo:
            return ()
        return (self.wifi_hint, self.weather_error, self.hub.ha_error, self.hub.mqtt_error,
                not tu.clock_valid())

    def _update_demo(self):
        if self.due("demo", C("DEMO_INTERVAL", 300)):
            self.weather = demo.weather(self.demo_step, tu.now())
            demo.tick(self.hub.sensors)
            self.demo_step += 1
            self.dirty = True

    def _update_live(self):
        import net
        if not net.connected():
            if self.hub.client:
                self.hub.mqtt_lost()
            # connecting blocks (touch is ignored meanwhile), so back off: 30 s .. 5 min
            if not self.due("wifi", min(300, 30 << min(self.wifi_fails, 4))):
                return
            self.wifi_hint = net.connect(C("WIFI_SSID"), C("WIFI_PASSWORD", ""), C("WIFI_COUNTRY"))
            if self.wifi_hint:
                self.wifi_fails += 1
                if self.wifi_fails % 3 == 0:
                    net.reset_radio()
                if self.wifi_fails >= 10:  # ~40 min without WiFi
                    raise RuntimeError("no WiFi after %d attempts" % self.wifi_fails)
                return
            self.wifi_fails = 0
            for k in ("weather", "ha", "mqtt", "wifi"):  # refresh everything after (re)connect
                self.timers.pop(k, None)

        if self.due("ntp", 6 * 3600) and not net.sync_time(C("NTP_HOST")) and not tu.clock_valid():
            self.retry_in("ntp", 6 * 3600, 60)

        interval = C("WEATHER_INTERVAL", 900)
        if self.has_weather and self.due("weather", interval):
            try:
                import weather
                self.weather = weather.fetch(net.get_json, C("LATITUDE"), C("LONGITUDE"),
                                             C("TEMP_UNIT", "celsius"), C("WIND_UNIT", "kmh"),
                                             int(C("UTC_OFFSET", 0) * 3600))
                self.weather_error = False
                self.weather_ok_at = time.ticks_ms()
                self.dirty = True
            except MemoryError:
                raise
            except Exception as e:
                print("weather:", repr(e))
                self.weather_error = True
                self.retry_in("weather", interval, 60)
            gc.collect()
        if self.weather and since(self.weather_ok_at) > 3 * interval * 1000:
            print("weather: data too old, hiding it")
            self.weather = None
            self.dirty = True

        sensor_interval = C("SENSOR_INTERVAL", 120)
        if self.hub.ha and self.due("ha", sensor_interval):
            self.hub.poll_ha(net.get_json)
            gc.collect()

        if self.hub.mq:
            if not self.hub.client and self.due("mqtt", 30):
                self.hub.mqtt_connect()
            self.hub.mqtt_poll()

        self.hub.expire(3 * sensor_interval)

    # --- drawing ----------------------------------------------------------
    def state(self):
        if self.weather:
            offset = self.weather["offset"]
        else:
            offset = int(C("UTC_OFFSET", 0) * 3600)
        hint = None
        if not self.demo:
            if self.wifi_hint:
                hint = self.wifi_hint
            elif not self.has_weather:
                hint = "set LATITUDE"
            elif self.weather_error:
                hint = "fetch failed"
        return {
            "page": self.page, "weather": self.weather, "sensors": self.hub.sensors,
            "location": C("LOCATION_NAME", "Demo City" if self.demo else ""),
            "demo": self.demo, "now": tu.now(), "offset": offset,
            "error": any(self.error_state()) or self.hub.error,
            "wind_unit": WIND_LABEL.get(C("WIND_UNIT", "kmh"), ""),
            "weather_hint": hint,
        }

    def draw(self, partial=False):
        """Render the current page and refresh the panel.

        partial=True (page flips) asks for a partial refresh. It becomes a
        full one when PARTIAL_REFRESH is False or this would be the
        FULL_REFRESH_EVERY-th partial in a row (<= 1: always full). Data
        updates use partial=False.
        """
        every = C("FULL_REFRESH_EVERY", 5)
        if not C("PARTIAL_REFRESH", True) or (partial and self.partials >= every - 1):
            partial = False
        t0 = time.ticks_ms()
        try:
            try:
                ui.render(self.epd.fb, self.state())
            except Exception as e:  # bug or unexpected data: show it instead of reboot-looping
                sys.print_exception(e)
                ui.message(self.epd.fb, "Display error", [repr(e), "Retrying with the next update."])
            self.epd.show(partial)
            self.draw_fails = 0
            self.partials = self.partials + 1 if partial else 0
        except OSError as e:  # display hardware problem (busy timeout)
            self.draw_fails += 1
            print("display:", repr(e))
            if self.draw_fails >= 3:
                raise
        self.touch.clear()
        self.last_draw = time.ticks_ms()
        self.dirty = False
        print("display: %s refresh, page %d, %d ms" % ("partial" if partial else "full", self.page,
                                                        time.ticks_diff(self.last_draw, t0)))
        gc.collect()

    def show_message(self, title, lines):
        ui.message(self.epd.fb, title, lines)
        self.epd.show()

    def run(self):
        if CONFIG_ERROR:
            print("config.py error:", CONFIG_ERROR)
            self.show_message("config.py error", [CONFIG_ERROR, "", "Fix config.py and reset the board."])
            while True:
                self.wd.feed()
                time.sleep(1)

        self.update()
        if self.hub.mq and self.hub.client:  # collect retained MQTT values first
            t0 = time.ticks_ms()
            while since(t0) < 3000:
                self.hub.mqtt_poll()
                time.sleep_ms(50)
            self.hub.changed = False
        self.draw()

        page_timeout = C("PAGE_TIMEOUT", 120) * 1000
        min_redraw = C("MIN_REDRAW_INTERVAL", 60) * 1000
        while True:
            self.wd.feed()
            self.update()
            if self.touch.tapped():
                self.page = (self.page + 1) % ui.PAGES
                self.page_since = time.ticks_ms()
                self.draw(partial=True)
            elif self.page and page_timeout and since(self.page_since) > page_timeout:
                self.page = 0
                self.draw(partial=True)
            elif self.dirty and since(self.last_draw) >= min_redraw:
                self.draw()
            time.sleep_ms(50)


def _show_last_crash():
    import os
    try:
        with open("crash.txt") as f:
            print("--- previous crash ---\n" + f.read() + "----------------------")
        os.rename("crash.txt", "crash_prev.txt")
    except OSError:
        pass


def main():
    _show_last_crash()
    wd = Watchdog(C("WATCHDOG_TIMEOUT", 300))
    app = None
    try:
        app = App(wd)
        app.run()
    except KeyboardInterrupt:
        wd.stop()  # don't reboot underneath an interactive session
        raise
    except Exception as e:
        if app:
            try:
                app.show_message("Error - restarting", [repr(e), "", "Details: crash.txt"])
            except Exception as e2:
                print("crash screen failed", repr(e2))
        _fatal(e)


main()
