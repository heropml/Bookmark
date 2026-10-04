# -*- coding: utf-8 -*-
"""Weather for the page's local fallback request: UAPIs for Chinese city names, then Open-Meteo."""
from __future__ import annotations

import json
import math
import threading
import time

# Several tabs opening together share one upstream weather lookup.
WEATHER_CACHE_SECONDS = 5 * 60
WEATHER_CACHE: dict[tuple, tuple[float, bytes, str]] = {}
WEATHER_CACHE_LOCK = threading.Lock()


def weather_code(description: str) -> int:
    """Map the Chinese fallback provider's condition text to a WMO-style code."""
    if "雷" in description:
        return 96 if "冰雹" in description else 95
    if "雪" in description:
        if "大" in description or "暴" in description:
            return 75
        return 71
    if "雨" in description:
        if "阵" in description:
            return 80
        if "大" in description or "暴" in description:
            return 65
        if "中" in description:
            return 63
        return 61
    if any(word in description for word in ("雾", "霾", "沙尘")):
        return 45
    if "阴" in description:
        return 3
    if "云" in description:
        return 2
    if "晴" in description:
        return 0
    return 3


def weather_description(code: int) -> str:
    """Use the same concise labels as the page for Open-Meteo responses."""
    if code == 0:
        return "晴"
    if code in (1, 2):
        return "多云"
    if code == 3:
        return "阴"
    if code in (45, 48):
        return "雾"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "雨"
    if 71 <= code <= 77 or code in (85, 86):
        return "雪"
    if code >= 95:
        return "雷雨"
    return "天气"


def weather_from_uapis(city: str) -> tuple[float, int, str]:
    """Get Chinese city weather from the primary provider."""
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    url = "https://uapis.cn/api/v1/misc/weather?" + urlencode({"city": city})
    request = Request(url, headers={"User-Agent": "Bookmark/1.0"})
    with urlopen(request, timeout=2.5) as response:
        upstream = json.load(response)
    temperature = float(upstream["temperature"])
    description = str(upstream["weather"]).strip()
    if not description or not math.isfinite(temperature):
        raise ValueError("invalid UAPIs weather response")
    return temperature, weather_code(description), description


def weather_from_open_meteo(
    city: str, latitude: float | None, longitude: float | None
) -> tuple[float, int, str]:
    """Independent fallback: resolve a city if needed, then fetch Open-Meteo."""
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    valid_coordinates = (
        latitude is not None and longitude is not None
        and math.isfinite(latitude) and math.isfinite(longitude)
        and -90 <= latitude <= 90 and -180 <= longitude <= 180
    )
    if not valid_coordinates:
        geocode_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
            {"name": city, "count": 1, "language": "zh"}
        )
        request = Request(geocode_url, headers={"User-Agent": "Bookmark/1.0"})
        with urlopen(request, timeout=2.5) as response:
            geocode = json.load(response)
        hit = (geocode.get("results") or [None])[0]
        if not isinstance(hit, dict):
            raise ValueError("Open-Meteo city not found")
        latitude = float(hit["latitude"])
        longitude = float(hit["longitude"])

    weather_url = "https://api.open-meteo.com/v1/forecast?" + urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "timezone": "auto",
        }
    )
    request = Request(weather_url, headers={"User-Agent": "Bookmark/1.0"})
    with urlopen(request, timeout=2.5) as response:
        upstream = json.load(response)
    current = upstream["current"]
    temperature = float(current["temperature_2m"])
    code = int(current["weather_code"])
    if not math.isfinite(temperature):
        raise ValueError("invalid Open-Meteo weather response")
    return temperature, code, weather_description(code)


def current_weather(city: str, latitude: float | None, longitude: float | None) -> tuple[bytes, str]:
    """The page's weather JSON and the provider that answered; LookupError when none did."""
    key = (city, latitude, longitude)
    with WEATHER_CACHE_LOCK:
        cached = WEATHER_CACHE.get(key)
    if cached and time.monotonic() - cached[0] < WEATHER_CACHE_SECONDS:
        return cached[1], cached[2]
    source = "uapis"
    try:
        temperature, code, description = weather_from_uapis(city)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        source = "open-meteo"
        try:
            temperature, code, description = weather_from_open_meteo(city, latitude, longitude)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise LookupError("no weather provider answered") from error
    data = json.dumps(
        {
            "current": {"temperature_2m": temperature, "weather_code": code},
            "description": description,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    with WEATHER_CACHE_LOCK:
        now = time.monotonic()
        for stale in [k for k, v in WEATHER_CACHE.items() if now - v[0] >= WEATHER_CACHE_SECONDS]:
            del WEATHER_CACHE[stale]
        WEATHER_CACHE[key] = (now, data, source)
    return data, source
