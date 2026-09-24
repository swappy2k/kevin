import json
from urllib.parse import quote
from urllib.request import Request, urlopen


def get_weather(city: str) -> str:
    """
    Get current weather for a city using wttr.in.
    No API key required.
    """

    city = city.strip()

    if not city:
        return "Tell me the city."


    url = (
        f"https://wttr.in/{quote(city)}"
        f"?format=j1"
    )

    request = Request(
        url,
        headers={
            "User-Agent": "Kevin Assistant"
        },
    )

    try:

        with urlopen(
            request,
            timeout=15,
        ) as response:

            data = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except Exception:

        return (
            f"I couldn't get the weather "
            f"for {city}."
        )


    try:

        current = data["current_condition"][0]

        temperature = current["temp_C"]
        feels_like = current["FeelsLikeC"]
        humidity = current["humidity"]
        description = current["weatherDesc"][0]["value"]
        wind = current["windspeedKmph"]


        return (
            f"{city}: {description}, "
            f"{temperature}°C, "
            f"feels like {feels_like}°C, "
            f"humidity {humidity}%, "
            f"wind {wind} km/h."
        )

    except (
        KeyError,
        IndexError,
        TypeError,
    ):

        return (
            f"I couldn't understand "
            f"the weather data for {city}."
        )