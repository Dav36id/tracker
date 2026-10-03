import requests
import json
import os
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo


GTFS_RT_URL = "https://gtfsrt.renfe.com/trip_updates.json"
DATA_DIR = "data"

MADRID_TZ = ZoneInfo("Europe/Madrid")

avui = date.today()

fitxer = os.path.join(
    DATA_DIR,
    f"{avui.isoformat()}.json"
)


print("==========================================")
print("R15 REALTIME")
print("Data:", avui)
print("==========================================")


if not os.path.exists(fitxer):
    raise Exception(
        f"No existeix el fitxer {fitxer}"
    )


# ============================================================
# CARREGAR JSON DEL DIA
# ============================================================

with open(
    fitxer,
    "r",
    encoding="utf-8"
) as f:

    dades = json.load(f)


print(
    "Carregant:",
    fitxer
)


# ============================================================
# DESCARREGAR GTFS-RT RENFE
# ============================================================

print(
    "Descarregant GTFS-RT de Renfe..."
)


response = requests.get(
    GTFS_RT_URL,
    timeout=30,
    headers={
        "User-Agent": "R15-Tracker/1.0"
    }
)


response.raise_for_status()


feed = response.json()


entities = feed.get(
    "entity",
    []
)


print(
    "Entitats:",
    len(entities)
)


# ============================================================
# CREAR DICCIONARI DE TRIPS EN TEMPS REAL
# ============================================================

realtime_trips = {}


for entity in entities:

    trip_update = entity.get(
        "tripUpdate"
    )

    if not trip_update:
        continue


    trip = trip_update.get(
        "trip",
        {}
    )


    trip_id = str(
        trip.get(
            "tripId",
            ""
        )
    ).strip()


    if not trip_id:
        continue


    realtime_trips[trip_id] = trip_update


print(
    "Trips amb informació:",
    len(realtime_trips)
)


# ============================================================
# FUNCIONS
# ============================================================

def timestamp_a_datetime(timestamp):

    if timestamp is None:
        return None

    try:

        timestamp = int(timestamp)

        dt_utc = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc
        )

        return dt_utc.astimezone(
            MADRID_TZ
        )

    except Exception:

        return None


def timestamp_a_iso(timestamp):

    dt = timestamp_a_datetime(
        timestamp
    )

    if dt is None:
        return None

    return dt.isoformat()


def timestamp_a_minuts(timestamp):

    dt = timestamp_a_datetime(
        timestamp
    )

    if dt is None:
        return None

    return (
        dt.hour * 60
        + dt.minute
    )


def minuts_a_hora(minuts):

    if minuts is None:
        return "--:--"

    minuts = int(minuts)

    minuts = minuts % 1440

    hores = minuts // 60
    minuts_restants = minuts % 60

    return (
        f"{hores:02d}:"
        f"{minuts_restants:02d}"
    )
