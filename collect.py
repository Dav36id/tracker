import requests
import zipfile
import io
import csv
import json
import os
from collections import defaultdict
from datetime import date, datetime


# ============================================================
# CONFIGURACIÓ
# ============================================================

GTFS_API = "https://data.renfe.com/api/3/action/package_show?id=horarios-cercanias"

DATA = date.today()

OUTPUT_DIR = "data"


# ============================================================
# DESCARREGAR GTFS OFICIAL RENFE
# ============================================================

def descarregar_gtfs():

    print("Descarregant GTFS oficial de Renfe...")

    resposta = requests.get(
        GTFS_API,
        timeout=60
    )

    resposta.raise_for_status()

    dades = resposta.json()

    for recurs in dades["result"]["resources"]:

        if recurs.get(
            "format",
            ""
        ).upper() == "GTFS":

            url = recurs["url"]

            print(
                "URL GTFS:",
                url
            )

            resposta = requests.get(
                url,
                timeout=120
            )

            resposta.raise_for_status()

            return zipfile.ZipFile(
                io.BytesIO(
                    resposta.content
                )
            )

    raise Exception(
        "No s'ha trobat el recurs GTFS de Renfe"
    )


# ============================================================
# LLEGIR CSV DEL GTFS
# ============================================================

def llegir(zip_gtfs, nom):

    print(
        "Llegint",
        nom
    )

    with zip_gtfs.open(nom) as f:

        lector = csv.DictReader(
            io.TextIOWrapper(
                f,
                encoding="utf-8-sig"
            )
        )

        # Netejar noms de columnes
        lector.fieldnames = [
            camp.strip()
            for camp in lector.fieldnames
        ]

        resultat = []

        for fila in lector:

            fila_neta = {}

            for clau, valor in fila.items():

                clau_neta = (
                    clau.strip()
                )

                if isinstance(
                    valor,
                    str
                ):
                    valor_neta = (
                        valor.strip()
                    )
                else:
                    valor_neta = valor

                fila_neta[
                    clau_neta
                ] = valor_neta

            resultat.append(
                fila_neta
            )

        return resultat


# ============================================================
# NORMALITZAR ID
# ============================================================

def normalitzar_id(valor):

    if valor is None:
        return ""

    # Eliminem qualsevol espai,
    # inclosos espais estranys del GTFS.
    return "".join(
        str(valor).split()
    )


# ============================================================
# SERVEI ACTIU
# ============================================================

def servei_actiu(
    service,
    data
):

    inici = date.fromisoformat(
        service["start_date"]
    )

    final = date.fromisoformat(
        service["end_date"]
    )

    if not (
        inici <= data <= final
    ):
        return False

    dies = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday"
    ]

    dia = dies[
        data.weekday()
    ]

    return (
        service.get(
            dia,
            ""
        ) == "1"
    )


# ============================================================
# CONVERTIR HORA GTFS A MINUTS
# ============================================================

def hora_a_minuts(hora):

    if not hora:
        return None

    try:

        parts = hora.split(":")

        h = int(parts[0])
        m = int(parts[1])

        return h * 60 + m

    except Exception:

        return None


# ============================================================
# HORA GTFS A ISO
# ============================================================

def hora_a_iso(
    data,
    hora
):

    minuts = hora_a_minuts(
        hora
    )

    if minuts is None:
        return None

    dia_extra = minuts // (
        24 * 60
    )

    minuts_dia = minuts % (
        24 * 60
    )

    h = minuts_dia // 60
    m = minuts_dia % 60

    from datetime import timedelta

    data_real = (
        data +
        timedelta(
            days=dia_extra
        )
    )

    return (
        f"{data_real.isoformat()}"
        f"T{h:02d}:{m:02d}:00"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "=========================================="
    )
    print(
        "R15 TRACKER"
    )
    print(
        "Data:",
        DATA
    )
    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # GTFS
    # --------------------------------------------------------

    gtfs = descarregar_gtfs()

    # --------------------------------------------------------
    # FITXERS
    # --------------------------------------------------------

    routes = llegir(
        gtfs,
        "routes.txt"
    )

    trips = llegir(
        gtfs,
        "trips.txt"
    )

    stop_times = llegir(
        gtfs,
        "stop_times.txt"
    )

    stops = llegir(
        gtfs,
        "stops.txt"
    )

    calendar = llegir(
        gtfs,
        "calendar.txt"
    )

    # --------------------------------------------------------
    # ESTACIONS
    # --------------------------------------------------------

    stop_names = {}

    for stop in stops:

        stop_id = normalitzar_id(
            stop.get(
                "stop_id"
            )
        )

        stop_name = (
            stop.get(
                "stop_name",
                ""
            ).strip()
        )

        stop_names[
            stop_id
        ] = stop_name

    # --------------------------------------------------------
    # LOCALITZAR REUS
    # --------------------------------------------------------

    reus_stop_ids = set()

    for stop_id, nom in stop_names.items():

        if (
            "REUS"
            in nom.upper()
        ):

            reus_stop_ids.add(
                stop_id
            )

    print()
    print(
        "Estacions Reus:",
        reus_stop_ids
    )

    # --------------------------------------------------------
    # RUTES R15
    # --------------------------------------------------------

    r15_routes = set()

    for route in routes:

        route_name = (
            route.get(
                "route_short_name",
                ""
            ).strip()
        )

        if route_name.upper() == "R15":

            r15_routes.add(
                normalitzar_id(
                    route.get(
                        "route_id"
                    )
                )
            )

    print(
        "Rutes R15:",
        len(r15_routes)
    )

    # --------------------------------------------------------
    # SERVEIS ACTIUS
    # --------------------------------------------------------

    serveis_actius = set()

    for service in calendar:

        if servei_actiu(
            service,
            DATA
        ):

            serveis_actius.add(
                normalitzar_id(
                    service.get(
                        "service_id"
                    )
                )
            )

    print(
        "Serveis actius:",
        len(serveis_actius)
    )

    # --------------------------------------------------------
    # TRIPS R15 DEL DIA
    # --------------------------------------------------------

    r15_trips = []

    for trip in trips:

        route_id = normalitzar_id(
            trip.get(
                "route_id"
            )
        )

        service_id = normalitzar_id(
            trip.get(
                "service_id"
            )
        )

        if (
            route_id in r15_routes
            and
            service_id in serveis_actius
        ):

            r15_trips.append(
                trip
            )

    print(
        "Trips R15 del dia:",
        len(r15_trips)
    )

    # --------------------------------------------------------
    # INDEXAR TRIPS
    # --------------------------------------------------------

    trip_by_id = {}

    for trip in r15_trips:

        trip_id = normalitzar_id(
            trip.get(
                "trip_id"
            )
        )

        trip_by_id[
            trip_id
        ] = trip

    # --------------------------------------------------------
    # INDEXAR STOP_TIMES
    #
    # IMPORTANT:
    # aquí normalitzem TAMBÉ els trip_id.
    # --------------------------------------------------------

    parades = defaultdict(list)

    coincidencies = 0

    for stop_time in stop_times:

        trip_id = normalitzar_id(
            stop_time.get(
                "trip_id"
            )
        )

        if trip_id not in trip_by_id:

            continue

        stop_id = normalitzar_id(
            stop_time.get(
                "stop_id"
            )
        )

        station = stop_names.get(
            stop_id,
            stop_id
        )

        sequence_text = (
            stop_time.get(
                "stop_sequence",
                "0"
            )
        )

        try:

            sequence = int(
                sequence_text
            )

        except Exception:

            continue

        arrival = (
            stop_time.get(
                "arrival_time",
                ""
            )
        )

        departure = (
            stop_time.get(
                "departure_time",
                ""
            )
        )

        parades[
            trip_id
        ].append({

            "sequence":
                sequence,

            "stop_id":
                stop_id,

            "station":
                station,

            "arrival":
                arrival,

            "departure":
                departure,

            "scheduled_arrival":
                hora_a_minuts(
                    arrival
                ),

            "scheduled_departure":
                hora_a_minuts(
                    departure
                )

        })

        coincidencies += 1

    print(
        "Stop_times R15 trobats:",
        coincidencies
    )

    # --------------------------------------------------------
    # ORDENAR PARADES
    # --------------------------------------------------------

    for trip_id in parades:

        parades[
            trip_id
        ].sort(
            key=lambda x:
                x["sequence"]
        )

    # --------------------------------------------------------
    # CONSTRUIR CIRCULACIONS
    # --------------------------------------------------------

    circulacions = []

    for trip in r15_trips:

        trip_id = normalitzar_id(
            trip.get(
                "trip_id"
            )
        )

        stops_trip = parades.get(
            trip_id,
            []
        )

        # Sense parades no podem mostrar
        # la circulació.
        if not stops_trip:

            continue

        primera = (
            stops_trip[0]
        )

        ultima = (
            stops_trip[-1]
        )

        # ----------------------------------------------------
        # DETERMINAR SENTIT
        # ----------------------------------------------------

        passa_reus = any(
            stop["stop_id"]
            in reus_stop_ids
            for stop in stops_trip
        )

        nom_primera = (
            primera["station"]
            .upper()
        )

        nom_ultima = (
            ultima["station"]
            .upper()
        )

        # Intentem identificar Barcelona.
        es_barcelona = (
            "BARCELONA"
            in nom_primera
            or
            "BARCELONA"
            in nom_ultima
        )

        if (
            es_barcelona
            and
            "REUS"
            in nom_ultima
        ):

            direction = "BAR_REUS"

        elif (
            "REUS"
            in nom_primera
            and
            es_barcelona
        ):

            direction = "REUS_BAR"

        elif passa_reus:

            # Si el tram R15 conté Reus però
            # no identifica Barcelona en el mateix
            # trip, mantenim el sentit segons
            # la posició de Reus.
            if (
                reus_stop_ids
                and
                primera["stop_id"]
                in reus_stop_ids
            ):

                direction = "REUS_BAR"

            else:

                direction = "BAR_REUS"

        else:

            # Altres trams R15 que no passen per Reus
            # no ens interessen per al tracker
            continue

        # ----------------------------------------------------
        # PARADES PER AL JSON
        # ----------------------------------------------------

        stops_json = []

        for stop in stops_trip:

            stops_json.append({

                "station":
                    stop["station"],

                "stop_id":
                    stop["stop_id"],

                "scheduled_arrival":
                    stop["scheduled_arrival"],

                "scheduled_departure":
                    stop["scheduled_departure"],

                "actual_minutes":
                    None

            })

        # ----------------------------------------------------
        # SORTIR DE LA CIRCULACIÓ
        # ----------------------------------------------------

        departure_iso = (
            hora_a_iso(
                DATA,
                primera["departure"]
            )
        )

        arrival_iso = (
            hora_a_iso(
                DATA,
                ultima["arrival"]
            )
        )

        circulacio = {

            "train_id":
                trip_id,

            "route_id":
                normalitzar_id(
                    trip.get(
                        "route_id"
                    )
                ),

            "service_id":
                normalitzar_id(
                    trip.get(
                        "service_id"
                    )
                ),

            "direction":
                direction,

            "departure":
                departure_iso,

            "arrival":
                arrival_iso,

            "started":
                False,

            "arrived":
                False,

            "final_delay_minutes":
                0,

            "stops":
                stops_json

        }

        circulacions.append(
            circulacio
        )

    # --------------------------------------------------------
    # ORDENAR
    # --------------------------------------------------------

    circulacions.sort(
        key=lambda train:
            (
                train["departure"]
                or ""
            )
    )

    # --------------------------------------------------------
    # RESULTAT
    # --------------------------------------------------------

    resultat = {

        "source":
            "Renfe Data",

        "source_type":
            "GTFS",

        "generated_at":
            datetime.now().astimezone().isoformat(),

        "date":
            DATA.isoformat(),

        "line":
            "R15",

        "trains":
            circulacions

    }

    # --------------------------------------------------------
    # CREAR DIRECTORI
    # --------------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        f"{DATA.isoformat()}.json"
    )

    # --------------------------------------------------------
    # GUARDAR JSON
    # --------------------------------------------------------

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            resultat,
            f,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # RESUM
    # --------------------------------------------------------

    print()
    print(
        "=========================================="
    )

    print(
        "CIRCULACIONS R15:",
        len(circulacions)
    )

    print(
        "Barcelona → Reus:",
        sum(
            1
            for t in circulacions
            if t["direction"]
            == "BAR_REUS"
        )
    )

    print(
        "Reus → Barcelona:",
        sum(
            1
            for t in circulacions
            if t["direction"]
            == "REUS_BAR"
        )
    )

    print(
        "Fitxer generat:",
        output_file
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()
