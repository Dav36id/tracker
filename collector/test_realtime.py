import requests
import json


# ============================================================
# PROVA API REALTIME MOBILITAT PENEDÈS
# ============================================================

URL = "https://mobilitatpenedes.cat/api/departures"

PARAMS = {
    "parada": "Reus"
}


print("==========================================")
print("PROVA REALTIME MOBILITAT PENEDÈS")
print("==========================================")

print()
print("URL:")
print(URL)

print()
print("Parada:")
print("Reus")

print()
print("Consultant API...")

try:

    response = requests.get(
        URL,
        params=PARAMS,
        timeout=30,
        headers={
            "User-Agent": "R15-Tracker/1.0"
        }
    )

    print()
    print("HTTP STATUS:")
    print(response.status_code)

    print()
    print("URL FINAL:")
    print(response.url)

    response.raise_for_status()

    dades = response.json()

    print()
    print("==========================================")
    print("RESPOSTA JSON")
    print("==========================================")

    print(
        json.dumps(
            dades,
            ensure_ascii=False,
            indent=2
        )
    )

    print()
    print("==========================================")
    print("PROVA FINALITZADA CORRECTAMENT")
    print("==========================================")

except Exception as e:

    print()
    print("==========================================")
    print("ERROR")
    print("==========================================")

    print(
        repr(e)
    )

    raise
