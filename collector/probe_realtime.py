import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo


TRIP_UPDATES_URL = "https://gtfsrt.renfe.com/trip_updates.json"
VEHICLE_POSITIONS_URL = "https://gtfsrt.renfe.com/vehicle_positions.json"
ALERTS_URL = "https://gtfsrt.renfe.com/alerts.json"

TIMEZONE = ZoneInfo("Europe/Madrid")


def descarregar(url):
    print(f"\nDescarregant:")
    print(url)

    r = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "R15-Tracker/1.0"
        }
    )

    r.raise_for_status()

    print(f"OK - {len(r.content):,} bytes")

    return r.json()


def epoch_a_hora(epoch):
    if not epoch:
        return "-"

    try:
        dt = datetime.fromtimestamp(
            int(epoch),
            tz=TIMEZONE
        )

        return dt.strftime("%H:%M:%S")

    except Exception:
        return str(epoch)


def analitzar_trip_updates(data):

    entities = data.get("entity", [])

    print("\n")
    print("=" * 70)
    print("TRIP UPDATES")
    print("=" * 70)

    print(f"Entitats: {len(entities)}")

    trip_ids = []

    for entity in entities:

        tu = entity.get("tripUpdate", {})

        trip = tu.get("trip", {})

        trip_id = trip.get("tripId")

        if not trip_id:
            continue

        trip_ids.append(trip_id)

    print(f"Trips amb trip_id: {len(trip_ids)}")

    print("\nPrimers 30 trip_id:")

    for trip_id in trip_ids[:30]:
        print(f"  {trip_id}")

    print("\nTrips que semblen R15:")

    r15 = []

    for trip_id in trip_ids:

        if "R15" in trip_id.upper():
            r15.append(trip_id)

    if r15:
        for trip_id in r15:
            print(f"  {trip_id}")
    else:
        print("  CAP amb text R15")

    return trip_ids


def analitzar_vehicle_positions(data):

    entities = data.get("entity", [])

    print("\n")
    print("=" * 70)
    print("VEHICLE POSITIONS")
    print("=" * 70)

    print(f"Entitats: {len(entities)}")

    if not entities:
        print("\n⚠️ NO HI HA VEHICLES AL FEED")
        print("Això és important: caldrà comprovar si Renfe està")
        print("retornant temporalment un feed buit.")

        return []

    resultats = []

    for entity in entities:

        vp = entity.get("vehicle", {})

        if not vp:
            continue

        trip = vp.get("trip", {})
        vehicle = vp.get("vehicle", {})
        position = vp.get("position", {})

        trip_id = trip.get("tripId")
        route_id = trip.get("routeId")

        vehicle_id = vehicle.get("id")
        vehicle_label = vehicle.get("label")

        latitude = position.get("latitude")
        longitude = position.get("longitude")

        current_stop_sequence = vp.get(
            "currentStopSequence"
        )

        stop_id = vp.get("stopId")

        current_status = vp.get(
            "currentStatus"
        )

        timestamp = vp.get("timestamp")

        item = {
            "trip_id": trip_id,
            "route_id": route_id,
            "vehicle_id": vehicle_id,
            "vehicle_label": vehicle_label,
            "latitude": latitude,
            "longitude": longitude,
            "current_stop_sequence": current_stop_sequence,
            "stop_id": stop_id,
            "current_status": current_status,
            "timestamp": timestamp
        }

        resultats.append(item)

    print(f"Vehicles amb informació: {len(resultats)}")

    print("\nPrimers 50 vehicles:")

    for item in resultats[:50]:

        print(
            f"\n"
            f"trip_id={item['trip_id']}\n"
            f"route_id={item['route_id']}\n"
            f"vehicle_id={item['vehicle_id']}\n"
            f"vehicle_label={item['vehicle_label']}\n"
            f"position={item['latitude']}, {item['longitude']}\n"
            f"stop_id={item['stop_id']}\n"
            f"stop_sequence={item['current_stop_sequence']}\n"
            f"status={item['current_status']}\n"
            f"time={epoch_a_hora(item['timestamp'])}"
        )

    print("\n")
    print("=" * 70)
    print("ROUTES DETECTADES")
    print("=" * 70)

    routes = {}

    for item in resultats:

        route = item["route_id"]

        if route is None:
            route = "(sense route_id)"

        routes.setdefault(route, 0)
        routes[route] += 1

    for route, count in sorted(
        routes.items(),
        key=lambda x: (-x[1], str(x[0]))
    ):
        print(f"{route}: {count} vehicles")

    print("\n")
    print("=" * 70)
    print("VEHICLES AMB R15 AL ID")
    print("=" * 70)

    r15 = []

    for item in resultats:

        text = " ".join(
            str(item.get(k) or "")
            for k in [
                "trip_id",
                "route_id",
                "vehicle_id",
                "vehicle_label"
            ]
        ).upper()

        if "R15" in text:

            r15.append(item)

            print(
                f"\n"
                f"trip_id={item['trip_id']}\n"
                f"route_id={item['route_id']}\n"
                f"vehicle_id={item['vehicle_id']}\n"
                f"vehicle_label={item['vehicle_label']}\n"
                f"stop_id={item['stop_id']}\n"
                f"position={item['latitude']}, {item['longitude']}"
            )

    if not r15:
        print("CAP vehicle conté literal R15")

    return resultats


def comparar_trips(trip_updates, vehicles):

    print("\n")
    print("=" * 70)
    print("COMPARACIÓ TRIP UPDATES ↔ VEHICLE POSITIONS")
    print("=" * 70)

    update_ids = set(trip_updates)

    vehicle_ids = set(
        item["trip_id"]
        for item in vehicles
        if item["trip_id"]
    )

    comuns = update_ids & vehicle_ids

    nomes_updates = update_ids - vehicle_ids

    nomes_vehicles = vehicle_ids - update_ids

    print(f"Trips a Trip Updates:       {len(update_ids)}")
    print(f"Trips a Vehicle Positions:  {len(vehicle_ids)}")
    print(f"Trips presents als dos:      {len(comuns)}")
    print(f"Només Trip Updates:          {len(nomes_updates)}")
    print(f"Només Vehicle Positions:     {len(nomes_vehicles)}")

    print("\n")
    print("TRIPS QUE APAREIXEN ALS DOS:")

    for trip_id in sorted(comuns)[:100]:
        print(f"  {trip_id}")


def analitzar_alerts(data):

    entities = data.get("entity", [])

    print("\n")
    print("=" * 70)
    print("ALERTS")
    print("=" * 70)

    print(f"Entitats: {len(entities)}")

    for entity in entities[:20]:

        alert = entity.get("alert", {})

        header_text = alert.get(
            "headerText",
            {}
        )

        translation = header_text.get(
            "translation",
            []
        )

        texts = []

        for t in translation:

            text = t.get("text")

            if text:
                texts.append(text)

        if texts:
            print(" - " + " | ".join(texts))


def main():

    print("=" * 70)
    print("RENFE REALTIME PROBE")
    print("=" * 70)

    print(
        "Hora local:",
        datetime.now(TIMEZONE).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    # ---------------------------------------------------------
    # TRIP UPDATES
    # ---------------------------------------------------------

    trip_data = descarregar(
        TRIP_UPDATES_URL
    )

    trip_ids = analitzar_trip_updates(
        trip_data
    )

    # ---------------------------------------------------------
    # VEHICLE POSITIONS
    # ---------------------------------------------------------

    vehicle_data = descarregar(
        VEHICLE_POSITIONS_URL
    )

    vehicles = analitzar_vehicle_positions(
        vehicle_data
    )

    # ---------------------------------------------------------
    # COMPARACIÓ
    # ---------------------------------------------------------

    comparar_trips(
        trip_ids,
        vehicles
    )

    # ---------------------------------------------------------
    # ALERTS
    # ---------------------------------------------------------

    alerts_data = descarregar(
        ALERTS_URL
    )

    analitzar_alerts(
        alerts_data
    )

    print("\n")
    print("=" * 70)
    print("FI DE LA INVESTIGACIÓ")
    print("=" * 70)


if __name__ == "__main__":
    main()
