const directionSelect = document.getElementById("direction");
const dateInput = document.getElementById("date");
const trainsContainer = document.getElementById("trains");
const summaryContainer = document.getElementById("summary");
const toggleHistoryButton = document.getElementById("toggleHistory");

let showHistory = false;
let currentData = null;


// ============================================================
// DATA
// ============================================================

function getTodayString() {

    const now = new Date();

    return (
        now.getFullYear() +
        "-" +
        String(now.getMonth() + 1).padStart(2, "0") +
        "-" +
        String(now.getDate()).padStart(2, "0")
    );
}


// ============================================================
// TIME
// ============================================================

function parseTimeToMinutes(value) {

    if (
        value === undefined ||
        value === null ||
        value === ""
    ) {
        return null;
    }

    if (
        typeof value === "number" &&
        Number.isFinite(value)
    ) {
        return value;
    }

    if (
        typeof value === "string" &&
        value.trim() !== "" &&
        !Number.isNaN(Number(value))
    ) {
        return Number(value);
    }

    const stringValue = String(value).trim();

    const match = stringValue.match(
        /^(\d{1,2}):(\d{2})/
    );

    if (match) {

        return (
            Number(match[1]) * 60 +
            Number(match[2])
        );
    }

    const date = new Date(stringValue);

    if (!Number.isNaN(date.getTime())) {

        return (
            date.getHours() * 60 +
            date.getMinutes()
        );
    }

    return null;
}


function formatTime(value) {

    if (
        value === undefined ||
        value === null ||
        value === ""
    ) {
        return "--:--";
    }

    const minutes = parseTimeToMinutes(value);

    if (minutes === null) {
        return "--:--";
    }

    const normalized =
        ((minutes % 1440) + 1440) % 1440;

    const hours =
        Math.floor(normalized / 60);

    const mins =
        normalized % 60;

    return (
        String(hours).padStart(2, "0") +
        ":" +
        String(mins).padStart(2, "0")
    );
}


function getNowMinutes() {

    const now = new Date();

    return (
        now.getHours() * 60 +
        now.getMinutes()
    );
}


// ============================================================
// DELAY
// ============================================================

function getDelayMinutes(stop) {

    if (!stop) {
        return null;
    }

    if (
        stop.delay_minutes !== undefined &&
        stop.delay_minutes !== null
    ) {
        return Math.round(
            Number(stop.delay_minutes)
        );
    }

    if (
        stop.realtime_delay_minutes !== undefined &&
        stop.realtime_delay_minutes !== null
    ) {
        return Math.round(
            Number(stop.realtime_delay_minutes)
        );
    }

    if (
        stop.delay_seconds !== undefined &&
        stop.delay_seconds !== null
    ) {
        return Math.round(
            Number(stop.delay_seconds) / 60
        );
    }

    if (
        stop.delay !== undefined &&
        stop.delay !== null
    ) {
        return Math.round(
            Number(stop.delay)
        );
    }

    return null;
}


// ============================================================
// STATION
// ============================================================

function getStationName(stop) {

    if (!stop) {
        return "Parada";
    }

    return (
        stop.station ||
        stop.stop_name ||
        stop.station_name ||
        stop.name ||
        stop.stop ||
        stop.stopId ||
        stop.stop_id ||
        "Parada"
    );
}


// ============================================================
// THEORETICAL TIME
// ============================================================

function getTheoreticalTime(stop) {

    if (!stop) {
        return null;
    }

    if (
        stop.scheduled_arrival !== undefined &&
        stop.scheduled_arrival !== null
    ) {
        return Number(
            stop.scheduled_arrival
        );
    }

    if (
        stop.scheduled_departure !== undefined &&
        stop.scheduled_departure !== null
    ) {
        return Number(
            stop.scheduled_departure
        );
    }

    return null;
}


// ============================================================
// REALTIME TIME
// ============================================================

function getRealtimeTime(stop) {

    if (!stop) {
        return null;
    }

    if (
        stop.actual_minutes !== undefined &&
        stop.actual_minutes !== null
    ) {
        return Number(
            stop.actual_minutes
        );
    }

    if (
        stop.actual_time !== undefined &&
        stop.actual_time !== null
    ) {
        return stop.actual_time;
    }

    return null;
}


// ============================================================
// DEPARTURE
// ============================================================

function getDepartureTime(train) {

    if (!train) {
        return null;
    }

    if (train.departure) {
        return train.departure;
    }

    if (
        Array.isArray(train.stops) &&
        train.stops.length > 0
    ) {

        const firstStop = train.stops[0];

        return (
            firstStop.scheduled_departure ??
            firstStop.scheduled_arrival ??
            null
        );
    }

    return null;
}


// ============================================================
// ARRIVAL
// ============================================================

function getArrivalTime(train) {

    if (!train) {
        return null;
    }

    if (train.arrival) {
        return train.arrival;
    }

    if (
        Array.isArray(train.stops) &&
        train.stops.length > 0
    ) {

        const lastStop =
            train.stops[train.stops.length - 1];

        return (
            lastStop.scheduled_arrival ??
            lastStop.scheduled_departure ??
            null
        );
    }

    return null;
}


// ============================================================
// LAST STOP
// ============================================================

function getLastStop(train) {

    if (
        !train ||
        !Array.isArray(train.stops) ||
        train.stops.length === 0
    ) {
        return null;
    }

    return train.stops[
        train.stops.length - 1
    ];
}


// ============================================================
// ACTUAL ARRIVAL
// ============================================================

function getActualArrivalMinutes(train) {

    const lastStop = getLastStop(train);

    if (!lastStop) {
        return null;
    }

    const actual =
        getRealtimeTime(lastStop);

    return parseTimeToMinutes(actual);
}


// ============================================================
// FINAL DELAY
// ============================================================

function getFinalDelay(train) {

    if (!train) {
        return 0;
    }

    if (
        train.final_delay_minutes !== undefined &&
        train.final_delay_minutes !== null
    ) {
        return Math.round(
            Number(
                train.final_delay_minutes
            )
        );
    }

    if (
        train.realtime_trip_delay_minutes !== undefined &&
        train.realtime_trip_delay_minutes !== null
    ) {
        return Math.round(
            Number(
                train.realtime_trip_delay_minutes
            )
        );
    }

    const lastStop = getLastStop(train);

    const delay =
        getDelayMinutes(lastStop);

    return delay !== null
        ? delay
        : 0;
}


// ============================================================
// ARRIVED?
// ============================================================

function hasTrainArrived(
    train,
    selectedDate
) {

    if (!train) {
        return false;
    }

    if (
        train.arrived === true ||
        train.has_arrived === true ||
        train.finished === true ||
        train.completed === true
    ) {
        return true;
    }

    const today = getTodayString();

    if (selectedDate < today) {
        return true;
    }

    if (selectedDate > today) {
        return false;
    }

    const actualArrival =
        getActualArrivalMinutes(train);

    if (actualArrival !== null) {

        return (
            actualArrival <=
            getNowMinutes()
        );
    }

    const arrival =
        getArrivalTime(train);

    const arrivalMinutes =
        parseTimeToMinutes(arrival);

    if (arrivalMinutes !== null) {

        const lastStop =
            getLastStop(train);

        const delay =
            getDelayMinutes(lastStop);

        const finalDelay =
            delay !== null
                ? Math.max(0, delay)
                : 0;

        return (
            arrivalMinutes +
            finalDelay <=
            getNowMinutes()
        );
    }

    return false;
}


// ============================================================
// DEPARTED?
// ============================================================

function hasTrainDeparted(train) {

    if (!train) {
        return false;
    }

    if (train.started === true) {
        return true;
    }

    const departure =
        getDepartureTime(train);

    const departureMinutes =
        parseTimeToMinutes(departure);

    if (departureMinutes === null) {
        return false;
    }

    return (
        departureMinutes <=
        getNowMinutes()
    );
}


// ============================================================
// STATUS
// ============================================================

function getTrainStatus(
    train,
    selectedDate
) {

    const arrived =
        hasTrainArrived(
            train,
            selectedDate
        );

    const delay =
        getFinalDelay(train);

    if (arrived) {

        if (delay > 15) {
            return "late";
        }

        return "finished";
    }

    if (!hasTrainDeparted(train)) {
        return "pending";
    }

    if (delay >= 4) {
        return "warning";
    }

    return "running";
}


// ============================================================
// STATUS TEXT
// ============================================================

function getStatusText(
    status,
    train
) {

    const delay =
        getFinalDelay(train);

    switch (status) {

        case "pending":
            return "Encara no ha sortit";

        case "running":

            if (delay > 0) {
                return `En circulació · +${delay} min`;
            }

            return "En circulació · en hora";

        case "warning":
            return `En circulació · +${delay} min`;

        case "late":
            return `Arribat · +${delay} min`;

        case "finished":
            return "Arribat";

        default:
            return "";
    }
}


// ============================================================
// TRAIN ID
// ============================================================

function getTrainId(train) {

    return (
        train.train_id ||
        train.trip_id ||
        train.id ||
        train.tripId ||
        "Tren"
    );
}


// ============================================================
// RENDER STOPS
// ============================================================

function renderStops(train) {

    if (
        !Array.isArray(train.stops) ||
        train.stops.length === 0
    ) {

        return `
            <div class="stops">
                <p class="no-stops">
                    No hi ha informació de parades.
                </p>
            </div>
        `;
    }

    let html = `

        <div class="stops">

            <div class="stops-title">
                Parades
            </div>

            <div class="stops-header">

                <div class="stop-header-station">
                    Estació
                </div>

                <div class="stop-header-theoretical">
                    Teòrica
                </div>

                <div class="stop-header-real">
                    Real
                </div>

                <div class="stop-header-delay">
                    Retard
                </div>

            </div>
    `;


    for (const stop of train.stops) {

        const station =
            getStationName(stop);

        const theoretical =
            getTheoreticalTime(stop);

        const realtime =
            getRealtimeTime(stop);

        const delay =
            getDelayMinutes(stop);


        // ----------------------------------------------------
        // REAL / ESTIMADA
        // ----------------------------------------------------

        let realHtml = "";


        if (realtime !== null) {

            realHtml = `

                <div class="real-cell">

                    <span class="actual-time">
                        ${formatTime(realtime)}
                    </span>

                    <span class="time-label real-label">
                        real
                    </span>

                </div>

            `;

        } else if (
            theoretical !== null &&
            delay !== null
        ) {

            const theoreticalMinutes =
                parseTimeToMinutes(
                    theoretical
                );

            const estimatedMinutes =
                theoreticalMinutes + delay;

            realHtml = `

                <div class="real-cell">

                    <span class="estimated-time">
                        ${formatTime(
                            estimatedMinutes
                        )}
                    </span>

                    <span class="time-label estimated-label">
                        estimada
                    </span>

                </div>

            `;

        } else {

            realHtml = `

                <div class="real-cell">

                    <span class="no-real-time">
                        —
                    </span>

                </div>

            `;
        }


        // ----------------------------------------------------
        // RETARD
        // ----------------------------------------------------

        let delayHtml = "—";

        if (
            delay !== null &&
            delay !== 0
        ) {

            const prefix =
                delay > 0
                    ? "+"
                    : "";

            delayHtml = `
                <span class="stop-delay">
                    ${prefix}${delay} min
                </span>
            `;
        }


        // ----------------------------------------------------
        // ROW
        // ----------------------------------------------------

        html += `

            <div class="stop-row">

                <div class="stop-name">
                    ${station}
                </div>

                <div class="theoretical-cell">

                    <span class="theoretical-time">
                        ${formatTime(theoretical)}
                    </span>

                </div>

                ${realHtml}

                <div class="delay-cell">

                    ${delayHtml}

                </div>

            </div>

        `;
    }


    html += `

        </div>

    `;


    return html;
}


// ============================================================
// RENDER TRAIN
// ============================================================

function renderTrain(
    train,
    selectedDate
) {

    const status =
        getTrainStatus(
            train,
            selectedDate
        );

    const delay =
        getFinalDelay(train);

    const trainId =
        getTrainId(train);

    const departure =
        getDepartureTime(train);

    const arrival =
        getArrivalTime(train);

    const statusText =
        getStatusText(
            status,
            train
        );

    const expressRefund =
        delay > 15;


    return `

        <article
            class="train ${status}"
            data-train-id="${trainId}"
        >

            <div class="train-main">

                <div class="train-left">

                    <div class="train-id">
                        🚆 ${trainId}
                    </div>

                    <div class="train-route">

                        <span>
                            ${formatTime(departure)}
                        </span>

                        <span class="arrow">
                            →
                        </span>

                        <span>
                            ${formatTime(arrival)}
                        </span>

                    </div>

                </div>

                <div class="train-right">

                    <div class="status">

                        <span class="status-dot"></span>

                        ${statusText}

                    </div>

                    ${
                        expressRefund
                            ? `

                                <div class="refund">

                                    Sí es pot sol·licitar
                                    devolució express

                                </div>

                            `
                            : ""
                    }

                </div>

            </div>

            ${renderStops(train)}

        </article>

    `;
}


// ============================================================
// SUMMARY
// ============================================================

function renderSummary(
    total,
    visible,
    arrived
) {

    summaryContainer.innerHTML = `

        <div class="summary">

            <strong>
                ${visible}
            </strong>

            trens mostrats

            ${
                showHistory
                    ? `

                        · ${arrived}
                        trens arribats

                    `
                    : ""
            }

        </div>

    `;
}


// ============================================================
// RENDER
// ============================================================

function render(data) {

    if (!data) {
        return;
    }

    const selectedDate =
        dateInput.value;

    let trains =
        data.trains ||
        data.circulations ||
        [];

    // --------------------------------------------------------
    // SENTIT
    // --------------------------------------------------------

    const direction =
        directionSelect.value;

    trains =
        trains.filter(train => {

            const trainDirection =
                train.direction ||
                train.route_direction ||
                train.direction_code;

            if (!trainDirection) {
                return true;
            }

            return (
                trainDirection ===
                direction
            );

        });


    // --------------------------------------------------------
    // VISIBILITAT
    // --------------------------------------------------------

    let visible;


    if (!showHistory) {

        visible =
            trains.filter(train => {

                return !hasTrainArrived(
                    train,
                    selectedDate
                );

            });

    } else {

        visible =
            trains.filter(train => {

                return hasTrainArrived(
                    train,
                    selectedDate
                );

            });

    }


    // --------------------------------------------------------
    // ORDRE
    // --------------------------------------------------------

    visible.sort((a, b) => {

        const timeA =
            parseTimeToMinutes(
                getDepartureTime(a)
            ) ?? 9999;

        const timeB =
            parseTimeToMinutes(
                getDepartureTime(b)
            ) ?? 9999;

        return timeA - timeB;

    });


    // --------------------------------------------------------
    // RESUM
    // --------------------------------------------------------

    const arrivedCount =
        trains.filter(train =>
            hasTrainArrived(
                train,
                selectedDate
            )
        ).length;


    renderSummary(
        trains.length,
        visible.length,
        arrivedCount
    );


    // --------------------------------------------------------
    // CAP TREN
    // --------------------------------------------------------

    if (visible.length === 0) {

        trainsContainer.innerHTML = `

            <div class="empty">

                ${
                    showHistory
                        ? "No hi ha trens ja arribats."
                        : "No hi ha trens en circulació o pendents."
                }

            </div>

        `;

        return;
    }


    // --------------------------------------------------------
    // RENDER
    // --------------------------------------------------------

    trainsContainer.innerHTML =
        visible
            .map(train =>
                renderTrain(
                    train,
                    selectedDate
                )
            )
            .join("");


    // --------------------------------------------------------
    // EXPANDIR
    // --------------------------------------------------------

    document
        .querySelectorAll(".train")
        .forEach(trainElement => {

            trainElement.addEventListener(
                "click",
                () => {

                    trainElement.classList.toggle(
                        "expanded"
                    );

                }
            );

        });
}


// ============================================================
// LOAD DATA
// ============================================================

async function loadData() {

    const date =
        dateInput.value;

    if (!date) {
        return;
    }

    trainsContainer.innerHTML = `

        <p class="loading">
            Carregant dades...
        </p>

    `;


    try {

        const response =
            await fetch(
                `data/${date}.json?t=${Date.now()}`
            );


        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        currentData =
            data;


        render(data);


        console.log(
            "R15 Tracker:",
            data.trains?.length || 0,
            "trens carregats"
        );


    } catch (error) {

        console.error(
            "Error carregant dades:",
            error
        );


        trainsContainer.innerHTML = `

            <div class="error">

                ❌ No s'han pogut carregar
                les dades d'aquest dia.

            </div>

        `;
    }
}


// ============================================================
// HISTORY
// ============================================================

toggleHistoryButton.addEventListener(
    "click",
    () => {

        showHistory =
            !showHistory;


        if (showHistory) {

            toggleHistoryButton.textContent =
                "← Tornar als trens actuals";

            toggleHistoryButton.classList.add(
                "active"
            );

        } else {

            toggleHistoryButton.textContent =
                "Consultar trens ja arribats";

            toggleHistoryButton.classList.remove(
                "active"
            );

        }


        if (currentData) {
            render(currentData);
        }

    }
);


// ============================================================
// CONTROLS
// ============================================================

directionSelect.addEventListener(
    "change",
    loadData
);


dateInput.addEventListener(
    "change",
    loadData
);


// ============================================================
// INIT
// ============================================================

dateInput.value =
    getTodayString();

loadData();


// ============================================================
// AUTO REFRESH
// ============================================================

setInterval(
    loadData,
    60 * 1000
);
