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

# Diferència màxima entre l'hora teòrica calculada
# a partir del realtime i l'hora teòrica del tren.
MAX_SCHEDULE_MATCH_MINUTES = 3

# Si dos trens estan massa a prop, no acceptem
# automàticament el matching.
MIN_CANDIDATE_SEPARATION_MINUTES = 2

# Diferència màxima entre el retard declarat pel feed
# i el retard calculat.
MAX_DELAY_DIFFERENCE_MINUTES = 5


# ============================================================
# UTILITATS
# ============================================================

def normalitzar_id(valor):

    if valor is None:
        return ""

    return str(valor).strip()


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


def format_minutes(minutes):

    if minutes is None:
        return "--:--"

    minutes = int(round(minutes))

    # Admetem horaris > 24:00
    # però per visualitzar-los fem servir el rellotge.
    display = minutes % (24 * 60)

    hores = display // 60
    minuts = display % 60

    return f"{hores:02d}:{minuts:02d}"


def diferencia_circular_minutes(a, b):

    """
    Diferència entre dues hores en minuts.

    Permet comparar també horaris propers a mitjanit.
    """

    d = abs(
        int(a) - int(b)
    )

    return min(
        d,
        24 * 60 - d
    )


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
# NETEJAR REALTIME ANTIC
# ============================================================

def netejar_realtime(dades):

    """
    Elimina les dades realtime de l'execució anterior.

    Això és important perquè collect.py pot conservar
    dades realtime vàlides del run anterior.

    Cada execució de realtime.py començarà des de zero
    i només escriurà la informació disponible en el feed
    actual.
    """

    trains = dades.get(
        "trains",
        []
    )

    camps_stop = [
        "actual_minutes",
        "delay_minutes",
        "actual_time"
    ]

    camps_train = [
        "final_delay_minutes",
        "started",
        "arrived"
    ]

    stops_netejades = 0

    for train in trains:

        for stop in train.get(
            "stops",
            []
        ):

            for camp in camps_stop:

                if camp in stop:

                    del stop[camp]

                    stops_netejades += 1

        for camp in camps_train:

            if camp in train:

                del train[camp]

    print(
        "Dades realtime antigues eliminades:",
        stops_netejades
    )


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

            delay_seconds = (
                int(delay_seconds)
                if delay_seconds is not None
                else 0
            )

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
                    delay_seconds

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
# HORA TEÒRICA D'UNA PARADA
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

        return int(
            valor
        )

    except Exception:

        return None


# ============================================================
# MATCHING DIRECTE PER ID
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
# CONSTRUIR ÍNDEX DE TOTES LES PARADES ESTÀTIQUES
# ============================================================

def construir_index_horaris(
    r15_trains
):

    """
    Índex:

        hora_teorica
            ->
        candidats (tren + parada)

    No depenem del stop_id realtime.

    """

    index = {}

    for train in r15_trains:

        train_id = normalitzar_id(
            train.get(
                "train_id"
            )
        )

        for static_stop in train.get(
            "stops",
            []
        ):

            theoretical = (
                hora_teorica_parada(
                    static_stop
                )
            )

            if theoretical is None:
                continue

            # Guardem també petites variacions.
            #
            # Exemple:
            # 16:42
            # 16:43
            # 16:41

            for offset in (
                -2,
                -1,
                0,
                1,
                2
            ):

                key = (
                    theoretical
                    + offset
                )

                if key not in index:

                    index[key] = []

                index[key].append({

                    "train":
                        train,

                    "train_id":
                        train_id,

                    "static_stop":
                        static_stop,

                    "theoretical":
                        theoretical

                })

    return index


# ============================================================
# MATCHING PER HORA
# ============================================================

def buscar_matching_per_hora(
    realtime_trip,
    r15_trains,
    horaris_index,
    used_trip_ids
):

    trip_id = realtime_trip[
        "trip_id"
    ]

    if trip_id in used_trip_ids:

        return None

    candidats = []

    # --------------------------------------------------------
    # Cada TripUpdate pot tenir una o diverses parades.
    # --------------------------------------------------------

    for realtime_stop in realtime_trip.get(
        "stops",
        []
    ):

        real_minutes = realtime_stop.get(
            "minutes"
        )

        if real_minutes is None:
            continue

        delay_minutes = (
            realtime_stop.get(
                "delay_seconds",
                0
            )
            / 60
        )

        # ----------------------------------------------------
        # Calcul de l'hora teòrica implícita
        #
        # Exemple:
        #
        # real: 17:05
        # retard: +5
        #
        # teòrica implícita: 17:00
        # ----------------------------------------------------

        theoretical_implied = (
            real_minutes
            - delay_minutes
        )

        # ----------------------------------------------------
        # Buscar candidats propers
        # ----------------------------------------------------

        rounded_theoretical = round(
            theoretical_implied
        )

        for key in range(
            rounded_theoretical - 3,
            rounded_theoretical + 4
        ):

            possibles = horaris_index.get(
                key,
                []
            )

            for possible in possibles:

                train = possible[
                    "train"
                ]

                train_id = possible[
                    "train_id"
                ]

                static_stop = possible[
                    "static_stop"
                ]

                theoretical = possible[
                    "theoretical"
                ]

                # No reutilitzar el mateix realtime
                # per a dos trens.
                if trip_id in used_trip_ids:
                    continue

                # ------------------------------------------------
                # Diferència horària
                # ------------------------------------------------

                schedule_difference = (
                    theoretical_implied
                    - theoretical
                )

                if abs(
                    schedule_difference
                ) > MAX_SCHEDULE_MATCH_MINUTES:

                    continue

                # ------------------------------------------------
                # Coherència del retard
                #
                # Calculat:
                #
                # real - teòrica
                #
                # vs
                #
                # retard del feed
                # ------------------------------------------------

                calculated_delay = (
                    real_minutes
                    - theoretical
                )

                delay_difference = abs(
                    calculated_delay
                    - delay_minutes
                )

                if (
                    delay_difference
                    > MAX_DELAY_DIFFERENCE_MINUTES
                ):

                    continue

                candidats.append({

                    "trip_id":
                        trip_id,

                    "realtime_stop":
                        realtime_stop,

                    "train":
                        train,

                    "train_id":
                        train_id,

                    "static_stop":
                        static_stop,

                    "theoretical":
                        theoretical,

                    "real_minutes":
                        real_minutes,

                    "delay_minutes":
                        delay_minutes,

                    "schedule_difference":
                        schedule_difference,

                    "delay_difference":
                        delay_difference

                })

    # --------------------------------------------------------
    # Si no tenim candidats
    # --------------------------------------------------------

    if not candidats:

        return None

    # --------------------------------------------------------
    # Ordenar candidats
    #
    # Prioritat:
    #
    # 1. menor diferència horària
    # 2. menor incoherència de retard
    # --------------------------------------------------------

    candidats.sort(
        key=lambda c: (
            abs(
                c[
                    "schedule_difference"
                ]
            ),
            c[
                "delay_difference"
            ]
        )
    )

    # --------------------------------------------------------
    # Eliminar duplicats del mateix tren
    #
    # Un tren pot tenir diverses parades candidates.
    # Ens quedem amb la millor.
    # --------------------------------------------------------

    millors_per_tren = {}

    for candidat in candidats:

        train_id = candidat[
            "train_id"
        ]

        actual = millors_per_tren.get(
            train_id
        )

        if (
            actual is None
            or
            (
                abs(
                    candidat[
                        "schedule_difference"
                    ]
                )
                <
                abs(
                    actual[
                        "schedule_difference"
                    ]
                )
            )
        ):

            millors_per_tren[
                train_id
            ] = candidat

    candidats_unics = list(
        millors_per_tren.values()
    )

    candidats_unics.sort(
        key=lambda c: (
            abs(
                c[
                    "schedule_difference"
                ]
            ),
            c[
                "delay_difference"
            ]
        )
    )

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    print()

    print(
        "CANDIDATS PER RT:",
        trip_id
    )

    for candidat in candidatos_unics[:10]:

        print(
            "  -",
            candidat[
                "train_id"
            ],
            "| teòrica:",
            format_minutes(
                candidat[
                    "theoretical"
                ]
            ),
            "| RT:",
            format_minutes(
                candidat[
                    "real_minutes"
                ]
            ),
            "| retard feed:",
            f"{candidat['delay_minutes']:+.1f}",
            "| diferència:",
            f"{candidat['schedule_difference']:+.1f}"
        )

    # --------------------------------------------------------
    # Si només tenim un candidat
    # --------------------------------------------------------

    millor = candidats_unics[0]

    if len(candidats_unics) == 1:

        print(
            "  >>> CANDIDAT ÚNIC:",
            millor[
                "train_id"
            ]
        )

        return millor

    # --------------------------------------------------------
    # Comparar primer i segon
    #
    # Si estan massa a prop, no decidim.
    # --------------------------------------------------------

    segon = candidats_unics[1]

    distancia = abs(
        (
            abs(
                segon[
                    "schedule_difference"
                ]
            )
            -
            abs(
                millor[
                    "schedule_difference"
                ]
            )
        )
    )

    if (
        distancia
        < MIN_CANDIDATE_SEPARATION_MINUTES
    ):

        print(
            "  !!! AMBIGU:",
            trip_id,
            "| millors:",
            millor[
                "train_id"
            ],
            "i",
            segon[
                "train_id"
            ],
            "| separació score:",
            round(
                distancia,
                2
            )
        )

        return None

    print(
        "  >>> MILLOR CANDIDAT:",
        millor[
            "train_id"
        ]
    )

    return millor


# ============================================================
# APLICAR REALTIME A UNA PARADA
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
        ] = (
            actual_datetime.isoformat()
        )


# ============================================================
# APLICAR REALTIME A UN TREN
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

    # --------------------------------------------------------
    # Si tenim stop_id coincident, el fem servir.
    # --------------------------------------------------------

    realtime_by_stop = {}

    for stop in realtime_stops:

        stop_id = normalitzar_id(
            stop.get(
                "stop_id"
            )
        )

        if stop_id:

            realtime_by_stop[
                stop_id
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
# APLICAR UNA ÚNICA PARADA DETECTADA
# ============================================================

def aplicar_matching_individual(
    candidat
):

    train = candidat[
        "train"
    ]

    static_stop = candidat[
        "static_stop"
    ]

    realtime_stop = candidat[
        "realtime_stop"
    ]

    aplicar_realtime(
        static_stop,
        realtime_stop
    )

    return 1


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

    # Ordenar cronològicament les parades
    # amb realtime.

    stops_amb_realtime.sort(
        key=lambda stop:
            stop.get(
                "actual_minutes",
                -1
            )
    )

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

    # Només considerem arribat si l'última
    # parada física del tren té realtime.

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
    # NETEJAR REALTIME ANTERIOR
    # --------------------------------------------------------

    netejar_realtime(
        dades
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

        # Guardem les dades netes?
        #
        # NO.
        #
        # Si Renfe falla, no destruïm les dades
        # del fitxer actual.

        return

    # --------------------------------------------------------
    # EXTREURE TRIPS REALTIME
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
    # ÍNDEX HORARIS
    # --------------------------------------------------------

    horaris_index = (
        construir_index_horaris(
            r15_trains
        )
    )

    # --------------------------------------------------------
    # VARIABLES
    # --------------------------------------------------------

    trains_updated = 0

    stops_updated = 0

    direct_matches = 0

    intelligent_matches = 0

    used_trip_ids = set()

    used_train_ids = set()

    # ========================================================
    # 1. MATCHING DIRECTE
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "1. MATCHING DIRECTE"
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

        if direct is None:

            continue

        if direct.get(
            "trip_id"
        ) in used_trip_ids:

            continue

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

            used_train_ids.add(
                train_id
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

    # ========================================================
    # 2. MATCHING PER HORA
    # ========================================================

    print()

    print(
        "=========================================="
    )

    print(
        "2. MATCHING PER HORA"
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Primer processem els trips realtime que tenen
    # una hora i retard vàlids.
    # --------------------------------------------------------

    candidats_processats = 0

    for realtime_trip in trips_realtime:

        trip_id = realtime_trip[
            "trip_id"
        ]

        if trip_id in used_trip_ids:

            continue

        if not realtime_trip.get(
            "stops"
        ):

            continue

        candidat = (
            buscar_matching_per_hora(
                realtime_trip,
                r15_trains,
                horaris_index,
                used_trip_ids
            )
        )

        if candidat is None:

            continue

        train = candidat[
            "train"
        ]

        train_id = candidat[
            "train_id"
        ]

        # ----------------------------------------------------
        # No reutilitzar un tren estàtic
        # ----------------------------------------------------

        if train_id in used_train_ids:

            print(
                "  DESCARTAT:",
                trip_id,
                "->",
                train_id,
                "| tren ja utilitzat"
            )

            continue

        # ----------------------------------------------------
        # Aplicar només la parada que realment hem pogut
        # identificar.
        # ----------------------------------------------------

        count = (
            aplicar_matching_individual(
                candidat
            )
        )

        if count <= 0:

            continue

        used_trip_ids.add(
            trip_id
        )

        used_train_ids.add(
            train_id
        )

        trains_updated += 1

        intelligent_matches += 1

        stops_updated += count

        candidats_processats += 1

        print()

        print(
            "MATCH PER HORA ACCEPTAT:",
            train_id,
            "<->",
            trip_id
        )

        print(
            "  Parada:",
            normalitzar_id(
                candidat[
                    "static_stop"
                ].get(
                    "stop_id"
                )
            )
        )

        print(
            "  Teòrica:",
            format_minutes(
                candidat[
                    "theoretical"
                ]
            )
        )

        print(
            "  Realtime:",
            format_minutes(
                candidat[
                    "real_minutes"
                ]
            )
        )

        print(
            "  Retard feed:",
            f"{candidat['delay_minutes']:+.1f} min"
        )

    # ========================================================
    # 3. ESTATS
    # ========================================================

    for train in r15_trains:

        actualitzar_estat_train(
            train
        )

    # ========================================================
    # METADADES
    # ========================================================

    ara = datetime.now(
        TZ
    )

    dades[
        "realtime_updated_at"
    ] = ara.isoformat()

    dades[
        "source_type"
    ] = "Renfe GTFS-RT"

    # ========================================================
    # GUARDAR
    # ========================================================

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

    # ========================================================
    # RESULTAT
    # ========================================================

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
        "  - Matching per hora:",
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
