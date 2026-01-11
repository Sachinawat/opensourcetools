import logging
from typing import Optional

import requests
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class WeatherResult(BaseModel):
    city: str
    country: str
    temperature_c: float = Field(..., description="Current temperature in Celsius")
    apparent_temperature_c: Optional[float] = Field(
        None, description="Feels like temperature in Celsius"
    )
    humidity_pct: Optional[float] = Field(None, description="Relative humidity percent")
    precipitation_mm: Optional[float] = Field(
        None, description="Current precipitation in millimeters"
    )
    source: str = "open-meteo.com"


def _geocode_city(city: str):
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": city, "count": 1, "language": "en", "format": "json"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("results"):
        raise ValueError(f"Could not resolve city '{city}'")
    return data["results"][0]


_CITY_NORMALIZATION = {
    "BLR": "Bengaluru",
    "BANGALORE": "Bengaluru",
    "BENGALURU": "Bengaluru",
    "DELHI": "New Delhi",
    "NEW DELHI": "New Delhi",
}


def _fetch_weather(lat: float, lon: float):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation",
        "timezone": "auto",
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("current", {})


def fetch_weather(city: str, country: str = "India") -> WeatherResult:
    """
    Fetch current weather for an Indian city using Open-Meteo (no API key required).
    """
    if not city:
        raise ValueError("City is required")

    normalized_city = _CITY_NORMALIZATION.get(city.strip().upper(), city)

    geo = _geocode_city(normalized_city)
    resolved_country = geo.get("country", "")
    if country.lower() not in resolved_country.lower():
        raise ValueError(f"Requested country '{country}' does not match result '{resolved_country}'")

    lat, lon = geo["latitude"], geo["longitude"]
    current = _fetch_weather(lat, lon)

    try:
        return WeatherResult(
            city=geo.get("name", city),
            country=resolved_country,
            temperature_c=current.get("temperature_2m"),
            apparent_temperature_c=current.get("apparent_temperature"),
            humidity_pct=current.get("relative_humidity_2m"),
            precipitation_mm=current.get("precipitation"),
        )
    except ValidationError as exc:
        logger.exception("WeatherResult validation failed")
        raise ValueError(f"Malformed weather data: {exc}") from exc
