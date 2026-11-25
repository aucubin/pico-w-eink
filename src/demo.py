# Sample data for demo mode (see the conditions at the top of config.example.py).
import math
import random

SENSORS = [
    {"name": "Living room", "source": "demo", "unit": "°C"},
    {"name": "Humidity", "source": "demo", "unit": "%", "decimals": 0},
    {"name": "Office CO2", "source": "demo", "unit": "ppm", "decimals": 0},
]
# per sensor: (start value, max step per tick, min, max)
_SENSOR_BASE = ((21.4, 0.3, 18, 25), (48, 2, 30, 70), (640, 60, 400, 1400))

# (weather code, is_day, temperature) - cycles on each demo refresh
_SCENES = ((2, 1, 14.6), (61, 1, 9.2), (0, 1, 23.8), (95, 1, 19.1),
           (71, 1, -2.4), (45, 1, 4.3), (3, 1, 11.0), (1, 0, 6.7))
_DAY_CODES = (3, 61, 0, 80, 2, 71, 95)


def _rnd(a, b):
    return a + (b - a) * random.getrandbits(16) / 65535


def weather(step, now):
    code, is_day, temp = _SCENES[step % len(_SCENES)]
    midnight = now - now % 86400
    hour0 = now - now % 3600
    days = []
    for i in range(4):
        hi = temp + 3 + (i * 7 + step) % 5 - 2
        days.append({"t": midnight + i * 86400,
                     "code": code if i == 0 else _DAY_CODES[(i + step) % len(_DAY_CODES)],
                     "hi": hi, "lo": hi - 6 - i % 3, "pop": (i * 35 + step * 15) % 100})
    ht, hp = [], []
    for i in range(24):
        h = (hour0 // 3600 + i) % 24
        ht.append(temp + 4 * math.sin((h - 9) * math.pi / 12) + _rnd(-0.4, 0.4))
        hp.append(max(0, min(100, int(60 * math.sin((i + step) * math.pi / 10)) + 20)))
    return {
        "temp": temp, "feels": temp - 1.8, "rh": 62, "code": code, "is_day": is_day,
        "wind": 14, "wind_dir": 250, "sunrise": midnight + 7 * 3600 + 42 * 60,
        "sunset": midnight + 16 * 3600 + 21 * 60, "days": days,
        "hourly_start": hour0, "hourly_t": ht, "hourly_pop": hp,
        "offset": 0,
    }


def tick(sensors):
    """Random-walk the demo sensor values."""
    for s, (base, step, lo, hi) in zip(sensors, _SENSOR_BASE):
        cur = float(s.text) if s.text is not None else base
        s.set(max(lo, min(hi, cur + _rnd(-step, step))))
