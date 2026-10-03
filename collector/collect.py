import csv
import io
import json
import os
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


# ============================================================
# CONFIGURACIÓ
# ============================================================

GTFS_URL = "https://data.transport.gencat.cat/estatic/renfe/GTFS/fomento_transit.zip"

DATA_DIR = "data"

TZ = ZoneInfo("Europe/Madrid")

# Diferència màxima que permetem entre:
# actual - teòric
# i
# delay
#
# Exemple correcte:
# teòric 16:32
# delay +5
# real 16:37
#
# 16:37 - 16:32 = 5
#
# Exemple incorrecte:
# teòric 16:32
# delay +5
# real 16:06
#
# 16:06 - 16:32 = -26
# -> NO coherent
MAX_REALTIME_ERROR_MINUTES = 5


# ============================================================
# UTILITATS
# ============================================================

def minuts_des_de_mitjanit(value):
    """
    Converteix HH:MM o HH:MM:SS a minuts des de mitjanit.
    """

    if not value:
        return None

    value = str(value).strip()

    try:
        parts = value.split(":")

        hour = int(parts[0])
        minute = int(parts[1])

        return hour * 60 + minute

    except Exception:
        return None


def normalitzar_text(value):
    if value is None:
        return ""

    return str(value).strip()


def carregar_csv(z, nom):
    """
    Llegeix un CSV del GTFS i elimina espais dels headers i valors.
    """

    with z.open(nom) as f:
        text = io.TextIOWrapper(f, encoding="utf-8-sig")

        reader = csv.DictReader(text)

        files = []

        for row in reader:
            clean = {}

            for key, value in row.items():
                key = normalitzar_text(key)
                value = normalitzar_text(value)

                clean[key] = value

            files.append(clean)

        return files


def carregar_json_anterior(data_path):
    """
    Carrega el JSON existent del dia actual, si existeix.
    """

    if not os.path.exists(data_path):
        return None

    try:
        with open(data_path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"⚠️ No s'ha pogut llegir el JSON anterior: {e}")
        return None


# ============================================================
# VALIDACIÓ DE REALTIME ANTIC
# ============================================================

def realtime_es_coherent(stop_nou, stop_antic):
    """
    Comprova si les dades de temps real antigues tenen sentit.

    Exigim:

        actual - teòric ≈ delay

    amb un marge de MAX_REALTIME_ERROR_MINUTES.

    Això evita conservar errors com:

        Teòric: 16:32
        Real:    16:06
        Delay:   +5

    perquè:

        16:06 - 16:32 = -26

    i no +5.
    """

    if not isinstance(stop_antic, dict):
        return False

    actual = stop_antic.get("actual_minutes")
    delay = stop_antic.get("delay_minutes")

    if actual is None or delay is None:
        return False

    try:
        actual = float(actual)
        delay = float(delay)
    except Exception:
        return False

    # Horari teòric nou
    theoretical = stop_nou.get("scheduled_arrival")

    if theoretical is None:
        theoretical = stop_nou.get("scheduled_departure")

    if theoretical is None:
        return False

    try:
        theoretical = float(theoretical)
    except Exception:
        return False

    diferencia = actual - theoretical

    error = abs(diferencia - delay)

    if error > MAX_REALTIME_ERROR_MINUTES:
        print(
            "🧹 Realtime antic descartat:"
            f" teòric={theoretical},"
            f" real={actual},"
            f" delay={delay},"
            f" error={error:.1f}"
        )

        return False

    return True


# ============================================================
# CONSERVAR REALTIME VÀLID
# ============================================================

def conservar_realtime_anterior(circulacions, dades_anteriors):
    """
    Conserva les dades realtime del JSON anterior,
    però NOMÉS si són coherents.

    També recalcula:

        started
        arrived
        final_delay_minutes

    a partir de les dades realtime vàlides.
    """

    if not dades_anteriors:
        return

    trens_antics = {}

    for tren in dades_anteriors.get("trains", []):
        train_id = tren.get("train_id")

        if train_id:
            trens_antics[str(train_id)] = tren

    conservats = 0
    descartats = 0

    for tren in circulacions:

        train_id = str(tren.get("train_id", ""))

        antic = trens_antics.get(train_id)

        if not antic:
            continue

        stops_antics = {}

        for stop in antic.get("stops", []):
            stop_id = normalitzar_text(stop.get("stop_id"))

            if stop_id:
                stops_antics[stop_id] = stop

        valid_realtime_stops = []

        # ----------------------------------------------------
        # STOPS
        # ----------------------------------------------------

        for stop in tren.get("stops", []):

            stop_id = normalitzar_text(stop.get("stop_id"))

            if not stop_id:
                continue

            antic_stop = stops_antics.get(stop_id)

            if not antic_stop:
                continue

            if not realtime_es_coherent(stop, antic_stop):

                descartats += 1

                # Ens assegurem que no quedi cap resta antiga
                stop["actual_minutes"] = None
                stop["actual_time"] = None
                stop["delay_minutes"] = None

                continue

            # ------------------------------------------------
            # REALTIME VÀLID
            # ------------------------------------------------

            stop["actual_minutes"] = antic_stop.get("actual_minutes")
            stop["actual_time"] = antic_stop.get("actual_time")
            stop["delay_minutes"] = antic_stop.get("delay_minutes")

            # També conservem altres camps eventuals
            if antic_stop.get("realtime_delay_minutes") is not None:
                stop["realtime_delay_minutes"] = antic_stop.get(
                    "realtime_delay_minutes"
                )

            if antic_stop.get("delay_seconds") is not None:
                stop["delay_seconds"] = antic_stop.get(
                    "delay_seconds"
                )

            valid_realtime_stops.append(stop)

            conservats += 1

        # ----------------------------------------------------
        # ESTAT DEL TREN
        # ----------------------------------------------------

        # Sempre partim d'un estat net.
        tren["started"] = False
        tren["arrived"] = False
        tren["final_delay_minutes"] = 0

        if not valid_realtime_stops:
            continue

        # Ja ha començat si tenim almenys una parada realtime.
        tren["started"] = True

        # Ordenem segons l'ordre original del recorregut.
        # L'última parada amb realtime és la més avançada.
        ultima = valid_realtime_stops[-1]

        delay_final = ultima.get("delay_minutes")

        if delay_final is not None:
            try:
                tren["final_delay_minutes"] = int(round(float(delay_final)))
            except Exception:
                tren["final_delay_minutes"] = 0

        # ----------------------------------------------------
        # ARRIBAT
        # ----------------------------------------------------

        stops = tren.get("stops", [])

        if stops:

            ultim_stop = stops[-1]

            ultim_stop_id = normalitzar_text(
                ultim_stop.get("stop_id")
            )

            # Només considerem arribat si tenim realtime
            # coherent de la seva última parada.
            if ultim_stop_id in stops_antics:

                antic_ultim = stops_antics[ultim_stop_id]

                if realtime_es_coherent(
                    ultim_stop,
                    antic_ultim
                ):
                    tren["arrived"] = True

    print(
        f"♻️ Realtime anterior: "
        f"{conservats} parades conservades, "
        f"{descartats} parades descartades"
    )


# ============================================================
# DESCARREGAR GTFS
# ============================================================

def descarregar_gtfs():

    print("📥 Descarregant GTFS Renfe...")

    response = requests.get(
        GTFS_URL,
        timeout=60
    )

    response.raise_for_status()

    print(
        f"✅ GTFS descarregat: "
        f"{len(response.content)} bytes"
    )

    return zipfile.ZipFile(
        io.BytesIO(response.content)
    )


# ============================================================
# GENERAR DADES
# ============================================================

def generar_dades():

    avui = datetime.now(TZ).date()

    data_str = avui.isoformat()

    data_path = os.path.join(
        DATA_DIR,
        f"{data_str}.json"
    )

    print()
    print("======================================")
    print("🚆 COLLECT R15")
    print("======================================")
    print(f"📅 Data: {data_str}")
    print()

    # --------------------------------------------------------
    # JSON ANTIC
    # --------------------------------------------------------

    dades_anteriors = carregar_json_anterior(
        data_path
    )

    if dades_anteriors:
        print(
            f"♻️ JSON anterior trobat: {data_path}"
        )
    else:
        print("ℹ️ No hi ha JSON anterior")

    # --------------------------------------------------------
    # GTFS
    # --------------------------------------------------------

    z = descarregar_gtfs()

    routes = carregar_csv(
        z,
        "routes.txt"
    )

    trips = carregar_csv(
        z,
        "trips.txt"
    )

    stop_times = carregar_csv(
        z,
        "stop_times.txt"
    )

    stops = carregar_csv(
        z,
        "stops.txt"
    )

    calendar = carregar_csv(
        z,
        "calendar.txt"
    )

    print()
    print(f"Routes: {len(routes)}")
    print(f"Trips: {len(trips)}")
    print(f"Stop times: {len(stop_times)}")
    print(f"Stops: {len(stops)}")
    print(f"Calendar: {len(calendar)}")
    print()

    # --------------------------------------------------------
    # DICCIONARIS
    # --------------------------------------------------------

    stops_by_id = {
        normalitzar_text(s.get("stop_id")): s
        for s in stops
    }

    trips_by_id = {
        normalitzar_text(t.get("trip_id")): t
        for t in trips
    }

    # --------------------------------------------------------
    # SERVEIS ACTIUS AVUI
    # --------------------------------------------------------

    weekday = avui.weekday()

    weekday_fields = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday"
    ]

    weekday_field = weekday_fields[weekday]

    serveis_valids = set()

    for cal in calendar:

        start = normalitzar_text(
            cal.get("start_date")
        )

        end = normalitzar_text(
            cal.get("end_date")
        )

        if not start or not end:
            continue

        if not (start <= data_str <= end):
            continue

        if normalitzar_text(
            cal.get(weekday_field)
        ) != "1":
            continue

        service_id = normalitzar_text(
            cal.get("service_id")
        )

        if service_id:
            serveis_valids.add(service_id)

    print(
        f"📆 Serveis vàlids avui: "
        f"{len(serveis_valids)}"
    )

    # --------------------------------------------------------
    # TRIPS R15
    # --------------------------------------------------------

    trips_r15 = []

    for trip in trips:

        route_id = normalitzar_text(
            trip.get("route_id")
        )

        trip_id = normalitzar_text(
            trip.get("trip_id")
        )

        service_id = normalitzar_text(
            trip.get("service_id")
        )

        if not trip_id:
            continue

        # R15
        route = next(
            (
                r
                for r in routes
                if normalitzar_text(
                    r.get("route_id")
                ) == route_id
            ),
            None
        )

        if not route:
            continue

        route_short_name = normalitzar_text(
            route.get("route_short_name")
        )

        route_long_name = normalitzar_text(
            route.get("route_long_name")
        )

        if (
            route_short_name != "R15"
            and "R15" not in route_long_name
        ):
            continue

        if service_id not in serveis_valids:
            continue

        trips_r15.append(trip)

    print(
        f"🚆 Trips R15 avui: "
        f"{len(trips_r15)}"
    )

    # --------------------------------------------------------
    # STOP TIMES AGRUPATS
    # --------------------------------------------------------

    stop_times_by_trip = {}

    for st in stop_times:

        trip_id = normalitzar_text(
            st.get("trip_id")
        )

        if not trip_id:
            continue

        if trip_id not in stop_times_by_trip:
            stop_times_by_trip[trip_id] = []

        stop_times_by_trip[trip_id].append(st)

    # --------------------------------------------------------
    # GENERAR CIRCULACIONS
    # --------------------------------------------------------

    circulacions = []

    for trip in trips_r15:

        trip_id = normalitzar_text(
            trip.get("trip_id")
        )

        trip_stop_times = stop_times_by_trip.get(
            trip_id,
            []
        )

        if not trip_stop_times:
            continue

        # Ordenem per stop_sequence
        trip_stop_times.sort(
            key=lambda x: int(
                x.get("stop_sequence", "0")
                or "0"
            )
        )

        stops_tren = []

        for st in trip_stop_times:

            stop_id = normalitzar_text(
                st.get("stop_id")
            )

            stop = stops_by_id.get(stop_id)

            if not stop:
                continue

            arrival = minuts_des_de_mitjanit(
                st.get("arrival_time")
            )

            departure = minuts_des_de_mitjanit(
                st.get("departure_time")
            )

            if arrival is None and departure is None:
                continue

            theoretical = arrival

            if theoretical is None:
                theoretical = departure

            stop_data = {
                "station": normalitzar_text(
                    stop.get("stop_name")
                ),
                "stop_id": stop_id,
                "scheduled_arrival": arrival,
                "scheduled_departure": departure,
                "actual_minutes": None,
                "actual_time": None,
                "delay_minutes": None
            }

            stops_tren.append(
                stop_data
            )

        if not stops_tren:
            continue

        # ----------------------------------------------------
        # DIRECCIÓ
        # ----------------------------------------------------

        first_station = stops_tren[0]["station"]
        last_station = stops_tren[-1]["station"]

        direction = ""

        if "Barcelona" in last_station:
            direction = "Barcelona"

        elif "Reus" in last_station:
            direction = "Reus"

        else:
            direction = last_station

        circulacio = {
            "train_id": trip_id,
            "trip_id": trip_id,
            "route_id": normalitzar_text(
                trip.get("route_id")
            ),
            "direction": direction,
            "started": False,
            "arrived": False,
            "final_delay_minutes": 0,
            "stops": stops_tren
        }

        circulacions.append(
            circulacio
        )

    # --------------------------------------------------------
    # ORDENAR TRENS
    # --------------------------------------------------------

    def hora_sort(tren):

        stops = tren.get("stops", [])

        if not stops:
            return 9999

        value = stops[0].get(
            "scheduled_departure"
        )

        if value is None:
            value = stops[0].get(
                "scheduled_arrival"
            )

        if value is None:
            return 9999

        return value

    circulacions.sort(
        key=hora_sort
    )

    print(
        f"🚆 Circulacions generades: "
        f"{len(circulacions)}"
    )

    # ========================================================
    # CONSERVAR REALTIME ANTIC
    # ========================================================

    conservar_realtime_anterior(
        circulacions,
        dades_anteriors
    )

    # ========================================================
    # SORTIDA
    # ========================================================

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    dades = {
        "date": data_str,
        "generated_at": datetime.now(
            TZ
        ).isoformat(),
        "source": "Renfe GTFS",
        "trains": circulacions
    }

    with open(
        data_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            dades,
            f,
            ensure_ascii=False,
            indent=2
        )

    print()
    print(
        f"💾 Guardat: {data_path}"
    )

    print(
        f"🚆 Trens: {len(circulacions)}"
    )

    print()
    print("✅ COLLECT FINALITZAT")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    generar_dades()
