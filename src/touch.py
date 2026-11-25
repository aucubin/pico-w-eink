# Minimal driver for the ICNT86 capacitive touch controller on the
# Waveshare Pico-CapTouch-ePaper-2.9.
from machine import Pin, I2C
import time

from timeutil import since

ADDR = 0x48


class Touch:
    def __init__(self, sda=6, scl=7, rst=16, irq=17):
        self._flag = False
        self._last = None
        self.ok = False
        try:
            self.i2c = I2C(1, sda=Pin(sda), scl=Pin(scl), freq=100_000)
            self.rst = Pin(rst, Pin.OUT, value=1)
            self.int = Pin(irq, Pin.IN, Pin.PULL_UP)
            self.rst(0)
            time.sleep_ms(100)
            self.rst(1)
            time.sleep_ms(100)
            self.ok = ADDR in self.i2c.scan()
            self.int.irq(trigger=Pin.IRQ_FALLING, handler=self._irq)
        except Exception as e:
            print("touch: init failed", e)
        print("touch:", "ok" if self.ok else "not found")

    def _irq(self, _pin):
        self._flag = True

    def _read(self, reg, n):
        self.i2c.writeto(ADDR, bytes((reg >> 8, reg & 0xFF)))
        return self.i2c.readfrom(ADDR, n)

    def _write(self, reg, val):
        self.i2c.writeto(ADDR, bytes((reg >> 8, reg & 0xFF, val)))

    def point(self):
        """Return raw (x, y) of the first touch point, or None."""
        if not (self.ok and self._flag):
            return None
        self._flag = False
        try:
            n = self._read(0x1001, 1)[0]
            if n == 0 or n > 5:
                self._write(0x1001, 0)
                return None
            b = self._read(0x1002, 7)
            self._write(0x1001, 0)
            return (b[1] | (b[2] << 8), b[3] | (b[4] << 8))
        except OSError as e:
            print("touch:", e)
            return None

    def tapped(self, debounce_ms=800):
        """True for a touch event, at most once per debounce_ms.

        Any touch interrupt counts, so a long press can register as several taps.
        """
        p = self.point()
        if p is None:
            return False
        if since(self._last) < debounce_ms:
            return False
        self._last = time.ticks_ms()
        print("touch: tap at", p)
        return True

    def clear(self):
        """Drop touches that happened while the display was refreshing."""
        self._flag = False
        if self.ok:
            try:
                self._write(0x1001, 0)
            except OSError as e:
                print("touch: clear failed", repr(e))
