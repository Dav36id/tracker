import csv
import io
import json
import os
import time
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


# ============================================================
# CONFIGURACIÓ
# ============================================================

GTFS_URL = (
    "https://ssl.renfe.com/"
    "ftransit/Fichero_CER_FOMENTO/fomento_transit.zip"
)

DATA_DIR = "data"
TZ = ZoneInfo("Europe/Madrid")

MAX_REALTIME_ERROR_MINUTES = 5


# ============================================================
# UTILITATS
# ============================================================

def normalitzar_text(value):
    if value is None:
        return ""
    return str(value).strip()


def minuts_des_de_mitjanit(value):
    """Converteix HH:MM:SS en minuts, incloent hores superiors a 24."""
    value = normalitzar_text(value)

    if not value:
        return None

    try:
        parts = value.split(":")
        if len(parts) < 2:
            return None

        hour = int(parts[0])
        minute = int(parts[1])

        if hour < 0 or not 0 <= minute < 60:
            return None

        return hour * 60 + minute

    except (TypeError, ValueError):
        return None


def carregar_csv(z, nom, obligatori=True):
    """Llegeix un CSV del GTFS i neteja els espais."""
    noms = set(z.namelist())

    if nom not in noms:
        if obligatori:
            raise ValueError(
                f"El fitxer obligatori {nom} no existeix al GTFS."
            )

        print(f"ℹ️ {nom} no existeix; es continuarà sense aquest fitxer.")
        return []

    with z.open(nom) as f:
        text = io.TextIOWrapper(f, encoding="utf-8-sig")
        reader = csv.DictReader(text)

        files = []
        for row in reader:
            files.append({
                normalitzar_text(k): normalitzar_text(v)
                for k, v in row.items()
                if k is not None
            })

        return files


def carregar_json_anterior(path):
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            dades = json.load(f)

        if not isinstance(dades, dict):
            return None

        return dades

    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ No s'ha pogut llegir el JSON anterior: {e}")
        return None


# ============================================================
# DESCÀRREGA GTFS
# ============================================================

def descarregar_gtfs():
    print("📥 Descarregant GTFS Renfe...")

    for intent in range(1, 6):
        try:
            print(f"   Intent {intent}/5...")

            response = requests.get(
                GTFS_URL,
                timeout=60,
                headers={"User-Agent": "R15-Tracker/1.0"},
            )
            response.raise_for_status()

            contingut = response.content

            if not zipfile.is_zipfile(io.BytesIO(contingut)):
                raise ValueError("La resposta descarregada no és un ZIP vàlid.")

            print(f"✅ GTFS descarregat: {len(contingut)} bytes")
            return zipfile.ZipFile(io.BytesIO(contingut))

        except (
            requests.exceptions.RequestException,
            ValueError,
            zipfile.BadZipFile,
        ) as e:
            print(f"⚠️ Error descarregant GTFS: {e}")

            if intent < 5:
                espera = intent * 10
                print(f"   ⏳ Esperant {espera} segons...")
                time.sleep(espera)

    raise RuntimeError("No s'ha pogut descarregar un GTFS vàlid després de 5 intents.")


# ============================================================
# CALENDARI GTFS
# ============================================================

def obtenir_serveis_actius(calendar, calendar_dates, avui):
    """
    Retorna els service_id actius en la data indicada.

    calendar.txt utilitza dates YYYYMMDD.
    calendar_dates.txt afegeix o elimina serveis per a dates concretes:
      exception_type=1 -> afegir servei
      exception_type=2 -> eliminar servei
    """
    data_gtfs = avui.strftime("%Y%m%d")
    weekday_fields = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    weekday_field = weekday_fields[avui.weekday()]

    serveis = set()

    for cal in calendar:
        start = normalitzar_text(cal.get("start_date"))
        end = normalitzar_text(cal.get("end_date"))
        service_id = normalitzar_text(cal.get("service_id"))

        if not start or not end or not service_id:
            continue

        # Compare dates en el mateix format: YYYYMMDD.
        if start <= data_gtfs <= end:
            if normalitzar_text(cal.get(weekday_field)) == "1":
                serveis.add(service_id)

    afegits = 0
    eliminats = 0

    for excepcio in calendar_dates:
        data_excepcio = normalitzar_text(excepcio.get("date"))

        if data_excepcio != data_gtfs:
            continue

        service_id = normalitzar_text(excepcio.get("service_id"))
        tipus = normalitzar_text(excepcio.get("exception_type"))

        if not service_id:
            continue

        if tipus == "1":
            if service_id not in serveis:
                afegits += 1
            serveis.add(service_id)

        elif tipus == "2":
            if service_id in serveis:
                eliminats += 1
            serveis.discard(service_id)

    print(f"📆 Serveis vàlids avui: {len(serveis)}")
    print(f"   Excepcions que afegeixen serveis: {afegits}")
    print(f"   Excepcions que eliminen serveis: {eliminats}")

    return serveis


# ============================================================
# CONSERVAR TEMPS REAL ANTERIOR
# ============================================================

def realtime_es_coherent(stop_nou, stop_antic):
    if not isinstance(stop_antic, dict):
        return False

    actual = stop_antic.get("actual_minutes")
    delay = stop_antic.get("delay_minutes")

    if actual is None or delay is None:
        return False

    theoretical = stop_nou.get("scheduled_arrival")
    if theoretical is None:
        theoretical = stop_nou.get("scheduled_departure")

    if theoretical is None:
        return False

    try:
        actual = float(actual)
        delay = float(delay)
        theoretical = float(theoretical)
    except (TypeError, ValueError):
        return False

    diferencia = actual - theoretical
    return abs(diferencia - delay) <= MAX_REALTIME_ERROR_MINUTES


def conservar_realtime_anterior(circulacions, dades_anteriors):
    if not isinstance(dades_anteriors, dict):
        return

    trens_antics = {
        str(tren.get("train_id")): tren
        for tren in dades_anteriors.get("trains", [])
        if tren.get("train_id")
    }

    conservats = 0
    descartats = 0

    for tren in circulacions:
        antic = trens_antics.get(str(tren.get("train_id")))

        if not antic:
            continue

        stops_antics = {
            normalitzar_text(stop.get("stop_id")): stop
            for stop in antic.get("stops", [])
            if normalitzar_text(stop.get("stop_id"))
        }

        parades_realtime_valides = []

        for stop in tren.get("stops", []):
            stop_id = normalitzar_text(stop.get("stop_id"))
            antic_stop = stops_antics.get(stop_id)

            # Inicialitzem sempre els camps de temps real.
            stop["actual_minutes"] = None
            stop["actual_time"] = None
            stop["delay_minutes"] = None

            if not antic_stop:
                continue

            if not realtime_es_coherent(stop, antic_stop):
                if (
                    antic_stop.get("actual_minutes") is not None
                    or antic_stop.get("delay_minutes") is not None
                ):
                    descartats += 1
                continue

            stop["actual_minutes"] = antic_stop.get("actual_minutes")
            stop["actual_time"] = antic_stop.get("actual_time")
            stop["delay_minutes"] = antic_stop.get("delay_minutes")

            for camp in ("realtime_delay_minutes", "delay_seconds"):
                if antic_stop.get(camp) is not None:
                    stop[camp] = antic_stop[camp]

            parades_realtime_valides.append(stop)
            conservats += 1

        tren["started"] = bool(parades_realtime_valides)
        tren["arrived"] = False
        tren["final_delay_minutes"] = 0

        if parades_realtime_valides:
            delay_final = parades_realtime_valides[-1].get("delay_minutes")

            if delay_final is not None:
                try:
                    tren["final_delay_minutes"] = int(round(float(delay_final)))
                except (TypeError, ValueError):
                    pass

        if tren.get("stops"):
            ultim_stop = tren["stops"][-1]
            ultim_id = normalitzar_text(ultim_stop.get("stop_id"))
            antic_ultim = stops_antics.get(ultim_id)

            if (
                antic_ultim
                and realtime_es_coherent(ultim_stop, antic_ultim)
                and antic_ultim.get("actual_minutes") is not None
            ):
                tren["arrived"] = True

    print("♻️ Temps real anterior:")
    print(f"   Parades conservades: {conservats}")
    print(f"   Parades descartades: {descartats}")


# ============================================================
# GENERAR DADES
# ============================================================

def generar_dades():
    avui = datetime.now(TZ).date()
    data_str = avui.isoformat()
    data_path = os.path.join(DATA_DIR, f"{data_str}.json")

    print("=" * 38)
    print("🚆 COLLECT R15")
    print("=" * 38)
    print(f"📅 Data: {data_str}")

    dades_anteriors = carregar_json_anterior(data_path)

    if dades_anteriors:
        print(f"♻️ JSON anterior trobat: {data_path}")
    else:
        print("ℹ️ No hi ha JSON anterior")

    z = descarregar_gtfs()

    with z:
        routes = carregar_csv(z, "routes.txt")
        trips = carregar_csv(z, "trips.txt")
        stop_times = carregar_csv(z, "stop_times.txt")
        stops = carregar_csv(z, "stops.txt")
        calendar = carregar_csv(z, "calendar.txt", obligatori=False)
        calendar_dates = carregar_csv(
            z, "calendar_dates.txt", obligatori=False
        )

    print()
    print(f"Routes: {len(routes)}")
    print(f"Trips: {len(trips)}")
    print(f"Stop times: {len(stop_times)}")
    print(f"Stops: {len(stops)}")
    print(f"Calendar: {len(calendar)}")
    print(f"Calendar dates: {len(calendar_dates)}")

    serveis_actius = obtenir_serveis_actius(
        calendar, calendar_dates, avui
    )

    routes_by_id = {
        normalitzar_text(route.get("route_id")): route
        for route in routes
        if normalitzar_text(route.get("route_id"))
    }

    stops_by_id = {
        normalitzar_text(stop.get("stop_id")): stop
        for stop in stops
        if normalitzar_text(stop.get("stop_id"))
    }

    stop_times_by_trip = {}

    for st in stop_times:
        trip_id = normalitzar_text(st.get("trip_id"))
        if trip_id:
            stop_times_by_trip.setdefault(trip_id, []).append(st)

    trips_r15 = []

    for trip in trips:
        trip_id = normalitzar_text(trip.get("trip_id"))
        route_id = normalitzar_text(trip.get("route_id"))
        service_id = normalitzar_text(trip.get("service_id"))

        if not trip_id or service_id not in serveis_actius:
            continue

        route = routes_by_id.get(route_id)
        if not route:
            continue

        short_name = normalitzar_text(route.get("route_short_name")).upper()
        long_name = normalitzar_text(route.get("route_long_name")).upper()

        # Identificació de la línia a partir de la informació de routes.txt.
        if short_name != "R15" and "R15" not in long_name:
            continue

        trips_r15.append(trip)

    print(f"🚆 Trips R15 avui: {len(trips_r15)}")

    circulacions = []

    for trip in trips_r15:
        trip_id = normalitzar_text(trip.get("trip_id"))
        trip_stop_times = stop_times_by_trip.get(trip_id, [])

        if not trip_stop_times:
            continue

        def ordre_parada(st):
            try:
                return int(st.get("stop_sequence") or 0)
            except ValueError:
                return 0

        trip_stop_times = sorted(trip_stop_times, key=ordre_parada)
        stops_tren = []

        for st in trip_stop_times:
            stop_id = normalitzar_text(st.get("stop_id"))
            stop = stops_by_id.get(stop_id)

            if not stop:
                continue

            arrival = minuts_des_de_mitjanit(st.get("arrival_time"))
            departure = minuts_des_de_mitjanit(st.get("departure_time"))

            if arrival is None and departure is None:
                continue

            stops_tren.append({
                "station": normalitzar_text(stop.get("stop_name")),
                "stop_id": stop_id,
                "scheduled_arrival": arrival,
                "scheduled_departure": departure,
                "actual_minutes": None,
                "actual_time": None,
                "delay_minutes": None,
            })

        if not stops_tren:
            continue

        first_station = stops_tren[0]["station"]
        last_station = stops_tren[-1]["station"]

        if "BARCELONA" in last_station.upper():
            direction = "Barcelona"
        elif "REUS" in last_station.upper():
            direction = "Reus"
        else:
            direction = last_station

        circulacions.append({
            "train_id": trip_id,
            "trip_id": trip_id,
            "route_id": normalitzar_text(trip.get("route_id")),
            "direction": direction,
            "started": False,
            "arrived": False,
            "final_delay_minutes": 0,
            "stops": stops_tren,
        })

    def hora_sort(tren):
        stops = tren.get("stops", [])
        if not stops:
            return 999999

        value = stops[0].get("scheduled_departure")
        if value is None:
            value = stops[0].get("scheduled_arrival")

        return value if value is not None else 999999

    circulacions.sort(key=hora_sort)

    print(f"🚆 Circulacions generades: {len(circulacions)}")

    # No sobreescrivim les dades del dia amb un fitxer buit.
    # Això també fa visible un possible canvi d'estructura del GTFS.
    if not circulacions:
        raise RuntimeError(
            "No s'ha trobat cap circulació de l'R15 per a hui. "
            "No s'ha modificat el JSON existent. "
            "Cal revisar els identificadors de ruta i els calendaris del GTFS."
        )

    conservar_realtime_anterior(circulacions, dades_anteriors)

    os.makedirs(DATA_DIR, exist_ok=True)

    dades = {
        "date": data_str,
        "generated_at": datetime.now(TZ).isoformat(),
        "source": "Renfe GTFS",
        "trains": circulacions,
    }

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(dades, f, ensure_ascii=False, indent=2)

    print(f"💾 Guardat: {data_path}")
    print(f"🚆 Trens: {len(circulacions)}")
    print("✅ COLLECT FINALITZAT")


if __name__ == "__main__":
    generar_dades()

