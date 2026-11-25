# Screen layouts for the 296x128 landscape display.
import gfx
import icons
import timeutil as tu

W, H = 296, 128
PAGES = 2
_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _t(v):
    return "--" if v is None else "%d°" % round(v)


def _pct(v):
    return "--%" if v is None else "%d%%" % v


def render(fb, st):
    """Draw a page. st keys: page, weather, sensors, location, demo, error,
    now (unix time of the data/redraw), offset (s from UTC), wind_unit, and
    optional weather_hint (2nd line under "No weather data")."""
    fb.fill(0)
    _header(fb, st)
    if st["page"] == 0:
        _page_now(fb, st)
    else:
        _page_forecast(fb, st)


def message(fb, title, lines):
    """Full-screen notice (config error, crash) with an inverted title bar."""
    fb.fill(0)
    fb.fill_rect(0, 0, W, 12, 1)
    gfx.text(fb, gfx.fit(title, W - 4), 2, 2, 1, 0)
    y = 20
    for line in lines:
        if not line:
            y += 11
        while line and y < H - 8:  # wrap long lines
            part = gfx.fit(line, W - 8)
            gfx.text(fb, part, 4, y)
            line = line[len(part):]
            y += 11


def _header(fb, st):
    fb.fill_rect(0, 0, W, 12, 1)
    # Time of this redraw = age of the data shown (the panel isn't redrawn
    # every minute, so it is labelled as an update time, not a clock).
    clock = "upd --:--"
    if tu.clock_valid(st["now"]):
        clock = "upd " + tu.hm(st["now"], st["offset"])
    if st["error"]:
        clock = "! " + clock
    if st["demo"]:
        clock = "DEMO  " + clock
    rx = W - 2 - gfx.width(clock)
    gfx.text(fb, clock, rx, 2, 1, 0)
    # page indicator dots
    for i in range(PAGES):
        x = rx - 8 - (PAGES - i) * 6
        if i == st["page"]:
            fb.fill_rect(x, 4, 4, 4, 0)
        else:
            fb.rect(x, 4, 4, 4, 0)
    title = st["location"] or "Weather"
    if st["page"] == 1:
        title += " forecast"
    gfx.text(fb, gfx.fit(title, rx - 8 - PAGES * 6 - 8), 2, 2, 1, 0)


# --- page 0: current weather + sensors -------------------------------------
def _page_now(fb, st):
    _current(fb, st)
    gfx.dotted_v(fb, 153, 16, 110)
    _sensors(fb, st["sensors"], 156, 13, W - 156, H - 13)


def _current(fb, st):
    w = st["weather"]
    if not w:
        gfx.center(fb, "No weather data", 76, 56)
        gfx.center(fb, st.get("weather_hint") or "waiting...", 76, 68)
        return
    off = st["offset"]
    label, kind = icons.describe(w["code"], w["is_day"])
    icons.draw(fb, kind, 3, 15, 48)
    gfx.text(fb, _t(w["temp"]), 56, 18, 3)
    gfx.text(fb, "feels " + _t(w["feels"]), 56, 49)

    today = w["days"][0] if w["days"] else None
    wind = "Wind --"
    if w["wind"] is not None:
        wind = "Wind %d %s" % (round(w["wind"]), st["wind_unit"])
        if w["wind_dir"] is not None:
            wind += " " + _COMPASS[int((w["wind_dir"] + 22.5) % 360 // 45)]
    rows = [
        label,
        wind,
        "Hum %s  Rain %s" % (_pct(w["rh"]), _pct(today["pop"] if today else None)),
    ]
    if today:
        rows.append("Hi %s  Lo %s" % (_t(today["hi"]), _t(today["lo"])))
    if w["sunrise"] is not None and w["sunset"] is not None:
        rows.append("Sun %s-%s" % (tu.hm(w["sunrise"], off), tu.hm(w["sunset"], off)))
    y = 67
    for r in rows:
        gfx.text(fb, gfx.fit(r, 148), 4, y)
        y += 12


def _sensors(fb, sensors, x0, y0, w, h):
    n = len(sensors)
    if not n:
        gfx.center(fb, "No sensors", x0 + w // 2, y0 + h // 2 - 10)
        gfx.center(fb, "see config.py", x0 + w // 2, y0 + h // 2 + 2)
        return
    slot = h // n
    for i, s in enumerate(sensors):
        sy = y0 + i * slot
        if i:
            gfx.dotted_h(fb, x0 + 2, sy, w - 4)
        val = s.text if s.text is not None else "--"
        # no value: show why (e.g. "bad HA token") in the unit position
        unit = s.display_unit() if s.text is not None else (s.err or "")
        uw = gfx.width(unit) + 3 if unit else 0
        for sc in ((3, 2, 1) if n == 1 else (2, 1)):
            if gfx.width(val, sc) + uw <= w - 4:
                break
        else:
            val = gfx.fit(val, w - 4 - uw, sc)
        block = 11 + 8 * sc
        by = sy + (slot - block) // 2 + 1
        gfx.text(fb, gfx.fit(s.name, w - 4), x0 + 2, by)
        vx = gfx.text(fb, val, x0 + 2, by + 11, sc)
        if unit:
            gfx.text(fb, unit, vx + 3, by + 11 + 8 * sc - 8)


# --- page 1: 4-day forecast + 24h graph -------------------------------------
def _page_forecast(fb, st):
    w = st["weather"]
    if not w:
        gfx.center(fb, "No weather data", W // 2, 60)
        return
    off = st["offset"]
    days = w["days"][:4]
    cw = W // max(1, len(days))
    for i, d in enumerate(days):
        x = i * cw
        cx = x + cw // 2
        if i:
            gfx.dotted_v(fb, x, 16, 66)
        gfx.center(fb, "Today" if i == 0 else tu.weekday(d["t"], off), cx, 16)
        icons.draw(fb, icons.describe(d["code"])[1], cx - 16, 26, 32)
        gfx.center(fb, "%s/%s" % (_t(d["hi"]), _t(d["lo"])), cx, 61)
        gfx.center(fb, _pct(d["pop"]), cx, 72)
    _graph(fb, w, off, 26, 89, W - 26 - 3, 27)


def _graph(fb, w, off, gx, gy, gw, gh):
    temps, pops = w["hourly_t"], w["hourly_pop"]
    n = len(temps)
    valid = [t for t in temps if t is not None]
    if n < 2 or len(valid) < 2:
        return
    lo, hi = min(valid), max(valid)
    span = max(hi - lo, 1)
    gfx.right(fb, _t(hi), gx - 3, gy)
    gfx.right(fb, _t(lo), gx - 3, gy + gh - 8)
    gfx.dotted_h(fb, gx, gy + gh, gw)

    def px(i):
        return gx + i * (gw - 1) // (n - 1)

    # precipitation probability as hatched bars
    for i in range(n - 1):
        bh = (pops[i] or 0) * gh // 100 if i < len(pops) else 0
        if bh:
            gfx.hatch(fb, px(i), gy + gh - bh, px(i + 1) - px(i), bh)
    # temperature line (2 px), with gaps where values are missing
    prev = None
    for i, t in enumerate(temps):
        if t is None:
            prev = None
            continue
        y = gy + gh - 1 - int((t - lo) * (gh - 2) / span)
        if prev:
            fb.line(prev[0], prev[1], px(i), y, 1)
            fb.line(prev[0], prev[1] - 1, px(i), y - 1, 1)
        prev = (px(i), y)
    # hour ticks every 6 h
    t0 = w["hourly_start"]
    for i in range(0, n, 6):
        x = px(i)
        fb.vline(x, gy + gh, 3, 1)
        gfx.center(fb, "%02d" % tu.hour(t0 + i * 3600, off), x, gy + gh + 4)
