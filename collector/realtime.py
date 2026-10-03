import json
import os
import requests
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURACIÓ
# ============================================================

GTFS_RT_URL = "https://gtfsrt.renfe.com/trip_updates.json"

DATA_DIR = "data"

TZ = ZoneInfo("Europe/Madrid")

HEADERS = {
    "User-Agent": "R15-Tracker/1.0"
}

# Diferència màxima per considerar que una coincidència és possible
MAX_MATCH_MINUTES = 45


# ============================================================
# FUNCIONS AUXILIARS
# ============================================================

def convertir_timestamp(timestamp):
    """
    Converteix timestamp Unix a datetime Europe/Madrid.
    """
    try:
        return datetime.fromtimestamp(
            int(timestamp),
            tz=timezone.utc
        ).astimezone(TZ)
    except Exception:
        return None


def minuts_des_de_mitjanit(dt):
    """
    Retorna els minuts des de mitjanit.
    """
    return dt.hour * 60 + dt.minute


def normalitzar_id(valor):
    """
    Normalitza un ID per evitar problemes d'espais.
    """
    if valor is None:
        return ""

    return str(valor).strip()


def carregar_json_avui():
    """
    Carrega el JSON del dia actual.
    """

    avui = date.today().isoformat()

    path = os.path.join(
        DATA_DIR,
        f"{avui}.json"
    )

    if not os.path.exists(path):

        print(
            "ERROR: no existeix:",
            path
        )

        return None, path

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        dades = json.load(f)

    return dades, path


# ============================================================
# DESCARREGAR GTFS-RT
# ============================================================

def descarregar_realtime():

    print(
        "Descarregant GTFS-RT de Renfe..."
    )

    response = requests.get(
        GTFS_RT_URL,
        timeout=30,
        headers=HEADERS
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# EXTREURE TRIPS REALTIME
# ============================================================

def extreure_trips_realtime(feed):

    resultat = []

    entities = feed.get(
        "entity",
        []
    )

    print(
        "Entitats:",
        len(entities)
    )

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

        trip_id = normalitzar_id(
            trip.get("tripId")
        )

        if not trip_id:
            continue

        relationship = trip.get(
            "scheduleRelationship"
        )

        # Guardem les dades de totes les parades
        stop_updates = []

        for stop_update in trip_update.get(
            "stopTimeUpdate",
            []
        ):

            stop_id = normalitzar_id(
                stop_update.get("stopId")
            )

            if not stop_id:
                continue

            arrival = stop_update.get(
                "arrival",
                {}
            )

            departure = stop_update.get(
                "departure",
                {}
            )

            timestamp = (
                arrival.get("time")
                or departure.get("time")
            )

            delay_seconds = (
                arrival.get("delay")
                if arrival.get("delay") is not None
                else departure.get("delay")
            )

            if timestamp is None:
                continue

            dt = convertir_timestamp(
                timestamp
            )

            if dt is None:
                continue

            stop_updates.append({
                "stop_id": stop_id,
                "datetime": dt,
                "minutes": minuts_des_de_mitjanit(dt),
                "delay_seconds": (
                    int(delay_seconds)
                    if delay_seconds is not None
                    else 0
                )
            })

        resultat.append({
            "trip_id": trip_id,
            "relationship": relationship,
            "stops": stop_updates
        })

    return resultat


# ============================================================
# CREAR ÍNDEX PER STOP
# ============================================================

def crear_index_stop(trips_realtime):

    index = {}

    for trip in trips_realtime:

        trip_id = trip["trip_id"]

        for stop in trip["stops"]:

            stop_id = stop["stop_id"]

            if stop_id not in index:
                index[stop_id] = []

            index[stop_id].append({
                "trip_id": trip_id,
                "minutes": stop["minutes"],
                "datetime": stop["datetime"],
                "delay_seconds": stop["delay_seconds"],
                "relationship": trip["relationship"]
            })

    return index


# ============================================================
# TROBAR HORA TEÒRICA D'UNA PARADA
# ============================================================

def hora_teorica_parada(stop):

    valor = stop.get(
        "scheduled_arrival"
    )

    if valor is None:

        valor = stop.get(
            "scheduled_departure"
        )

    if valor is None:
        return None

    try:
        return int(valor)

    except Exception:
        return None


# ============================================================
# MATCHING PER ID DIRECTE
# ============================================================

def buscar_matching_directe(
    train,
    realtime_by_id
):

    train_id = normalitzar_id(
        train.get("train_id")
    )

    if not train_id:
        return None

    return realtime_by_id.get(
        train_id
    )


# ============================================================
# MATCHING PER PARADA + HORA
# ============================================================

def buscar_matching_intelligent(
    train,
    index_stop,
    used_trip_ids
):

    millor = None

    millor_distancia = None

    stops = train.get(
        "stops",
        []
    )

    for static_stop in stops:

        stop_id = normalitzar_id(
            static_stop.get("stop_id")
        )

        if not stop_id:
            continue

        hora_teorica = hora_teorica_parada(
            static_stop
        )

        if hora_teorica is None:
            continue

        candidats = index_stop.get(
            stop_id,
            []
        )

        for candidat in candidats:

            trip_id = candidat["trip_id"]

            # No reutilitzar un mateix tren realtime
            if trip_id in used_trip_ids:
                continue

            hora_real = candidat["minutes"]

            diferencia = abs(
                hora_real - hora_teorica
            )

            if diferencia > MAX_MATCH_MINUTES:
                continue

            # Penalització lleugera si el retard declarat
            # no concorda amb la diferència horària.
            delay_minutes = (
                candidat["delay_seconds"] / 60
            )

            diferencia_delay = abs(
                (hora_real - hora_teorica)
                - delay_minutes
            )

            puntuacio = (
                diferencia
                + diferencia_delay * 0.25
            )

            if (
                millor is None
                or puntuacio < millor_distancia
            ):

                millor = {
                    "trip_id": trip_id,
                    "static_stop": static_stop,
                    "realtime_stop": candidat,
                    "score": puntuacio
                }

                millor_distancia = puntuacio

    return millor


# ============================================================
# APLICAR REALTIME A UNA PARADA
# ============================================================

def aplicar_realtime(
    static_stop,
    realtime_stop
):

    delay_seconds = realtime_stop.get(
        "delay_seconds",
        0
    )

    delay_minutes = round(
        delay_seconds / 60
    )

    actual_minutes = realtime_stop.get(
        "minutes"
    )

    actual_datetime = realtime_stop.get(
        "datetime"
    )

    static_stop["actual_minutes"] = (
        actual_minutes
    )

    static_stop["delay_minutes"] = (
        delay_minutes
    )

    if actual_datetime:

        static_stop["actual_time"] = (
            actual_datetime.isoformat()
        )


# ============================================================
# ACTUALITZAR UN TREN
# ============================================================

def actualitzar_train(
    train,
    realtime_trip
):

    updated = 0

    realtime_stops = realtime_trip.get(
        "stops",
        []
    )

    # Índex dels stop realtime
    realtime_by_stop = {}

    for stop in realtime_stops:

        realtime_by_stop[
            stop["stop_id"]
        ] = stop

    for static_stop in train.get(
        "stops",
        []
    ):

        stop_id = normalitzar_id(
            static_stop.get("stop_id")
        )

        realtime_stop = (
            realtime_by_stop.get(
                stop_id
            )
        )

        if realtime_stop is None:
            continue

        aplicar_realtime(
            static_stop,
            realtime_stop
        )

        updated += 1

    return updated


# ============================================================
# ACTUALITZAR ESTATS DEL TREN
# ============================================================

def actualitzar_estat_train(train):

    stops = train.get(
        "stops",
        []
    )

    if not stops:
        return

    stops_amb_realtime = [
        stop
        for stop in stops
        if stop.get("actual_minutes") is not None
    ]

    if not stops_amb_realtime:
        return

    # Retard final basat en l'última parada
    ultima = stops_amb_realtime[-1]

    if ultima.get("delay_minutes") is not None:

        train["final_delay_minutes"] = (
            ultima["delay_minutes"]
        )

    # El tren ha començat si tenim alguna parada realtime
    train["started"] = True

    # Si tenim realtime de l'última parada,
    # considerem que ha arribat.
    ultima_parada = stops[-1]

    if (
        ultima_parada.get(
            "actual_minutes"
        ) is not None
    ):

        train["arrived"] = True


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("==========================================")
    print("R15 REALTIME")
    print(
        "Data:",
        date.today().isoformat()
    )
    print("==========================================")

    # --------------------------------------------------------
    # CARREGAR JSON
    # --------------------------------------------------------

    dades, path = carregar_json_avui()

    if dades is None:
        return

    print(
        "Carregant:",
        path
    )

    # --------------------------------------------------------
    # DESCARREGAR FEED
    # --------------------------------------------------------

    try:

        feed = descarregar_realtime()

    except Exception as e:

        print(
            "ERROR descarregant GTFS-RT:",
            repr(e)
        )

        return

    # --------------------------------------------------------
    # EXTREURE TRIPS
    # --------------------------------------------------------

    trips_realtime = extreure_trips_realtime(
        feed
    )

    print(
        "Trips amb informació:",
        len(trips_realtime)
    )

    # --------------------------------------------------------
    # ÍNDEXOS
    # --------------------------------------------------------

    realtime_by_id = {
        trip["trip_id"]: trip
        for trip in trips_realtime
    }

    index_stop = crear_index_stop(
        trips_realtime
    )

    # Trips realtime ja utilitzats
    used_trip_ids = set()

    # --------------------------------------------------------
    # TROBAR TRENS R15
    # --------------------------------------------------------

    trains = dades.get(
        "trains",
        []
    )

    r15_trains = []

    for train in trains:

        # collect.py ja genera només R15,
        # però deixem aquesta comprovació.
        route = normalitzar_id(
            train.get("route_id")
        )

        train_id = normalitzar_id(
            train.get("train_id")
        )

        if (
            "R15" in route
            or "R15" in train_id
            or route == ""
        ):

            r15_trains.append(
                train
            )

    # Si no podem determinar route_id,
    # treballem amb tots els trens del fitxer.
    if not r15_trains:
        r15_trains = trains

    # --------------------------------------------------------
    # MATCHING
    # --------------------------------------------------------

    trains_updated = 0
    stops_updated = 0
    direct_matches = 0
    intelligent_matches = 0

    for train in r15_trains:

        train_id = normalitzar_id(
            train.get("train_id")
        )

        # ----------------------------------------------
        # 1. MATCHING DIRECTE
        # ----------------------------------------------

        direct = buscar_matching_directe(
            train,
            realtime_by_id
        )

        if (
            direct is not None
            and train_id not in used_trip_ids
        ):

            count = actualitzar_train(
                train,
                direct
            )

            if count > 0:

                used_trip_ids.add(
                    direct["trip_id"]
                )

                trains_updated += 1
                direct_matches += 1
                stops_updated += count

                continue

        # ----------------------------------------------
        # 2. MATCHING INTELLIGENT
        # ----------------------------------------------

        intelligent = buscar_matching_intelligent(
            train,
            index_stop,
            used_trip_ids
        )

        if intelligent is None:
            continue

        realtime_trip_id = intelligent[
            "trip_id"
        ]

        realtime_trip = realtime_by_id.get(
            realtime_trip_id
        )

        if realtime_trip is None:
            continue

        count = actualitzar_train(
            train,
            realtime_trip
        )

        if count > 0:

            used_trip_ids.add(
                realtime_trip_id
            )

            trains_updated += 1
            intelligent_matches += 1
            stops_updated += count

    # --------------------------------------------------------
    # ACTUALITZAR ESTATS
    # --------------------------------------------------------

    for train in r15_trains:

        actualitzar_estat_train(
            train
        )

    # --------------------------------------------------------
    # METADADES
    # --------------------------------------------------------

    ara = datetime.now(
        TZ
    )

    dades["realtime_updated_at"] = (
        ara.isoformat()
    )

    dades["source_type"] = (
        "Renfe GTFS-RT"
    )

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            dades,
            f,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # RESULTAT
    # --------------------------------------------------------

    print()
    print("==========================================")
    print("RESULTAT REALTIME")
    print(
        "Trips GTFS-RT:",
        len(trips_realtime)
    )

    print(
        "Trens R15 actualitzats:",
        trains_updated
    )

    print(
        "  - Matching directe:",
        direct_matches
    )

    print(
        "  - Matching intel·ligent:",
        intelligent_matches
    )

    print(
        "Trens sense realtime:",
        max(
            0,
            len(r15_trains) - trains_updated
        )
    )

    print(
        "Parades actualitzades:",
        stops_updated
    )

    print(
        "Trips realtime utilitzats:",
        len(used_trip_ids)
    )

    print(
        "Fitxer actualitzat:",
        path
    )

    print("==========================================")


# ============================================================
# EXECUCIÓ
# ============================================================

if __name__ == "__main__":
    main()
