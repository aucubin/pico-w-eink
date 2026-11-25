# WiFi, NTP and HTTP JSON helpers.
import time

_wlan = None
_country_set = False


class HTTPError(OSError):
    def __init__(self, status):
        super().__init__("HTTP %d" % status)
        self.status = status


def _set_country(country):
    global _country_set
    if _country_set or not country:
        return
    _country_set = True
    try:
        import network
        network.country(country)  # MicroPython >= 1.21
        return
    except Exception as e1:
        try:
            import rp2
            rp2.country(country)  # older firmware
            return
        except Exception as e2:
            print("wifi: cannot set country", country, repr(e1), repr(e2))


def _hint(status):
    import network
    return {
        getattr(network, "STAT_WRONG_PASSWORD", -3): "WiFi: bad password",
        getattr(network, "STAT_NO_AP_FOUND", -2): "WiFi: AP not found",
        getattr(network, "STAT_CONNECT_FAIL", -1): "WiFi: connect failed",
    }.get(status, "WiFi: no connection")


def connect(ssid, password, country=None, timeout_s=15):
    """Connect to WiFi, blocking for up to timeout_s.

    Returns None on success, otherwise a short error text for the screen.
    """
    global _wlan
    import network
    _set_country(country)  # must happen before the radio is first activated
    if _wlan is None:
        _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)
    if _wlan.isconnected():
        return None
    try:
        # CYW43 power-management value with power saving disabled -> more
        # reliable sockets (same as network.WLAN.PM_NONE on newer firmware)
        _wlan.config(pm=getattr(network.WLAN, "PM_NONE", 0xA11140))
    except Exception as e:
        print("wifi: cannot disable power saving", repr(e))
    _wlan.disconnect()
    _wlan.connect(ssid, password)
    t0 = time.ticks_ms()
    while not _wlan.isconnected():
        st = _wlan.status()
        if st < 0:  # wrong password / AP not found / failed: no point waiting
            print("wifi: failed, status", st)
            return _hint(st)
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
            print("wifi: timeout, status", st)
            return "WiFi: no IP (DHCP)" if st == 2 else "WiFi: timeout"  # 2 = link up, no IP
        time.sleep_ms(200)
    print("wifi: connected,", _wlan.ifconfig()[0])
    return None


def reset_radio():
    """Power-cycle the WiFi chip; helps when the CYW43 driver gets wedged."""
    if _wlan is None:
        return
    print("wifi: resetting radio")
    try:
        _wlan.disconnect()
        _wlan.active(False)
        time.sleep_ms(1000)
        _wlan.active(True)
    except Exception as e:
        print("wifi: radio reset failed", repr(e))


def connected():
    return _wlan is not None and _wlan.isconnected()


def sync_time(host=None):
    try:
        import ntptime
        if host:
            ntptime.host = host
        ntptime.settime()
        return True
    except Exception as e:
        print("ntp: sync with", host or "default host", "failed:", repr(e))
        return False


def get_json(url, headers=None, timeout=10):
    """GET url and parse JSON. Raises HTTPError for non-200 responses.

    Needs a firmware whose `requests` supports timeout= (MicroPython >= 1.22);
    without a timeout a stalled server would freeze the app.
    """
    import requests
    r = requests.get(url, headers=headers or {}, timeout=timeout)
    try:
        if r.status_code != 200:
            raise HTTPError(r.status_code)
        return r.json()
    finally:
        r.close()
