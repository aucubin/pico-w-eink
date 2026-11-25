# Render the UI with demo data on the desktop (MicroPython unix port).
#   micropython tools/preview.py [out_dir] [scenes]
# Writes PBM images; tools/pbm2png.py turns them into a PNG sheet.
import sys

sys.path.insert(0, "src")

import framebuf
import random
import demo
import timeutil as tu
import ui
from sensors import SensorHub

out = sys.argv[1] if len(sys.argv) > 1 else "preview"
scenes = int(sys.argv[2]) if len(sys.argv) > 2 else 8

buf = bytearray(ui.W * ui.H // 8)
fb = framebuf.FrameBuffer(buf, ui.W, ui.H, framebuf.MONO_VLSB)
hub = SensorHub(demo.SENSORS)
now = 1764081120  # fixed timestamp + seed for reproducible output
random.seed(0)


def save(path):
    with open(path, "wb") as f:
        f.write(b"P4\n%d %d\n" % (ui.W, ui.H))
        row = bytearray(ui.W // 8)
        for y in range(ui.H):
            for xb in range(ui.W // 8):
                v = 0
                for b in range(8):
                    v = (v << 1) | fb.pixel(xb * 8 + b, y)
                row[xb] = v
            f.write(row)


for step in range(scenes):
    w = demo.weather(step, now)
    demo.tick(hub.sensors)
    for page in range(ui.PAGES):
        if page and step:  # forecast page only for the first scene
            continue
        st = {"page": page, "weather": w, "sensors": hub.sensors, "location": "Demo City",
              "demo": True, "error": False, "now": now, "offset": 3600, "wind_unit": "km/h"}
        ui.render(fb, st)
        save("%s/s%d_p%d.pbm" % (out, step, page))

# edge cases: no weather + long location + unavailable value; single wide sensor; missing values
st = {"page": 0, "weather": None, "sensors": hub.sensors[:1], "location": "A very long location name",
      "demo": False, "error": True, "now": now, "offset": 0, "wind_unit": "km/h", "weather_hint": "WiFi failed"}
hub.sensors[0].set("unavailable")
ui.render(fb, st)
save("%s/edge_nodata.pbm" % out)
hub.sensors[1].name = "Pressure"
hub.sensors[1].unit = "hPa"
hub.sensors[1].decimals = 1
hub.sensors[1].set(1013.25)
st.update(sensors=hub.sensors[1:2], weather=demo.weather(4, now))
ui.render(fb, st)
save("%s/edge_one_sensor.pbm" % out)
# API returned nulls; sensor errors
w = demo.weather(0, now)
w.update(rh=None, wind_dir=None, sunrise=None)
w["days"][1]["pop"] = None
for i in range(5, 9):
    w["hourly_t"][i] = None
hub.sensors[0].clear("bad HA token")
hub.sensors[2].clear("no MQTT_HOST")
st.update(sensors=hub.sensors, weather=w, error=True, page=0)
ui.render(fb, st)
save("%s/edge_nulls_p0.pbm" % out)
st["page"] = 1
ui.render(fb, st)
save("%s/edge_nulls_p1.pbm" % out)
ui.message(fb, "Error - restarting", ["OSError('epd: busy timeout')", "", "Details: crash.txt"])
save("%s/edge_message.pbm" % out)
print("ok")
