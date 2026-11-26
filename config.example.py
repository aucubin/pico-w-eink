# Copy this file to the Pico as `config.py` and fill it in.
# Demo mode (sample values) is used when there is no config.py, DEMO_MODE is
# True, WIFI_SSID is empty, or there is nothing to show (LATITUDE/LONGITUDE
# None and SENSORS empty). The startup log says which condition applied.
# A config.py with an error shows the error on the display instead.

DEMO_MODE = False

# --- WiFi -----------------------------------------------------------------
WIFI_SSID = ""
WIFI_PASSWORD = ""
WIFI_COUNTRY = "DE"        # 2-letter regulatory domain (needed for channels 12/13)

# --- Weather (Open-Meteo, no API key) --------------------------------------
LOCATION_NAME = "Berlin"   # shown in the header
LATITUDE = 52.52           # set to None to disable weather
LONGITUDE = 13.41
TEMP_UNIT = "celsius"      # "celsius" or "fahrenheit"
WIND_UNIT = "kmh"          # "kmh", "ms", "mph" or "kn"

# --- Home Assistant (only needed for HA sensors) ---------------------------
HA_URL = "http://192.168.1.10:8123"   # use the IP, .local names don't resolve
HA_TOKEN = ""              # Profile -> Security -> Long-lived access tokens

# --- MQTT (only needed for MQTT sensors) ------------------------------------
MQTT_HOST = ""             # e.g. "192.168.1.10"
MQTT_PORT = 1883
MQTT_USER = ""
MQTT_PASSWORD = ""

# --- Sensors: up to 3 are shown ----------------------------------------------
# Home Assistant:  {"name": ..., "entity": "sensor.xyz"}
#   optional "attribute": read an attribute instead of the state
#            (attributes carry no unit, so also set "unit")
# MQTT:            {"name": ..., "topic": "some/topic"}   (exact topic, no + or #)
#   optional "key": field in a JSON payload; dots for nesting, numbers index
#            lists ("air.co2", "values.0")
#   optional "max_age": seconds without a message before the value shows "--"
# Common optional: "unit" (overrides HA's unit), "decimals" (default 1,
#            applied to any numeric value)
# A value that can't be read shows "--" plus the reason (e.g. "bad HA token").
SENSORS = [
    # {"name": "Living room", "entity": "sensor.living_room_temperature"},
    # {"name": "Garden", "topic": "zigbee2mqtt/garden", "key": "temperature", "unit": "°C"},
    # {"name": "Office CO2", "topic": "home/office/co2", "unit": "ppm", "decimals": 0},
]

# --- Behaviour (seconds unless noted) ----------------------------------------
WEATHER_INTERVAL = 900     # Open-Meteo refresh (failed fetches retry after 60 s;
                           # data older than 3x this is hidden)
SENSOR_INTERVAL = 120      # Home Assistant polling (MQTT is push); HA values
                           # older than 3x this show "--"
MIN_REDRAW_INTERVAL = 60   # minimum time between data-driven refreshes
PAGE_TIMEOUT = 120         # return to the main page after this (0 = never)
DEMO_INTERVAL = 300        # demo mode: how often sample values change
FLIP_DISPLAY = True        # rotated 180° (default); False = Waveshare orientation
PARTIAL_REFRESH = True     # fast, flicker-free page flips (False = always full)
FULL_REFRESH_EVERY = 5     # every Nth page flip is a full refresh to clear
                           # ghosting (1 = every flip is full)
WATCHDOG_TIMEOUT = 300     # reboot if the main loop hangs this long (0 = off)
NTP_HOST = None            # None = MicroPython default (pool.ntp.org)
UTC_OFFSET = 0             # hours; only used until weather provides the
                           # timezone (ignored in demo mode, which uses UTC)
