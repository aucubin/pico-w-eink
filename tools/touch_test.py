# Touch diagnostics for the Pico-CapTouch-ePaper-2.9 (runs on the Pico):
#   mpremote run tools/touch_test.py
# Prints the I2C scan, the controller version, the INT pin level and raw
# touch reports for 30 s. It doesn't use the app's touch.py on purpose.
from machine import Pin, I2C
import time

ADDR = 0x48
i2c = I2C(1, sda=Pin(6), scl=Pin(7), freq=100_000)
rst = Pin(16, Pin.OUT, value=1)
irq_pin = Pin(17, Pin.IN, Pin.PULL_UP)

print("INT level before reset:", irq_pin.value())
rst(1); time.sleep_ms(100); rst(0); time.sleep_ms(100); rst(1); time.sleep_ms(100)
print("I2C1 scan:", [hex(a) for a in i2c.scan()], "(0x48 may be missing; the version read below is what counts)")


def read(reg, n):
    i2c.writeto(ADDR, bytes((reg >> 8, reg & 0xFF)))
    return i2c.readfrom(ADDR, n)


try:
    print("version reg 0x000a:", read(0x000A, 4))
except OSError as e:
    print("version read failed:", e)

irqs = [0]


def on_irq(_pin):
    irqs[0] += 1


irq_pin.irq(trigger=Pin.IRQ_FALLING, handler=on_irq)

print("Touch the screen now (30 s)...")
t0 = time.ticks_ms()
last_level = irq_pin.value()
while time.ticks_diff(time.ticks_ms(), t0) < 30_000:
    lvl = irq_pin.value()
    if lvl != last_level:
        print("INT ->", lvl, " irq count", irqs[0])
        last_level = lvl
    if lvl == 0:
        try:
            n = read(0x1001, 1)[0]
            if 0 < n <= 5:
                b = read(0x1002, 7 * n)
                pts = [(b[1 + 7 * i] | b[2 + 7 * i] << 8, b[3 + 7 * i] | b[4 + 7 * i] << 8) for i in range(n)]
                print("touch count", n, "points", pts)
            i2c.writeto(ADDR, b"\x10\x01\x00")
        except OSError as e:
            print("read failed:", e)
    time.sleep_ms(20)
print("done, falling-edge IRQs seen:", irqs[0])
