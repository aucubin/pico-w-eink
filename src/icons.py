# Vector weather icons drawn with framebuf primitives, scalable to any size.
from array import array

_DIRS = ((100, 0), (71, 71), (0, 100), (-71, 71), (-100, 0), (-71, -71), (0, -100), (71, -71))
_BOLT = (5, 0, 1, 6, 4, 6, 2, 11, 9, 4, 6, 4, 8, 0)  # 10 x 11 grid

# WMO weather code -> (label, icon)
_CODES = {
    0: ("Clear", "sun"), 1: ("Mostly clear", "partly"), 2: ("Partly cloudy", "partly"),
    3: ("Overcast", "cloud"), 45: ("Fog", "fog"), 48: ("Rime fog", "fog"),
    51: ("Light drizzle", "drizzle"), 53: ("Drizzle", "drizzle"), 55: ("Dense drizzle", "drizzle"),
    56: ("Frz. drizzle", "drizzle"), 57: ("Frz. drizzle", "drizzle"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"), 80: ("Light showers", "rain"), 81: ("Showers", "rain"),
    82: ("Heavy showers", "rain"), 85: ("Snow showers", "snow"), 86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "thunder"), 96: ("T-storm, hail", "thunder"), 99: ("T-storm, hail", "thunder"),
}


_reported = set()


def describe(code, is_day=True):
    if code not in _CODES and code not in _reported:
        _reported.add(code)
        print("weather: unknown weather code", code)
    label, kind = _CODES.get(code, ("Unknown", "cloud"))
    if not is_day:
        kind = {"sun": "moon", "partly": "partly_night"}.get(kind, kind)
    return label, kind


def _s(a, r):  # symmetric rounding of a*r/100
    return (a * r + 50) // 100 if a >= 0 else -((-a * r + 50) // 100)


def sun(fb, cx, cy, r, c=1):
    fb.ellipse(cx, cy, r, r, c, True)
    if r >= 6:
        fb.ellipse(cx, cy, r - 2, r - 2, 0, True)
    r1 = r + max(2, r // 3)
    r2 = r1 + max(2, r * 2 // 3)
    for dx, dy in _DIRS:
        x1, y1 = cx + _s(dx, r1), cy + _s(dy, r1)
        x2, y2 = cx + _s(dx, r2), cy + _s(dy, r2)
        fb.line(x1, y1, x2, y2, c)
        if r >= 8:
            ox, oy = (0, 1) if dy == 0 else (1, 0)
            fb.line(x1 + ox, y1 + oy, x2 + ox, y2 + oy, c)


def moon(fb, cx, cy, r, c=1):
    fb.ellipse(cx, cy, r, r, c, True)
    fb.ellipse(cx + r * 55 // 100, cy - r * 35 // 100, r * 80 // 100, r * 80 // 100, 0, True)


def _cloud_shape(fb, x, y, w, h, d, c):
    yb = y + h - 1
    r1 = h * 35 // 100
    rm = h // 2
    r2 = h * 30 // 100
    fb.ellipse(x + r1, yb - r1, max(0, r1 - d), max(0, r1 - d), c, True)
    fb.ellipse(x + w * 55 // 100, yb - rm, max(0, rm - d), max(0, rm - d), c, True)
    fb.ellipse(x + w - 1 - r2, yb - r2, max(0, r2 - d), max(0, r2 - d), c, True)
    top = yb - min(r1, r2)
    fb.fill_rect(x + r1, top, w - r2 - r1, yb - d - top + 1, c)


def cloud(fb, x, y, w, h, c=1):
    """Outlined cloud with white interior (covers whatever is behind it)."""
    d = 2 if h >= 16 else 1
    _cloud_shape(fb, x, y, w, h, 0, c)
    _cloud_shape(fb, x, y, w, h, d, 1 - c)


def _rain(fb, x, y, w, h, c, thick):
    for i in range(3):
        px = x + w * (20 + 30 * i) // 100
        top = y + (i % 2) * h // 4
        ln = h * 3 // 4
        fb.line(px, top, px - ln // 3, top + ln, c)
        if thick:
            fb.line(px + 1, top, px + 1 - ln // 3, top + ln, c)


def _drizzle(fb, x, y, w, h, c, thick):
    d = 2 if thick else 1
    for row in range(2):
        for i in range(3):
            px = x + w * (15 + 30 * i) // 100 - row * w // 8
            py = y + row * h // 2 + (i % 2) * h // 6
            fb.fill_rect(px, py, d, d + 1, c)


def _snow(fb, x, y, w, h, c, thick):
    r = max(1, h // 5)
    for i in range(3):
        cx = x + w * (15 + 35 * i) // 100
        cy = y + r + (i % 2) * (h - 2 * r - 1)
        fb.hline(cx - r, cy, 2 * r + 1, c)
        fb.vline(cx, cy - r, 2 * r + 1, c)
        if thick:
            fb.line(cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1, c)
            fb.line(cx - r + 1, cy + r - 1, cx + r - 1, cy - r + 1, c)


def _bolt(fb, x, y, w, h, c):
    pts = array("h", [(v * w // 10) if i % 2 == 0 else (v * h // 11) for i, v in enumerate(_BOLT)])
    fb.poly(x, y, pts, c, True)


def draw(fb, kind, x, y, s, c=1):
    """Draw icon `kind` into the s x s box at (x, y)."""
    thick = s >= 32
    if kind == "sun":
        sun(fb, x + s // 2, y + s // 2, s * 22 // 100, c)
    elif kind == "moon":
        moon(fb, x + s // 2, y + s // 2, s * 34 // 100, c)
    elif kind in ("partly", "partly_night"):
        if kind == "partly":
            sun(fb, x + s * 36 // 100, y + s * 34 // 100, s * 15 // 100, c)
        else:
            moon(fb, x + s * 38 // 100, y + s * 32 // 100, s * 24 // 100, c)
        cloud(fb, x + s * 18 // 100, y + s * 42 // 100, s * 80 // 100, s * 48 // 100, c)
    elif kind == "cloud":
        cloud(fb, x + s * 4 // 100, y + s * 22 // 100, s * 92 // 100, s * 56 // 100, c)
    elif kind == "fog":
        cloud(fb, x + s * 8 // 100, y + s * 4 // 100, s * 84 // 100, s * 46 // 100, c)
        for i in range(3):
            yy = y + s * (62 + 13 * i) // 100
            xx = x + s * (10 + 8 * (i % 2)) // 100
            fb.hline(xx, yy, s * 72 // 100, c)
            if thick:
                fb.hline(xx, yy + 1, s * 72 // 100, c)
    else:
        cloud(fb, x + s * 4 // 100, y + s * 4 // 100, s * 92 // 100, s * 52 // 100, c)
        zx, zy, zw, zh = x + s * 18 // 100, y + s * 64 // 100, s * 70 // 100, s * 34 // 100
        if kind == "rain":
            _rain(fb, zx, zy, zw, zh, c, thick)
        elif kind == "drizzle":
            _drizzle(fb, zx, zy, zw, zh, c, thick)
        elif kind == "snow":
            _snow(fb, zx, zy, zw, zh, c, thick)
        elif kind == "thunder":
            _bolt(fb, x + s * 36 // 100, y + s * 48 // 100, s * 30 // 100, s * 50 // 100, c)
