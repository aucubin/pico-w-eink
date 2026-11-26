# Pico W e-paper weather & sensor display

MicroPython app for a **Raspberry Pi Pico W** plugged into the
**Waveshare Pico-CapTouch-ePaper-2.9** (296×128, black/white, capacitive touch).

* Current weather and a 4-day forecast from [Open-Meteo](https://open-meteo.com) (no API key)
* Up to 3 sensor values from **Home Assistant** (REST API) and/or **MQTT**
* Tap the screen to switch between pages. It returns to the main page after `PAGE_TIMEOUT`.
* **Demo mode** with sample data when nothing is configured (exact conditions at the top of `config.example.py`)

| Page 1: now + sensors | Page 2: forecast + 24 h graph |
|---|---|
| icon, temperature, wind, humidity, hi/lo, sunrise/sunset; 3 sensors on the right | 4 days (icon, hi/lo, rain %), hourly temperature line with rain probability bars |

## Install

1. Flash the MicroPython firmware for the **Pico W** (`RPI_PICO_W`, v1.22 or newer) from
   <https://micropython.org/download/RPI_PICO_W/>.
2. Copy the app (needs `pip install mpremote`):

   ```sh
   (cd src && mpremote cp *.py :)
   ```

   It now runs in demo mode. The demo clock shows `upd --:--` unless the
   board's clock has been set, because demo mode doesn't use NTP.
3. Configure it:

   ```sh
   cp config.example.py config.py   # edit WiFi, location, sensors
   mpremote cp config.py :config.py
   mpremote reset
   ```

Use `mpremote repl` to watch the log output: WiFi status, fetch errors, touch coordinates and refresh times.
After a crash, the error is in `crash.txt` on the board and is printed again at the next boot.

## Sensors

```python
SENSORS = [
    # Home Assistant entity state (unit comes from HA)
    {"name": "Living room", "entity": "sensor.living_room_temperature"},
    # HA attribute instead of state
    {"name": "Outside", "entity": "weather.home", "attribute": "temperature", "unit": "°C"},
    # MQTT with a JSON payload (zigbee2mqtt style), dots for nested keys
    {"name": "Garden", "topic": "zigbee2mqtt/garden", "key": "temperature", "unit": "°C"},
    # MQTT with a plain value payload
    {"name": "CO2", "topic": "home/office/co2", "unit": "ppm", "decimals": 0},
]
```

* HA needs `HA_URL` and a long-lived `HA_TOKEN`. It is polled every `SENSOR_INTERVAL` seconds.
* MQTT needs `MQTT_HOST` and optionally a user name and password. Values are pushed, and retained topics
  show up right after boot. Only exact topics work, not wildcards.
* A value that can't be read shows `--` and the reason, for example `bad HA token`, `not in HA`,
  `no MQTT_HOST`, `offline` or `stale`.

## Behaviour notes

* **Refreshes.** Page flips use a fast partial refresh (no flash), with the waveform taken from Waveshare's
  `Pico_ePaper-2.9.py`. The automatic return to page 1 also counts as a flip. Every
  `FULL_REFRESH_EVERY`-th flip is a full refresh (about 2 s, flashes) to clear ghosting. Data updates are
  full refreshes, unless a flip happens first and shows them. Set `PARTIAL_REFRESH = False` to always
  use full refreshes.
* **Timing.** The panel sleeps between updates. Data changes redraw the screen at most every
  `MIN_REDRAW_INTERVAL` seconds, and weather refreshes every `WEATHER_INTERVAL`. The header shows the time
  of the last redraw (`upd 14:32`), not a running clock.
* **Problems.** A `!` in the header means a WiFi, weather, Home Assistant or MQTT access failed, or the clock
  isn't set yet. It appears and disappears as soon as the state changes.
  * Failed weather fetches retry after 60 s. Weather older than 3× `WEATHER_INTERVAL` is hidden.
  * WiFi reconnects with a back-off from 30 s up to 5 min. It resets the radio every 3rd failure and reboots
    after 10.
  * NTP resyncs every 6 h.
* **Recovery.** The app reboots (after showing the error on screen) when:
  * it crashes,
  * the display stops responding 3 times,
  * it runs out of memory 3 times in a row,
  * or the main loop hangs for `WATCHDOG_TIMEOUT` seconds.
  
  A broken `config.py` shows its error on the display instead.
* **Time.** Time comes from NTP, and the timezone comes from Open-Meteo (`timezone=auto`).
* **Orientation.** The picture is rotated 180° by default (`FLIP_DISPLAY = True`), also without a `config.py`. Set `FLIP_DISPLAY = False` for the orientation of Waveshare's examples.

## Layout

```
src/              files that go onto the Pico
  main.py         app loop, scheduling, touch handling, error recovery
  epd.py          e-paper driver (SSD1680, landscape framebuffer, full + partial refresh)
  touch.py        ICNT86 touch controller
  ui.py           page layouts and message screen
  gfx.py          scaled text, degree sign, dotted lines and hatching
  icons.py        vector weather icons, WMO weather codes
  weather.py      Open-Meteo client
  sensors.py      Home Assistant + MQTT sensor values
  mqtt.py         minimal MQTT 3.1.1 subscriber
  net.py          WiFi, NTP, HTTP
  timeutil.py     Unix time, local time formatting, wrap-safe tick helper
  demo.py         sample data
tools/
  preview.py      render pages to PBM files (MicroPython unix port)
  pbm2png.py      PBM files -> PNG contact sheet (CPython)
```

Preview the layouts without hardware (`brew install micropython`), from the repo root:

```sh
mkdir -p preview && micropython tools/preview.py preview
python3 tools/pbm2png.py preview/sheet.png preview/*.pbm
```
