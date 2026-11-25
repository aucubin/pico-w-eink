# Open-Meteo forecast client (https://open-meteo.com, no API key needed).
# Values the API returns as null stay None; the UI shows them as "--".
_URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        "weather_code,wind_speed_10m,wind_direction_10m,is_day"
        "&hourly=temperature_2m,precipitation_probability&forecast_hours=24"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max,sunrise,sunset&forecast_days=4"
        "&timezone=auto&timeformat=unixtime"
        "&temperature_unit={tu}&wind_speed_unit={wu}")


def fetch(get_json, lat, lon, temp_unit="celsius", wind_unit="kmh", default_offset=0):
    j = get_json(_URL.format(lat=lat, lon=lon, tu=temp_unit, wu=wind_unit))
    cur, d, h = j["current"], j["daily"], j["hourly"]
    if cur.get("temperature_2m") is None or cur.get("weather_code") is None:
        raise ValueError("weather: response without current temperature/code")
    days = []
    for i in range(len(d["time"])):
        if d["weather_code"][i] is None:
            break
        days.append({
            "t": d["time"][i],
            "code": d["weather_code"][i],
            "hi": d["temperature_2m_max"][i],
            "lo": d["temperature_2m_min"][i],
            "pop": d["precipitation_probability_max"][i],
        })
    offset = j.get("utc_offset_seconds")
    if offset is None:
        print("weather: no utc_offset_seconds, using UTC_OFFSET")
        offset = default_offset
    return {
        "temp": cur["temperature_2m"],
        "feels": cur.get("apparent_temperature"),
        "rh": cur.get("relative_humidity_2m"),
        "code": cur["weather_code"],
        "is_day": cur.get("is_day", 1),
        "wind": cur.get("wind_speed_10m"),
        "wind_dir": cur.get("wind_direction_10m"),
        "sunrise": d["sunrise"][0] if d["sunrise"] else None,
        "sunset": d["sunset"][0] if d["sunset"] else None,
        "days": days,
        "hourly_start": h["time"][0],
        "hourly_t": h["temperature_2m"],
        "hourly_pop": h["precipitation_probability"],
        "offset": offset,
    }
