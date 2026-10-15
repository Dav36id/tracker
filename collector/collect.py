import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


# ============================================================
# CONFIGURACIÓ
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

GTFS_RT_URL = "https://gtfsrt.renfe.com/trip_updates.json"
TIMEZONE = ZoneInfo("Europe/Madrid")
TIMEOUT = (10, 25)

# Diferència màxima per al matching intel·ligent.
MAX_TIME_DIFFERENCE_MINUTES = 10

# Evitem aplicar una mateixa actualització a diversos trens.
USED_FEED_IDS = set()


# ============================================================
# DATA I HORA
# ============================================================

def ara_local():
    return datetime.now(TIMEZONE)


def data_local():
    return ara_local().date().isoformat()


def minuts_a_hora(minuts):
    if minuts is None:
        return None

    minuts = int(round(float(minuts))) % 1440
    hores = minuts // 60
    minuts_restants = minuts % 60

    return f"{hores:02d}:{minuts_restants:02d}"


def timestamp_a_minuts(timestamp):
    if timestamp is None:
        return None

    try:
        instant = datetime.fromtimestamp(
            float(timestamp),
            tz=TIMEZONE
        )
        return instant.hour * 60 + instant.minute
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def minuts_desde_valor(valor):
    if valor is None or valor == "":
        return None

    try:
        if isinstance(valor, (int, float)):
            return int(round(valor))

        text = str(valor).strip()

        if text.isdigit() or (
            text.startswith("-") and text[1:].isdigit()
        ):
            return int(text)

        parts = text.split(":")

        if len(parts) >= 2:
            return int(parts[0]) * 60 + int(parts[1])

    except (ValueError, TypeError):
        pass

    return None


def diferencia_circular(a, b):
    """Diferència en minuts tenint en compte el canvi de dia."""
    if a is None or b is None:
        return None

    diferencia = abs(int(a) - int(b))
    return min(diferencia, 1440 - diferencia)


# ============================================================
# NORMALITZACIÓ
# ============================================================

def normalitzar_id(valor):
    if valor is None:
        return ""

    return str(valor).strip()


def obtenir_trip_id(update):
    trip = update.get("trip") or update.get("trip_descriptor") or {}

    return normalitzar_id(
        trip.get("trip_id")
        or trip.get("tripId")
        or trip.get("id")
    )


def obtenir_route_id(update):
    trip = update.get("trip") or update.get("trip_descriptor") or {}

    return normalitzar_id(
        trip.get("route_id")
        or trip.get("routeId")
    )


def obtenir_stop_id(stop):
    return normalitzar_id(
        stop.get("stop_id")
        or stop.get("stopId")
        or stop.get("station_id")
    )


def obtenir_stop_sequence(stop):
    try:
        value = stop.get("stop_sequence", stop.get("stopSequence"))

        if value is None:
            return None

        return int(value)
    except (ValueError, TypeError):
        return None


def obtenir_stop_updates(update):
    stops = (
        update.get("stop_time_update")
        or update.get("stopTimeUpdate")
        or update.get("stop_time_updates")
        or []
    )

    return stops if isinstance(stops, list) else []


# ============================================================
# LECTURA DE TEMPS GTFS-RT
# ============================================================

def obtenir_event(stop_update, event_name):
    event = (
        stop_update.get(event_name)
        or stop_update.get(
            "arrival" if event_name == "arrival_time" else "departure"
        )
        or {}
    )

    if not isinstance(event, dict):
        return {}

    return event


def obtenir_temps_event(stop_update, tipus):
    event = stop_update.get(tipus) or {}

    if not isinstance(event, dict):
        return None

    timestamp = event.get("time")

    if timestamp is not None:
        return timestamp_a_minuts(timestamp)

    return None


def obtenir_retard_event(stop_update, tipus):
    event = stop_update.get(tipus) or {}

    if not isinstance(event, dict):
        return None

    delay = event.get("delay")

    if delay is None:
        return None

    try:
        return int(round(float(delay) / 60))
    except (ValueError, TypeError):
        return None


def obtenir_retard_trip(update):
    trip = update.get("trip") or update.get("trip_descriptor") or {}

    # Alguns feeds poden incloure un retard general del viatge.
    for field in ("delay", "delay_seconds"):
        value = trip.get(field)

        if value is not None:
            try:
                return int(round(float(value) / 60))
            except (ValueError, TypeError):
                pass

    return None


# ============================================================
# MATCHING DE PARADES
# ============================================================

def indexar_parades(train):
    result = {}

    for index, stop in enumerate(train.get("stops", [])):
        stop_id = obtenir_stop_id(stop)
        sequence = obtenir_stop_sequence(stop)

        if stop_id:
            result.setdefault(stop_id, []).append(index)

        if sequence is not None:
            result.setdefault(f"SEQ:{sequence}", []).append(index)

    return result


def trobar_parada(train, feed_stop, index):
    stops = train.get("stops", [])
    stop_id = obtenir_stop_id(feed_stop)

    if stop_id:
        for i, stop in enumerate(stops):
            if obtenir_stop_id(stop) == stop_id:
                return i

    sequence = obtenir_stop_sequence(feed_stop)

    if sequence is not None:
        # Primer intent: coincidència de stop_sequence.
        for i, stop in enumerate(stops):
            if obtenir_stop_sequence(stop) == sequence:
                return i

        # Segon intent: la seqüència pot correspondre a l'índex.
        if 0 <= sequence < len(stops):
            return sequence

    return None


def obtenir_horari_parada(stop):
    for field in (
        "scheduled_arrival",
        "scheduled_departure",
        "arrival",
        "departure"
    ):
        value = minuts_desde_valor(stop.get(field))

        if value is not None:
            return value

    return None


def puntuacio_matching(train, feed_stops):
    """
    Calcula si les parades i els horaris del feed corresponen
    a una circulació programada.
    """
    stops = train.get("stops", [])

    if not stops or not feed_stops:
        return None

    coincidencies = 0
    diferencies = []

    for feed_stop in feed_stops:
        index = trobar_parada(train, feed_stop, None)

        if index is None:
            continue

        scheduled = obtenir_horari_parada(stops[index])

        arrival = obtenir_temps_event(feed_stop, "arrival")
        departure = obtenir_temps_event(feed_stop, "departure")
        actual = arrival if arrival is not None else departure

        delay = obtenir_retard_event(feed_stop, "arrival")

        if delay is None:
            delay = obtenir_retard_event(feed_stop, "departure")

        if scheduled is None:
            continue

        coincidencies += 1

        if actual is not None:
            expected = actual - (delay or 0)
            diff = diferencia_circular(scheduled, expected)
            if diff is not None:
                diferencies.append(diff)

    # Exigim diverses parades coincidents per evitar associacions dubtoses.
    if coincidencies < 2:
        return None

    if diferencies:
        mitjana = sum(diferencies) / len(diferencies)

        if mitjana > MAX_TIME_DIFFERENCE_MINUTES:
            return None

        return (coincidencies, mitjana)

    # Sense temps reals no podem confirmar l'associació només amb una parada.
    return (coincidencies, 0)


# ============================================================
# APLICAR ACTUALITZACIONS A LES PARADES
# ============================================================

def aplicar_actualitzacio_parada(train_stop, feed_stop):
    updated = False

    for event_name in ("arrival", "departure"):
        event = feed_stop.get(event_name) or {}

        if not isinstance(event, dict):
            continue

        actual = obtenir_temps_event(feed_stop, event_name)
        delay = obtenir_retard_event(feed_stop, event_name)

        if actual is not None:
            train_stop["actual_minutes"] = actual
            train_stop["actual_time"] = minuts_a_hora(actual)
            train_stop["realtime_source"] = "Renfe GTFS-RT"
            updated = True

        if delay is not None:
            train_stop["delay_minutes"] = delay
            train_stop["delay_seconds"] = delay * 60
            updated = True

    return updated


def aplicar_actualitzacio_tren(train, update, feed_id):
    feed_stops = obtenir_stop_updates(update)
    stops = train.get("stops", [])

    if not stops or not feed_stops:
        return 0

    actualitzades = 0

    for feed_stop in feed_stops:
        index = trobar_parada(train, feed_stop, None)

        if index is None or index >= len(stops):
            continue

        if aplicar_actualitzacio_parada(stops[index], feed_stop):
            actualitzades += 1

    if actualitzades:
        train["realtime_updated_at"] = ara_local().isoformat()
        train["realtime_source"] = "Renfe GTFS-RT"
        train["realtime_trip_id"] = obtenir_trip_id(update)

        trip_delay = obtenir_retard_trip(update)

        if trip_delay is not None:
            train["realtime_trip_delay_minutes"] = trip_delay
            train["final_delay_minutes"] = trip_delay
        else:
            # Si no hi ha retard general, utilitzem l'última parada
            # que dispose de retard, si n'hi ha.
            for stop in reversed(stops):
                delay = stop.get("delay_minutes")

                if delay is not None:
                    try:
                        train["final_delay_minutes"] = int(delay)
                        break
                    except (ValueError, TypeError):
                        pass

        train["realtime_updated"] = True

    return actualitzades


# ============================================================
# EXTRAURE ENTITATS DEL FEED
# ============================================================

def obtenir_trip_updates(feed):
    entities = feed.get("entity", feed.get("entities", []))

    if not isinstance(entities, list):
        return []

    result = []

    for entity in entities:
        update = (
            entity.get("trip_update")
            or entity.get("tripUpdate")
            or entity.get("trip_update_descriptor")
        )

        if isinstance(update, dict):
            entity_id = normalitzar_id(entity.get("id"))
            result.append((entity_id, update))

    return result


# ============================================================
# MATCHING DIRECTE I INTEL·LIGENT
# ============================================================

def actualitzar_trens(trains, updates):
    directes = 0
    intelligents = 0
    sense_match = 0
    parades_actualitzades = 0

    # Índex dels identificadors dels trens del JSON.
    by_train_id = {}

    for train in trains:
        for field in ("train_id", "trip_id", "id", "tripId"):
            value = normalitzar_id(train.get(field))

            if value:
                by_train_id.setdefault(value, []).append(train)

    used_trains = set()

    for feed_id, update in updates:
        trip_id = obtenir_trip_id(update)
        feed_stops = obtenir_stop_updates(update)

        candidates = by_train_id.get(trip_id, []) if trip_id else []

        train = next(
            (candidate for candidate in candidates
             if id(candidate) not in used_trains),
            None
        )

        # Matching directe: l'identificador del viatge coincideix.
        if train is not None:
            directes += 1
        else:
            # Matching intel·ligent: busquem coincidències de parades
            # i d'horaris, però només acceptem una associació clara.
            ranked = []

            for candidate in trains:
                if id(candidate) in used_trains:
                    continue

                score = puntuacio_matching(candidate, feed_stops)

                if score is not None:
                    ranked.append((score, candidate))

            ranked.sort(
                key=lambda item: (
                    -item[0][0],
                    item[0][1]
                )
            )

            if ranked:
                best_score, best_train = ranked[0]

                # Si el segon candidat té una puntuació pràcticament
                # igual, no associem el feed de manera arbitrària.
                ambiguous = (
                    len(ranked) > 1
                    and ranked[1][0][0] == best_score[0]
                    and abs(ranked[1][0][1] - best_score[1]) < 1
                )

                if ambiguous:
                    sense_match += 1
                    continue

                train = best_train
                intelligents += 1

        if train is None:
            sense_match += 1
            continue

        if feed_id and feed_id in USED_FEED_IDS:
            continue

        used_trains.add(id(train))

        if feed_id:
            USED_FEED_IDS.add(feed_id)

        count = aplicar_actualitzacio_tren(train, update, feed_id)
        parades_actualitzades += count

        if count == 0:
            # Si no s'ha pogut associar cap parada, no comptem
            # aquest tren com una actualització efectiva.
            sense_match += 1

    return {
        "directes": directes,
        "intelligents": intelligents,
        "sense_match": sense_match,
        "parades_actualitzades": parades_actualitzades
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 42)
    print("R15 REALTIME")
    print(f"Data local: {data_local()}")
    print("=" * 42)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Utilitzem la data de Catalunya, no la data UTC del runner.
    today = data_local()
    json_path = DATA_DIR / f"{today}.json"

    if not json_path.exists():
        print(f"ERROR: no existeix: {json_path.relative_to(BASE_DIR)}")

        available = sorted(DATA_DIR.glob("*.json"))

        if available:
            print("Fitxers disponibles:")
            for path in available[-5:]:
                print(f"  - {path.name}")

        sys.exit(1)

    try:
        with json_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"ERROR llegint el JSON de trens: {error}")
        sys.exit(1)

    trains = data.get("trains", data.get("circulations", []))

    if not isinstance(trains, list):
        print("ERROR: el JSON no conté una llista de trens vàlida.")
        sys.exit(1)

    print(f"Fitxer: {json_path.relative_to(BASE_DIR)}")
    print(f"Trens programats: {len(trains)}")

    try:
        response = requests.get(
            GTFS_RT_URL,
            timeout=TIMEOUT,
            headers={"User-Agent": "R15-Tracker/1.0"}
        )
        response.raise_for_status()
        feed = response.json()
    except requests.RequestException as error:
        print(f"ERROR descarregant el feed de Renfe: {error}")
        print("Es conserva el JSON programat sense modificar.")
        sys.exit(1)
    except ValueError as error:
        print(f"ERROR: el feed de Renfe no és JSON vàlid: {error}")
        sys.exit(1)

    updates = obtenir_trip_updates(feed)

    print(f"Actualitzacions del feed: {len(updates)}")

    stats = actualitzar_trens(trains, updates)

    # Actualitzem les dades de control sense eliminar els horaris.
    data["realtime_checked_at"] = ara_local().isoformat()
    data["realtime_feed_url"] = GTFS_RT_URL
    data["realtime_stats"] = stats

    try:
        with json_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except OSError as error:
        print(f"ERROR desant les dades: {error}")
        sys.exit(1)

    print("-" * 42)
    print(f"Matching directe: {stats['directes']}")
    print(f"Matching intel·ligent: {stats['intelligents']}")
    print(f"Sense correspondència: {stats['sense_match']}")
    print(f"Parades actualitzades: {stats['parades_actualitzades']}")
    print(f"Guardat: {json_path.relative_to(BASE_DIR)}")
    print("R15 REALTIME FINALITZAT")


if __name__ == "__main__":
    main()

