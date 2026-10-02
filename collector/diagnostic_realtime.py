import requests
import json

URL = "https://gtfsrt.renfe.com/trip_updates.json"

response = requests.get(
    URL,
    timeout=30,
    headers={
        "User-Agent": "R15-Tracker/1.0"
    }
)

response.raise_for_status()

data = response.json()

print("TIPUS:", type(data))
print()

print("CLAUS PRINCIPALS:")
print(list(data.keys()))
print()

entities = data.get("entity", [])

print("NOMBRE ENTITATS:", len(entities))
print()

if entities:

    print("PRIMERA ENTITAT:")
    print(
        json.dumps(
            entities[0],
            indent=2,
            ensure_ascii=False
        )
    )
