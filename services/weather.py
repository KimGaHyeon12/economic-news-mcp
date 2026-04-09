import httpx
from datetime import date, timedelta


class WeatherError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


WEATHER_CODE_MAP = {
    0: "\ub9d1\uc74c",
    1: "\ub300\uccb4\ub85c \ub9d1\uc74c",
    2: "\ubd80\ubd84\uc801\uc73c\ub85c \ud750\ub9bc",
    3: "\ud750\ub9bc",
    45: "\uc548\uac1c",
    48: "\uc11c\ub9ac \uc548\uac1c",
    51: "\uc57d\ud55c \uc774\uc2ac\ube44",
    53: "\uc774\uc2ac\ube44",
    55: "\uac15\ud55c \uc774\uc2ac\ube44",
    61: "\uc57d\ud55c \ube44",
    63: "\ube44",
    65: "\uac15\ud55c \ube44",
    71: "\uc57d\ud55c \ub208",
    73: "\ub208",
    75: "\uac15\ud55c \ub208",
    80: "\uc57d\ud55c \uc18c\ub098\uae30",
    81: "\uc18c\ub098\uae30",
    82: "\uac15\ud55c \uc18c\ub098\uae30",
    95: "\ub1cc\uc6b0",
}

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
INCHEON_LATITUDE = 37.4563
INCHEON_LONGITUDE = 126.7052
DEFAULT_LOCATION = "\uc778\ucc9c"


def _parse_date(target_date: str | None) -> date | None:
    if not target_date:
        return None

    try:
        return date.fromisoformat(target_date)
    except ValueError as exc:
        raise WeatherError("date must be in YYYY-MM-DD format.", status_code=400) from exc


def _fetch_json(url: str, params: dict) -> dict:
    try:
        with httpx.Client(trust_env=False, timeout=10.0) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        detail = ""
        if getattr(exc, "response", None) is not None:
            detail = f" Details: {exc.response.text}"
        raise WeatherError(
            f"\ub0a0\uc528 \uc815\ubcf4\ub97c \uac00\uc838\uc624\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.{detail}",
            status_code=502,
        ) from exc

    return response.json()


def _resolve_location(location: str | None) -> tuple[str, float, float]:
    if not location:
        return DEFAULT_LOCATION, INCHEON_LATITUDE, INCHEON_LONGITUDE

    data = _fetch_json(
        OPEN_METEO_GEOCODING_URL,
        {
            "name": location,
            "count": 1,
            "language": "ko",
            "format": "json",
        },
    )
    results = data.get("results", [])
    if not results:
        raise WeatherError(f"Could not find coordinates for location '{location}'.", status_code=404)

    top = results[0]
    return (
        top.get("name", location),
        top["latitude"],
        top["longitude"],
    )


def _extract_daily_entries(data: dict) -> list[dict]:
    location_name = data.get("_location_name", DEFAULT_LOCATION)
    daily = data.get("daily")
    if not daily:
        raise WeatherError("\ub0a0\uc528 \uc751\ub2f5 \ud615\uc2dd\uc774 \uc62c\ubc14\ub974\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.", status_code=502)

    dates = daily.get("time", [])
    codes = daily.get("weather_code", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])

    entries = []
    for index, item_date in enumerate(dates):
        weather_code = codes[index] if index < len(codes) else None
        entries.append(
            {
                "location": location_name,
                "date": item_date,
                "temperature_max_c": max_temps[index] if index < len(max_temps) else None,
                "temperature_min_c": min_temps[index] if index < len(min_temps) else None,
                "weather_code": weather_code,
                "weather_text": WEATHER_CODE_MAP.get(weather_code, "\uc54c \uc218 \uc5c6\uc74c"),
                "is_current": False,
            }
        )

    if not entries:
        raise WeatherError("No forecast data was returned for the requested date.", status_code=404)

    return entries


def get_today_weather(
    location: str | None = None,
    target_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    resolved_location, latitude, longitude = _resolve_location(location)
    today = date.today()
    single_date = _parse_date(target_date)
    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)

    if single_date is not None:
        parsed_start = single_date
        parsed_end = single_date

    if parsed_start is None and parsed_end is not None:
        parsed_start = parsed_end
    if parsed_end is None and parsed_start is not None:
        parsed_end = parsed_start

    if parsed_start and parsed_end and parsed_start > parsed_end:
        raise WeatherError("start_date must be before or equal to end_date.", status_code=400)

    if parsed_start is None and parsed_end is None:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "timezone": "Asia/Seoul",
        }
        data = _fetch_json(OPEN_METEO_URL, params)
        current = data.get("current")
        if not current:
            raise WeatherError("\ub0a0\uc528 \uc751\ub2f5 \ud615\uc2dd\uc774 \uc62c\ubc14\ub974\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.", status_code=502)

        temperature = current.get("temperature_2m")
        weather_code = current.get("weather_code")

        return {
            "location": resolved_location,
            "date": today.isoformat(),
            "temperature_c": temperature,
            "weather_code": weather_code,
            "weather_text": WEATHER_CODE_MAP.get(weather_code, "\uc54c \uc218 \uc5c6\uc74c"),
            "is_current": True,
        }

    assert parsed_start is not None and parsed_end is not None

    entries: list[dict] = []

    if parsed_start < today:
        archive_end = min(parsed_end, today - timedelta(days=1))
        archive_data = _fetch_json(
            OPEN_METEO_ARCHIVE_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": "Asia/Seoul",
                "start_date": parsed_start.isoformat(),
                "end_date": archive_end.isoformat(),
            },
        )
        archive_data["_location_name"] = resolved_location
        entries.extend(_extract_daily_entries(archive_data))

    if parsed_end >= today:
        forecast_start = max(parsed_start, today)
        forecast_data = _fetch_json(
            OPEN_METEO_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": "Asia/Seoul",
                "start_date": forecast_start.isoformat(),
                "end_date": parsed_end.isoformat(),
            },
        )
        forecast_data["_location_name"] = resolved_location
        entries.extend(_extract_daily_entries(forecast_data))

    if not entries:
        raise WeatherError("No weather data was returned for the requested range.", status_code=404)

    if len(entries) == 1:
        return entries[0]

    return {
        "location": resolved_location,
        "start_date": parsed_start.isoformat(),
        "end_date": parsed_end.isoformat(),
        "is_current": False,
        "entries": entries,
    }
