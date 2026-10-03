import requests
import json
import os
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURACIÓ
# ============================================================

GTFS_RT_URL = "https://gtfsrt.renfe.com/trip_updates.json"
DATA_DIR = "data"

MADRID_TZ = ZoneInfo("Europe/Madrid")

avui = date.today()

fitxer = os.path.join(
    DATA_DIR,
    f"{avui.isoformat()}.json"
)


# ============================================================
# INICI
# ============================================================

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
print()
print("=== TRIP IDs GTFS-RT ===")

for trip_id in realtime_trips:
    print(
        "GTFS-RT:",
        repr(trip_id)
    )

print()
print("=== TRIP IDs DEL JSON ===")

for train in dades.get("trains", []):
    print(
        "JSON:",
        repr(
            train.get("train_id")
        )
    )

print()
print("==========================================")

# ============================================================
# FUNCIONS DE TEMPS
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


# ============================================================
# CONVERTIR RETARD A MINUTS
# ============================================================

def obtenir_retard(obj):

    if not isinstance(obj, dict):
        return None

    delay = obj.get("delay")

    if delay is None:
        return None

    try:

        return int(delay) / 60

    except Exception:

        return None


# ============================================================
# OBTENIR TIMESTAMP D'ARRIBADA
# ============================================================

def obtenir_timestamp_arribada(update):

    if not isinstance(update, dict):
        return None

    arrival = update.get(
        "arrival"
    )

    if not isinstance(arrival, dict):
        return None

    timestamp = arrival.get(
        "time"
    )

    if timestamp is not None:
        try:
            return int(timestamp)
        except Exception:
            pass

    return None


# ============================================================
# OBTENIR TIMESTAMP DE SORTIDA
# ============================================================

def obtenir_timestamp_sortida(update):

    if not isinstance(update, dict):
        return None

    departure = update.get(
        "departure"
    )

    if not isinstance(departure, dict):
        return None

    timestamp = departure.get(
        "time"
    )

    if timestamp is not None:
        try:
            return int(timestamp)
        except Exception:
            pass

    return None


# ============================================================
# OBTENIR RETARD D'UNA PARADA
# ============================================================

def obtenir_retard_parada(update):

    if not isinstance(update, dict):
        return None


    # Primer intentem arrival

    arrival = update.get(
        "arrival"
    )

    if isinstance(arrival, dict):

        delay = arrival.get(
            "delay"
        )

        if delay is not None:

            try:

                return round(
                    int(delay) / 60
                )

            except Exception:
                pass


    # Si no hi ha arrival, mirem departure

    departure = update.get(
        "departure"
    )

    if isinstance(departure, dict):

        delay = departure.get(
            "delay"
        )

        if delay is not None:

            try:

                return round(
                    int(delay) / 60
                )

            except Exception:
                pass


    return None


# ============================================================
# INDEXAR STOP UPDATES
# ============================================================

def crear_index_stop_updates(
    trip_update
):

    resultat = {}


    stop_updates = trip_update.get(
        "stopTimeUpdate",
        []
    )


    for update in stop_updates:

        if not isinstance(
            update,
            dict
        ):
            continue


        stop_id = str(
            update.get(
                "stopId",
                ""
            )
        ).strip()


        if stop_id:

            resultat[
                stop_id
            ] = update


    return resultat


# ============================================================
# ACTUALITZAR TRENS
# ============================================================

trens_actualitzats = 0
parades_actualitzades = 0
trens_sense_realtime = 0


for train in dades.get(
    "trains",
    []
):

    train_id = str(
        train.get(
            "train_id",
            ""
        )
    ).strip()


    if not train_id:
        continue


    # --------------------------------------------------------
    # BUSCAR EL TRAIN AL GTFS-RT
    # --------------------------------------------------------

    trip_update = realtime_trips.get(
        train_id
    )


    if not trip_update:

        trens_sense_realtime += 1

        continue


    trens_actualitzats += 1


    # --------------------------------------------------------
    # INDEXAR LES PARADES REALTIME
    # --------------------------------------------------------

    stop_updates = crear_index_stop_updates(
        trip_update
    )


    # --------------------------------------------------------
    # RETARD FINAL
    # --------------------------------------------------------

    final_delay = None


    # --------------------------------------------------------
    # ACTUALITZAR CADA PARADA
    # --------------------------------------------------------

    for stop in train.get(
        "stops",
        []
    ):

        stop_id = str(
            stop.get(
                "stop_id",
                ""
            )
        ).strip()


        update = stop_updates.get(
            stop_id
        )


        if not update:

            continue


        # ----------------------------------------------------
        # RETARD
        # ----------------------------------------------------

        delay = obter_retard = obter_retard_parada(
            update
        )


        if delay is not None:

            stop[
                "delay_minutes"
            ] = delay


        # ----------------------------------------------------
        # HORA REAL
        # ----------------------------------------------------

        timestamp = (
            obtenir_timestamp_arribada(
                update
            )
        )


        if timestamp is None:

            timestamp = (
                obtenir_timestamp_sortida(
                    update
                )
            )


        if timestamp is not None:

            actual_minutes = (
                timestamp_a_minuts(
                    timestamp
                )
            )


            if actual_minutes is not None:

                stop[
                    "actual_minutes"
                ] = actual_minutes


                stop[
                    "actual_time"
                ] = timestamp_a_iso(
                    timestamp
                )


                parades_actualitzades += 1


        # ----------------------------------------------------
        # RETARD FINAL
        # ----------------------------------------------------

        if delay is not None:

            final_delay = delay


    # --------------------------------------------------------
    # RETARD FINAL DEL TREN
    # --------------------------------------------------------

    if final_delay is not None:

        train[
            "final_delay_minutes"
        ] = round(
            final_delay
        )


    # --------------------------------------------------------
    # ESTAT DEL TRAIN
    # --------------------------------------------------------

    trip_properties = trip_update.get(
        "tripProperties",
        {}
    )


    # Si Renfe indica que el viatge ha acabat

    if (
        trip_properties.get(
            "isCanceled"
        )
        is True
    ):

        train[
            "cancelled"
        ] = True


    # ========================================================
    # ACTUALITZAR STARTED / ARRIVED
    # ========================================================

    actuals = []

    for stop in train.get(
        "stops",
        []
    ):

        actual = stop.get(
            "actual_minutes"
        )

        if actual is not None:

            actuals.append(
                actual
            )


    if actuals:

        train[
            "started"
        ] = True


        # Mirem l'última parada

        ultima = train[
            "stops"
        ][-1]


        ultima_actual = ultima.get(
            "actual_minutes"
        )


        if ultima_actual is not None:

            ara = (
                datetime.now(
                    MADRID_TZ
                ).hour * 60
                +
                datetime.now(
                    MADRID_TZ
                ).minute
            )


            # Si l'hora real de l'última parada
            # ja ha passat, considerem arribat.

            if ultima_actual <= ara:

                train[
                    "arrived"
                ] = True


# ============================================================
# GUARDAR RESULTAT
# ============================================================

dades[
    "realtime_updated_at"
] = datetime.now(
    MADRID_TZ
).isoformat()


dades[
    "source_type"
] = "GTFS + GTFS-RT"


with open(
    fitxer,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        dades,
        f,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# RESUM
# ============================================================

print()
print(
    "=========================================="
)

print(
    "RESULTAT REALTIME"
)

print(
    "Trips GTFS-RT:",
    len(realtime_trips)
)

print(
    "Trens R15 actualitzats:",
    trens_actualitzats
)

print(
    "Trens sense realtime:",
    trens_sense_realtime
)

print(
    "Parades actualitzades:",
    parades_actualitzades
)

print(
    "Fitxer actualitzat:",
    fitxer
)

print(
    "=========================================="
)
