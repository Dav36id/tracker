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

# Diferència màxima entre hora teòrica i realtime
# per considerar una coincidència.
MAX_MATCH_MINUTES = 10

# Diferència màxima permesa entre:
#
#   hora realtime - hora teòrica
#
# i
#
#   retard declarat pel feed
#
MAX_DELAY_DIFFERENCE_MINUTES = 5

# Nombre MÍNIM de parades coincidents necessàries
# per acceptar un matching intel·ligent.
MIN_MATCHING_STOPS = 2


# ============================================================
# UTILITATS
# ============================================================

def convertir_timestamp(timestamp):

    try:

        return datetime.fromtimestamp(
            int(timestamp),
            tz=timezone.utc
        ).astimezone(TZ)

    except Exception:

        return None


def minuts_des_de_mitjanit(dt):

    return (
        dt.hour * 60
        + dt.minute
    )


def normalitzar_id(valor):

    if valor is None:
        return ""

    return str(valor).strip()


def format_minutes(minutes):

    if minutes is None:
        return "--:--"

    minutes = int(minutes)

    # Per si hi ha horaris després de mitjanit
    minutes = minutes % (24 * 60)

    hores = minutes // 60
    minuts = minutes % 60

    return f"{hores:02d}:{minuts:02d}"


# ============================================================
# CARREGAR JSON DEL DIA
# ============================================================

def carregar_json_avui():

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
# DESCARREGAR REALTIME
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
            trip.get(
                "tripId"
            )
        )

        if not trip_id:
            continue

        relationship = trip.get(
            "scheduleRelationship"
        )

        # ----------------------------------------------------
        # Informació addicional del TripDescriptor
        # ----------------------------------------------------

        route_id = normalitzar_id(
            trip.get(
                "routeId"
            )
        )

        direction_id = trip.get(
            "directionId"
        )

        start_time = normalitzar_id(
            trip.get(
                "startTime"
            )
        )

        start_date = normalitzar_id(
            trip.get(
                "startDate"
            )
        )

        stop_updates = []

        for stop_update in trip_update.get(
            "stopTimeUpdate",
            []
        ):

            stop_id = normalitzar_id(
                stop_update.get(
                    "stopId"
                )
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
                or
                departure.get("time")
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

                "stop_id":
                    stop_id,

                "datetime":
                    dt,

                "minutes":
                    minuts_des_de_mitjanit(
                        dt
                    ),

                "delay_seconds":
                    int(
                        delay_seconds
                    )
                    if delay_seconds is not None
                    else 0

            })

        resultat.append({

            "trip_id":
                trip_id,

            "relationship":
                relationship,

            "route_id":
                route_id,

            "direction_id":
                direction_id,

            "start_time":
                start_time,

            "start_date":
                start_date,

            "stops":
                stop_updates

        })

    return resultat


# ============================================================
# INDEXAR REALTIME PER STOP
# ============================================================

def crear_index_stop(
    trips_realtime
):

    index = {}

    for trip in trips_realtime:

        trip_id = trip[
            "trip_id"
        ]

        for stop in trip[
            "stops"
        ]:

            stop_id = stop[
                "stop_id"
            ]

            if stop_id not in index:

                index[
                    stop_id
                ] = []

            index[
                stop_id
            ].append({

                "trip_id":
                    trip_id,

                "minutes":
                    stop[
                        "minutes"
                    ],

                "datetime":
                    stop[
                        "datetime"
                    ],

                "delay_seconds":
                    stop[
                        "delay_seconds"
                    ],

                "relationship":
                    trip[
                        "relationship"
                    ],

                "route_id":
                    trip[
                        "route_id"
                    ],

                "direction_id":
                    trip[
                        "direction_id"
                    ],

                "start_time":
                    trip[
                        "start_time"
                    ],

                "start_date":
                    trip[
                        "start_date"
                    ]

            })

    return index


# ============================================================
# HORA TEÒRICA
# ============================================================

def hora_teorica_parada(
    stop
):

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

        return int(
            valor
        )

    except Exception:

        return None


# ============================================================
# MATCHING DIRECTE
# ============================================================

def buscar_matching_directe(
    train,
    realtime_by_id
):

    train_id = normalitzar_id(
        train.get(
            "train_id"
        )
    )

    if not train_id:
        return None

    return realtime_by_id.get(
        train_id
    )


# ============================================================
# MATCHING INTEL·LIGENT
#
# REQUISIT IMPORTANT:
#
# El mateix trip realtime ha de coincidir amb
# COM A MÍNIM 2 PARADES del tren estàtic.
#
# Això evita falsos positius provocats per una sola
# parada amb una hora semblant.
# ============================================================

def buscar_matching_intelligent(
    train,
    index_stop,
    used_trip_ids
):

    train_id = normalitzar_id(
        train.get(
            "train_id"
        )
    )

    candidats_tren = {}

    stops = train.get(
        "stops",
        []
    )

    # --------------------------------------------------------
    # Buscar candidats
    # --------------------------------------------------------

    for static_stop in stops:

        stop_id = normalitzar_id(
            static_stop.get(
                "stop_id"
            )
        )

        if not stop_id:
            continue

        hora_teorica = (
            hora_teorica_parada(
                static_stop
            )
        )

        if hora_teorica is None:
            continue

        candidats = index_stop.get(
            stop_id,
            []
        )

        for candidat in candidats:

            trip_id = candidat[
                "trip_id"
            ]

            if trip_id in used_trip_ids:
                continue

            hora_real = candidat[
                "minutes"
            ]

            diferencia = (
                hora_real
                - hora_teorica
            )

            # ------------------------------------------------
            # LIMITACIÓ TEMPORAL
            # ------------------------------------------------

            if abs(
                diferencia
            ) > MAX_MATCH_MINUTES:

                continue

            delay_minutes = (
                candidat[
                    "delay_seconds"
                ] / 60
            )

            # ------------------------------------------------
            # COHERÈNCIA DEL RETARD
            # ------------------------------------------------

            diferencia_delay = abs(
                diferencia
                - delay_minutes
            )

            if (
                diferencia_delay
                > MAX_DELAY_DIFFERENCE_MINUTES
            ):

                continue

            # ------------------------------------------------
            # Guardar coincidència
            # ------------------------------------------------

            if trip_id not in candidats_tren:

                candidats_tren[
                    trip_id
                ] = []

            candidats_tren[
                trip_id
            ].append({

                "static_stop":
                    static_stop,

                "realtime_stop":
                    candidat,

                "diferencia":
                    diferencia,

                "diferencia_delay":
                    diferencia_delay

            })

    # --------------------------------------------------------
    # LOG DE CANDIDATS
    # --------------------------------------------------------

    if candidats_tren:

        print()
        print(
            "------------------------------------------"
        )

        print(
            "CANDIDATS PER AL TREN:",
            train_id
        )

        print(
            "------------------------------------------"
        )

        for trip_id, coincidencies in (
            candidats_tren.items()
        ):

            print(
                "  RT:",
                trip_id
            )

            print(
                "     Coincidències:",
                len(coincidencies)
            )

            for coincidencia in coincidencies:

                static_stop = (
                    coincidencia[
                        "static_stop"
                    ]
                )

                realtime_stop = (
                    coincidencia[
                        "realtime_stop"
                    ]
                )

                stop_id = normalitzar_id(
                    static_stop.get(
                        "stop_id"
                    )
                )

                theoretical = (
                    hora_teorica_parada(
                        static_stop
                    )
                )

                real = realtime_stop.get(
                    "minutes"
                )

                delay = (
                    realtime_stop.get(
                        "delay_seconds",
                        0
                    )
                    / 60
                )

                diferencia = (
                    coincidencia[
                        "diferencia"
                    ]
                )

                print(
                    "     - stop:",
                    stop_id,
                    "| teòrica:",
                    format_minutes(
                        theoretical
                    ),
                    "| real:",
                    format_minutes(
                        real
                    ),
                    "| diferència:",
                    f"{diferencia:+.1f} min",
                    "| feed:",
                    f"{delay:+.1f} min"
                )

    # --------------------------------------------------------
    # Si no hi ha candidats
    # --------------------------------------------------------

    if not candidats_tren:

        return None

    # --------------------------------------------------------
    # ELIMINAR CANDIDATS AMB NOMÉS 1 COINCIDÈNCIA
    # --------------------------------------------------------

    candidats_valids = {}

    for trip_id, coincidencies in (
        candidats_tren.items()
    ):

        nombre_coincidencies = len(
            coincidencies
        )

        if (
            nombre_coincidencies
            < MIN_MATCHING_STOPS
        ):

            print(
                "  DESCARTAT:",
                trip_id,
                "| només",
                nombre_coincidencies,
                "coincidència/es"
            )

            continue

        candidats_valids[
            trip_id
        ] = coincidencies

    # --------------------------------------------------------
    # Si cap candidat té 2 o més parades
    # --------------------------------------------------------

    if not candidats_valids:

        print(
            "  Cap candidat té",
            MIN_MATCHING_STOPS,
            "coincidències."
        )

        return None

    # --------------------------------------------------------
    # PUNTUAR CANDIDATS
    # --------------------------------------------------------

    millor = None
    millor_puntuacio = None

    for trip_id, coincidencies in (
        candidats_valids.items()
    ):

        nombre_coincidencies = len(
            coincidencies
        )

        suma_diferencies = sum(
            abs(
                c["diferencia"]
            )
            for c in coincidencies
        )

        suma_incoherencia = sum(
            c[
                "diferencia_delay"
            ]
            for c in coincidencies
        )

        # Com més coincidències millor.
        #
        # Com menys diferència millor.
        #
        # Com menys incoherència millor.

        puntuacio = (

            suma_diferencies

            +

            suma_incoherencia * 0.5

            -

            nombre_coincidencies * 8

        )

        print(
            "  VALID:",
            trip_id,
            "| coincidències:",
            nombre_coincidencies,
            "| score:",
            round(
                puntuacio,
                2
            )
        )

        if (
            millor is None
            or
            puntuacio
            < millor_puntuacio
        ):

            millor_coincidencia = min(
                coincidencies,
                key=lambda c:
                    (
                        abs(
                            c[
                                "diferencia"
                            ]
                        )
                        +
                        c[
                            "diferencia_delay"
                        ]
                        * 0.5
                    )
            )

            millor = {

                "trip_id":
                    trip_id,

                "static_stop":
                    millor_coincidencia[
                        "static_stop"
                    ],

                "realtime_stop":
                    millor_coincidencia[
                        "realtime_stop"
                    ],

                "coincidencies":
                    nombre_coincidencies,

                "score":
                    puntuacio

            }

            millor_puntuacio = (
                puntuacio
            )

    # --------------------------------------------------------
    # RESULTAT
    # --------------------------------------------------------

    if millor:

        print(
            "  >>> MILLOR CANDIDAT:",
            millor[
                "trip_id"
            ],
            "|",
            "coincidències:",
            millor[
                "coincidencies"
            ],
            "| score:",
            round(
                millor[
                    "score"
                ],
                2
            )
        )

    return millor


# ============================================================
# APLICAR REALTIME
# ============================================================

def aplicar_realtime(
    static_stop,
    realtime_stop
):

    delay_seconds = (
        realtime_stop.get(
            "delay_seconds",
            0
        )
    )

    delay_minutes = round(
        delay_seconds / 60
    )

    actual_minutes = (
        realtime_stop.get(
            "minutes"
        )
    )

    actual_datetime = (
        realtime_stop.get(
            "datetime"
        )
    )

    static_stop[
        "actual_minutes"
    ] = actual_minutes

    static_stop[
        "delay_minutes"
    ] = delay_minutes

    if actual_datetime:

        static_stop[
            "actual_time"
        ] = actual_datetime.isoformat()


# ============================================================
# ACTUALITZAR TREN
# ============================================================

def actualitzar_train(
    train,
    realtime_trip
):

    updated = 0

    realtime_stops = (
        realtime_trip.get(
            "stops",
            []
        )
    )

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
            static_stop.get(
                "stop_id"
            )
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
# ACTUALITZAR ESTAT DEL TREN
# ============================================================

def actualitzar_estat_train(
    train
):

    stops = train.get(
        "stops",
        []
    )

    if not stops:
        return

    stops_amb_realtime = [

        stop

        for stop in stops

        if stop.get(
            "actual_minutes"
        ) is not None

    ]

    if not stops_amb_realtime:
        return

    ultima = (
        stops_amb_realtime[-1]
    )

    if (
        ultima.get(
            "delay_minutes"
        )
        is not None
    ):

        train[
            "final_delay_minutes"
        ] = ultima[
            "delay_minutes"
        ]

    train[
        "started"
    ] = True

    ultima_parada = stops[-1]

    if (
        ultima_parada.get(
            "actual_minutes"
        )
        is not None
    ):

        train[
            "arrived"
        ] = True


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print(
        "=========================================="
    )

    print(
        "R15 REALTIME"
    )

    print(
        "Data:",
        date.today().isoformat()
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # CARREGAR JSON
    # --------------------------------------------------------

    dades, path = (
        carregar_json_avui()
    )

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

        feed = (
            descarregar_realtime()
        )

    except Exception as e:

        print(
            "ERROR descarregant GTFS-RT:",
            repr(e)
        )

        return

    # --------------------------------------------------------
    # EXTREURE TRIPS
    # --------------------------------------------------------

    trips_realtime = (
        extreure_trips_realtime(
            feed
        )
    )

    print(
        "Trips amb informació:",
        len(trips_realtime)
    )

    realtime_by_id = {

        trip["trip_id"]:
            trip

        for trip
        in trips_realtime

    }

    index_stop = (
        crear_index_stop(
            trips_realtime
        )
    )

    # --------------------------------------------------------
    # FILTRAR R15
    # --------------------------------------------------------

    trains = dades.get(
        "trains",
        []
    )

    r15_trains = []

    for train in trains:

        route = normalitzar_id(
            train.get(
                "route_id"
            )
        )

        train_id = normalitzar_id(
            train.get(
                "train_id"
            )
        )

        if (
            "R15"
            in route
            or
            "R15"
            in train_id
            or
            route == ""
        ):

            r15_trains.append(
                train
            )

    if not r15_trains:

        r15_trains = trains

    print(
        "Trens estàtics R15:",
        len(r15_trains)
    )

    # --------------------------------------------------------
    # MATCHING
    # --------------------------------------------------------

    trains_updated = 0

    stops_updated = 0

    direct_matches = 0

    intelligent_matches = 0

    used_trip_ids = set()

    # --------------------------------------------------------
    # PRIMER: MATCHING DIRECTE
    # --------------------------------------------------------

    print()
    print(
        "=========================================="
    )

    print(
        "MATCHING DIRECTE"
    )

    print(
        "=========================================="
    )

    for train in r15_trains:

        train_id = normalitzar_id(
            train.get(
                "train_id"
            )
        )

        direct = (
            buscar_matching_directe(
                train,
                realtime_by_id
            )
        )

        if (
            direct is not None
            and
            train_id
            not in used_trip_ids
        ):

            count = (
                actualitzar_train(
                    train,
                    direct
                )
            )

            if count > 0:

                used_trip_ids.add(
                    direct[
                        "trip_id"
                    ]
                )

                trains_updated += 1

                direct_matches += 1

                stops_updated += count

                print(
                    "DIRECTE:",
                    train_id,
                    "<->",
                    direct[
                        "trip_id"
                    ],
                    "| parades:",
                    count
                )

    # --------------------------------------------------------
    # SEGON: MATCHING INTEL·LIGENT
    # --------------------------------------------------------

    print()
    print(
        "=========================================="
    )

    print(
        "MATCHING INTEL·LIGENT"
    )

    print(
        "Mínim de coincidències:",
        MIN_MATCHING_STOPS
    )

    print(
        "=========================================="
    )

    for train in r15_trains:

        train_id = normalitzar_id(
            train.get(
                "train_id"
            )
        )

        # ----------------------------------------------------
        # Si ja té realtime, no el tornem a buscar.
        # ----------------------------------------------------

        if any(
            stop.get(
                "actual_minutes"
            ) is not None
            for stop in train.get(
                "stops",
                []
            )
        ):

            continue

        intelligent = (
            buscar_matching_intelligent(
                train,
                index_stop,
                used_trip_ids
            )
        )

        if intelligent is None:

            continue

        realtime_trip_id = (
            intelligent[
                "trip_id"
            ]
        )

        realtime_trip = (
            realtime_by_id.get(
                realtime_trip_id
            )
        )

        if realtime_trip is None:

            continue

        count = (
            actualitzar_train(
                train,
                realtime_trip
            )
        )

        if count > 0:

            used_trip_ids.add(
                realtime_trip_id
            )

            trains_updated += 1

            intelligent_matches += 1

            stops_updated += count

            print()

            print(
                "MATCH INTEL·LIGENT ACCEPTAT:",
                train_id,
                "<->",
                realtime_trip_id
            )

            print(
                "  Coincidències:",
                intelligent[
                    "coincidencies"
                ]
            )

            print(
                "  Score:",
                round(
                    intelligent[
                        "score"
                    ],
                    2
                )
            )

            print(
                "  Parades actualitzades:",
                count
            )

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

    dades[
        "realtime_updated_at"
    ] = ara.isoformat()

    dades[
        "source_type"
    ] = "Renfe GTFS-RT"

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

    print(
        "=========================================="
    )

    print(
        "RESULTAT REALTIME"
    )

    print(
        "=========================================="
    )

    print(
        "Trips GTFS-RT:",
        len(trips_realtime)
    )

    print(
        "Trens R15:",
        len(r15_trains)
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
            len(r15_trains)
            - trains_updated
        )
    )

    print(
        "Parades actualitzades:",
        stops_updated
    )

    print(
        "Trips realtime utilitzats:",
        len(
            used_trip_ids
        )
    )

    print(
        "Fitxer actualitzat:",
        path
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":

    main()
