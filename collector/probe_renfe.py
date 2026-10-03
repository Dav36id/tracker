import requests
import json


# ============================================================
# CONFIGURACIÓ
# ============================================================

FEEDS = {
    "TRIP UPDATES": "https://gtfsrt.renfe.com/trip_updates.json",
    "VEHICLE POSITIONS": "https://gtfsrt.renfe.com/vehicle_positions.json",
    "ALERTS": "https://gtfsrt.renfe.com/alerts.json",
}


HEADERS = {
    "User-Agent": "R15-Tracker/1.0"
}


# ============================================================
# FUNCIÓ PER DESCARREGAR FEED
# ============================================================

def descarregar_feed(
    nom,
    url
):

    print()
    print()
    print("==========================================")
    print(nom)
    print("==========================================")
    print("URL:", url)
    print()

    try:

        response = requests.get(
            url,
            timeout=30,
            headers=HEADERS
        )

        print(
            "HTTP:",
            response.status_code
        )

        response.raise_for_status()

        dades = response.json()

        return dades

    except Exception as e:

        print(
            "ERROR:",
            repr(e)
        )

        return None


# ============================================================
# TRIP UPDATES
# ============================================================

trip_feed = descarregar_feed(
    "TRIP UPDATES",
    FEEDS["TRIP UPDATES"]
)


if trip_feed is not None:

    entities = trip_feed.get(
        "entity",
        []
    )

    print(
        "Entitats:",
        len(entities)
    )

    print()
    print("TRIPS TROBATS:")

    total = 0

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

        trip_id = trip.get(
            "tripId"
        )

        route_id = trip.get(
            "routeId"
        )

        schedule_relationship = trip.get(
            "scheduleRelationship"
        )

        print(
            "tripId:",
            repr(trip_id),
            "| routeId:",
            repr(route_id),
            "| estat:",
            repr(schedule_relationship)
        )

        total += 1

    print()
    print(
        "Trip updates trobats:",
        total
    )


# ============================================================
# VEHICLE POSITIONS
# ============================================================

vehicle_feed = descarregar_feed(
    "VEHICLE POSITIONS",
    FEEDS["VEHICLE POSITIONS"]
)


if vehicle_feed is not None:

    entities = vehicle_feed.get(
        "entity",
        []
    )

    print(
        "Entitats:",
        len(entities)
    )

    print()
    print("VEHICLES TROBATS:")

    total = 0


    for entity in entities:

        vehicle = entity.get(
            "vehicle"
        )

        if not vehicle:
            continue


        trip = vehicle.get(
            "trip",
            {}
        )


        vehicle_info = vehicle.get(
            "vehicle",
            {}
        )


        trip_id = trip.get(
            "tripId"
        )


        route_id = trip.get(
            "routeId"
        )


        vehicle_id = vehicle_info.get(
            "id"
        )


        label = vehicle_info.get(
            "label"
        )


        latitude = vehicle.get(
            "position",
            {}
        ).get(
            "latitude"
        )


        longitude = vehicle.get(
            "position",
            {}
        ).get(
            "longitude"
        )


        print(
            "tripId:",
            repr(trip_id),
            "| routeId:",
            repr(route_id),
            "| vehicle:",
            repr(vehicle_id),
            "| label:",
            repr(label),
            "| pos:",
            latitude,
            longitude
        )


        total += 1


    print()
    print(
        "Vehicles trobats:",
        total
    )


# ============================================================
# ALERTS
# ============================================================

alert_feed = descarregar_feed(
    "ALERTS",
    FEEDS["ALERTS"]
)


if alert_feed is not None:

    entities = alert_feed.get(
        "entity",
        []
    )

    print(
        "Entitats:",
        len(entities)
    )

    print()
    print("ALERTES TROBADES:")

    total = 0


    for entity in entities:

        alert = entity.get(
            "alert"
        )

        if not alert:
            continue


        informed_entities = alert.get(
            "informedEntity",
            []
        )


        header_text = alert.get(
            "headerText",
            {}
        )


        translation = header_text.get(
            "translation",
            []
        )


        text = ""


        if translation:

            first = translation[0]

            text = first.get(
                "text",
                ""
            )


        print()
        print(
            "ALERTA:"
        )

        print(
            "Text:",
            text
        )


        for informed in informed_entities:

            print(
                "  routeId:",
                repr(
                    informed.get(
                        "routeId"
                    )
                ),
                "| tripId:",
                repr(
                    informed.get(
                        "trip",
                        {}
                    ).get(
                        "tripId"
                    )
                ),
                "| stopId:",
                repr(
                    informed.get(
                        "stopId"
                    )
                )
            )


        total += 1


    print()
    print(
        "Alertes trobades:",
        total
    )


# ============================================================
# FINAL
# ============================================================

print()
print()
print("==========================================")
print("INVESTIGACIÓ FINALITZADA")
print("==========================================")
