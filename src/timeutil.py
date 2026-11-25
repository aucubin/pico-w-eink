# Wall-clock and monotonic time helpers.
import time

# Some MicroPython ports count from 2000-01-01; normalise to Unix time.
EPOCH_DELTA = 0 if time.gmtime(0)[0] == 1970 else 946684800
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_FOREVER = 1 << 29


def since(t):
    """Milliseconds since ticks_ms() value t; None or very old -> huge.

    ticks_ms() wraps every 2**30 ms on rp2, so ticks_diff() turns negative
    for gaps over ~6.2 days. Treat that as "very long ago" instead of
    "just now", otherwise timers and debounces stall for days.
    """
    if t is None:
        return _FOREVER
    d = time.ticks_diff(time.ticks_ms(), t)
    return d if d >= 0 else _FOREVER


def now():
    return time.time() + EPOCH_DELTA


def clock_valid(t=None):
    return (t or now()) > 1_700_000_000  # RTC was set (by NTP) after Nov 2023


def local(t, offset):
    return time.gmtime(int(t + offset - EPOCH_DELTA))


def hm(t, offset):
    lt = local(t, offset)
    return "%02d:%02d" % (lt[3], lt[4])


def hour(t, offset):
    return local(t, offset)[3]


def weekday(t, offset):
    return DAYS[local(t, offset)[6]]
