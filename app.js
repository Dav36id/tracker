```javascript
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
    if (value === undefined || value === null || value === "") {
        return null;
    }

    if (typeof value === "number" && Number.isFinite(value)) {
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
    const match = stringValue.match(/^(\d{1,2}):(\d{2})/);

    if (match) {
        return Number(match[1]) * 60 + Number(match[2]);
    }

    const date = new Date(stringValue);

    if (!Number.isNaN(date.getTime())) {
        return date.getHours() * 60 + date.getMinutes();
    }

    return null;
}

function formatTime(value) {
    const minutes = parseTimeToMinutes(value);

    if (minutes === null) {
        return "--:--";
    }

    const normalized = ((minutes % 1440) + 1440) % 1440;
    const hours = Math.floor(normalized / 60);
    const mins = Math.floor(normalized % 60);

    return (
        String(hours).padStart(2, "0") +
        ":" +
        String(mins).padStart(2, "0")
    );
}

function getNowMinutes() {
    const now = new Date();
    return now.getHours() * 60 + now.getMinutes();
}

// ============================================================
// DELAY
// ============================================================

function getDelayMinutes(stop) {
    if (!stop) {
        return null;
    }

    const fields = [
        "delay_minutes",
        "realtime_delay_minutes"
    ];

    for (const field of fields) {
        if (stop[field] !== undefined && stop[field] !== null) {
            const value = Number(stop[field]);

            if (Number.isFinite(value)) {
                return Math.round(value);
            }
        }
    }

    if (stop.delay_seconds !== undefined && stop.delay_seconds !== null) {
        const value = Number(stop.delay_seconds);
        return Number.isFinite(value) ? Math.round(value / 60) : null;
    }

    if (stop.delay !== undefined && stop.delay !== null) {
        const value = Number(stop.delay);
        return Number.isFinite(value) ? Math.round(value) : null;
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

    if (stop.scheduled_arrival !== undefined &&
        stop.scheduled_arrival !== null) {
        return stop.scheduled_arrival;
    }

    if (stop.scheduled_departure !== undefined &&
        stop.scheduled_departure !== null) {
        return stop.scheduled_departure;
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

    if (stop.actual_minutes !== undefined &&
        stop.actual_minutes !== null) {
        return stop.actual_minutes;
    }

    if (stop.actual_time !== undefined &&
        stop.actual_time !== null) {
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

    if (train.departure !== undefined && train.departure !== null) {
        return train.departure;
    }

    if (Array.isArray(train.stops) && train.stops.length > 0) {
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

    if (train.arrival !== undefined && train.arrival !== null) {
        return train.arrival;
    }

    if (Array.isArray(train.stops) && train.stops.length > 0) {
        const lastStop = train.stops[train.stops.length - 1];

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
    if (!train || !Array.isArray(train.stops) || train.stops.length === 0) {
        return null;
    }

    return train.stops[train.stops.length - 1];
}

// ============================================================
// ACTUAL ARRIVAL
// ============================================================

function getActualArrivalMinutes(train) {
    const lastStop = getLastStop(train);

    if (!lastStop) {
        return null;
    }

    const actual = getRealtimeTime(lastStop);

    if (actual === null || actual === undefined || actual === "") {
        return null;
    }

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
        const value = Number(train.final_delay_minutes);
        return Number.isFinite(value) ? Math.round(value) : 0;
    }

    if (
        train.realtime_trip_delay_minutes !== undefined &&
        train.realtime_trip_delay_minutes !== null
    ) {
        const value = Number(train.realtime_trip_delay_minutes);
        return Number.isFinite(value) ? Math.round(value) : 0;
    }

    const delay = getDelayMinutes(getLastStop(train));

    return delay !== null ? delay : 0;
}

// ============================================================
// DATE HELPERS
// ============================================================

function isSelectedDateToday(selectedDate) {
    return selectedDate === getTodayString();
}

function isSelectedDatePast(selectedDate) {
    return selectedDate < getTodayString();
}

// ============================================================
// ARRIVED?
// ============================================================

function hasTrainArrived(train, selectedDate) {
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

    // Les trens d'un dia anterior es consideren històrics.
    if (isSelectedDatePast(selectedDate)) {
        return true;
    }

    // Un tren d'una data futura no ha pogut arribar encara.
    if (selectedDate > getTodayString()) {
        return false;
    }

    // Per a avui, només usem una hora real de l'última parada.
    // No fem desaparèixer el tren només perquè passe l'hora teòrica.
    const actualArrival = getActualArrivalMinutes(train);

    if (actualArrival !== null) {
        return actualArrival <= getNowMinutes();
    }

    // Sense informació real, no podem confirmar l'arribada.
    return false;
}

// ============================================================
// DEPARTED?
// ============================================================

function hasTrainDeparted(train, selectedDate) {
    if (!train) {
        return false;
    }

    if (train.started === true) {
        return true;
    }

    if (selectedDate > getTodayString()) {
        return false;
    }

    if (isSelectedDatePast(selectedDate)) {
        return true;
    }

    const departureMinutes = parseTimeToMinutes(getDepartureTime(train));

    if (departureMinutes === null) {
        return false;
    }

    return departureMinutes <= getNowMinutes();
}

// ============================================================
// STATUS
// ============================================================

function getTrainStatus(train, selectedDate) {
    const arrived = hasTrainArrived(train, selectedDate);
    const departed = hasTrainDeparted(train, selectedDate);
    const delay = getFinalDelay(train);

    if (arrived) {
        return delay > 15 ? "late" : "finished";
    }

    if (!departed) {
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


function getStatusText(status, train) {
    const delay = getFinalDelay(train);

    if (status === "pending") {
        return "Encara no ha sortit";
    }

    if (status === "running") {
        if (delay > 0) {
            return "En circulació · +" + delay + " min";
        }
        return "En circulació · en hora";
    }

    if (status === "warning") {
        return "En circulació · +" + delay + " min";
    }

    if (status === "late") {
        return "Arribat · +" + delay + " min";
    }

    if (status === "finished") {
        return "Arribat";
    }

    return "";
}

// ============================================================
// TRAIN ID
// ============================================================

function getTrainId(train) {
    const id =
        train.train_id ||
        train.trip_id ||
        train.id ||
        train.tripId ||
        "Tren";

    const match = String(id).match(/^5187V(.+)R15$/);

    if (match) {
        return match[1];
    }

    const alternateMatch = String(id).match(/^5174S(.+)R15$/);

    if (alternateMatch) {
        return alternateMatch[1];
    }

    return id;
}

// ============================================================
// DIRECTION FILTER
// ============================================================

function normalizeDirection(value) {
    return String(value || "")
        .trim()
        .toUpperCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[\s-]+/g, "_");
}

function trainMatchesDirection(train, selectedDirection) {
    const direction = normalizeDirection(selectedDirection);

    const trainDirection = normalizeDirection(
        train.direction ||
        train.route_direction ||
        train.direction_code ||
        ""
    );

    // Si no tenim direcció, no descartem el tren automàticament.
    if (!trainDirection) {
        return true;
    }

    // El selector BAR_REUS significa Barcelona → Reus.
    // Les dades GTFS identifiquen aquests trens amb direction "Reus".
    if (direction === "BAR_REUS") {
        return trainDirection === "REUS";
    }

    // El selector REUS_BAR significa Reus → Barcelona.
    if (direction === "REUS_BAR") {
        return trainDirection === "BARCELONA";
    }

    return trainDirection === direction;
}

// ============================================================
// RENDER STOPS
// ============================================================

function renderStops(train) {
    if (!Array.isArray(train.stops) || train.stops.length === 0) {
        return `
            <div class="stops">
                <p class="no-stops">No hi ha informació de parades.</p>
            </div>
        `;
    }

    let html = `
        <div class="stops">
            <div class="stops-title">Parades</div>

            <div class="stops-header">
                <div class="stop-header-station">Estació</div>
                <div class="stop-header-theoretical">Teòrica</div>
                <div class="stop-header-real">Real</div>
                <div class="stop-header-delay">Retard</div>
            </div>
    `;

    for (const stop of train.stops) {
        const station = getStationName(stop);
        const theoretical = getTheoreticalTime(stop);
        const realtime = getRealtimeTime(stop);
        const delay = getDelayMinutes(stop);

        let realHtml = "";

        if (realtime !== null && realtime !== undefined) {
            realHtml = `
                <div class="real-cell">
                    <span class="actual-time">${formatTime(realtime)}</span>
                    <span class="time-label real-label">real</span>
                </div>
            `;
        } else if (theoretical !== null && delay !== null) {
            const theoreticalMinutes = parseTimeToMinutes(theoretical);
            const estimatedMinutes =
                theoreticalMinutes !== null
                    ? theoreticalMinutes + delay
                    : null;

            realHtml = estimatedMinutes !== null
                ? `
                    <div class="real-cell">
                        <span class="estimated-time">${formatTime(estimatedMinutes)}</span>
                        <span class="time-label estimated-label">estimada</span>
                    </div>
                `
                : `
                    <div class="real-cell">
                        <span class="no-real-time">—</span>
                    </div>
                `;
        } else {
            realHtml = `
                <div class="real-cell">
                    <span class="no-real-time">—</span>
                </div>
            `;
        }

        let delayHtml = "—";

        if (delay !== null && delay !== 0) {
            const prefix = delay > 0 ? "+" : "";

            delayHtml = `
                <span class="stop-delay">${prefix}${delay} min</span>
            `;
        }

        html += `
            <div class="stop-row">
                <div class="stop-name">${station}</div>

                <div class="theoretical-cell">
                    <span class="theoretical-time">${formatTime(theoretical)}</span>
                </div>

                ${realHtml}

                <div class="delay-cell">${delayHtml}</div>
            </div>
        `;
    }

    html += `</div>`;

    return html;
}

// ============================================================
// RENDER TRAIN
// ============================================================

function renderTrain(train, selectedDate) {
    const status = getTrainStatus(train, selectedDate);
    const delay = getFinalDelay(train);
    const trainId = getTrainId(train);
    const departure = getDepartureTime(train);
    const arrival = getArrivalTime(train);
    const statusText = getStatusText(status, train);
    const expressRefund = delay > 15;

    return `
        <article class="train ${status}" data-train-id="${trainId}">
            <div class="train-main">
                <div class="train-left">
                    <div class="train-id">🚆 ${trainId}</div>

                    <div class="train-route">
                        <span>${formatTime(departure)}</span>
                        <span class="arrow">→</span>
                        <span>${formatTime(arrival)}</span>
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
                                    Sí es pot sol·licitar devolució express
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

function renderSummary(total, visible, arrived) {
    summaryContainer.innerHTML = `
        <div class="summary">
            <strong>${visible}</strong>
            trens mostrats
            ${
                showHistory
                    ? ` · ${arrived} trens arribats`
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

    const selectedDate = dateInput.value;

    let trains = Array.isArray(data.trains)
        ? data.trains
        : Array.isArray(data.circulations)
            ? data.circulations
            : [];

    // FILTRE PER DIRECCIÓ
    const direction = directionSelect.value;

    trains = trains.filter(train =>
        trainMatchesDirection(train, direction)
    );

    // FILTRE D'ARRIBADES
    let visible;

    if (!showHistory) {
        visible = trains.filter(train =>
            !hasTrainArrived(train, selectedDate)
        );
    } else {
        visible = trains.filter(train =>
            hasTrainArrived(train, selectedDate)
        );
    }

    // ORDRE PER HORA DE SORTIDA
    visible.sort((a, b) => {
        const timeA = parseTimeToMinutes(getDepartureTime(a)) ?? 9999;
        const timeB = parseTimeToMinutes(getDepartureTime(b)) ?? 9999;

        return timeA - timeB;
    });

    const arrivedCount = trains.filter(train =>
        hasTrainArrived(train, selectedDate)
    ).length;

    renderSummary(trains.length, visible.length, arrivedCount);

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

    trainsContainer.innerHTML = visible
        .map(train => renderTrain(train, selectedDate))
        .join("");

    document.querySelectorAll("#trains .train").forEach(trainElement => {
        trainElement.addEventListener("click", () => {
            trainElement.classList.toggle("expanded");
        });
    });
}

// ============================================================
// LOAD DATA
// ============================================================

async function loadData() {
    const date = dateInput.value;

    if (!date) {
        return;
    }

    trainsContainer.innerHTML = `
        <p class="loading">Carregant dades...</p>
    `;

    try {
        const response = await fetch(
            `data/${date}.json?t=${Date.now()}`
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        currentData = data;
        render(data);

        console.log(
            "R15 Tracker:",
            Array.isArray(data.trains) ? data.trains.length : 0,
            "trens carregats"
        );
    } catch (error) {
        console.error("Error carregant dades:", error);

        trainsContainer.innerHTML = `
            <div class="error">
                ❌ No s'han pogut carregar les dades d'aquest dia.
            </div>
        `;
    }
}

// ============================================================
// HISTORY
// ============================================================

toggleHistoryButton.addEventListener("click", () => {
    showHistory = !showHistory;

    if (showHistory) {
        toggleHistoryButton.textContent = "← Tornar als trens actuals";
        toggleHistoryButton.classList.add("active");
    } else {
        toggleHistoryButton.textContent = "Consultar trens ja arribats";
        toggleHistoryButton.classList.remove("active");
    }

    if (currentData) {
        render(currentData);
    }
});

// ============================================================
// CONTROLS
// ============================================================

directionSelect.addEventListener("change", loadData);
dateInput.addEventListener("change", loadData);

// ============================================================
// INIT
// ============================================================

dateInput.value = getTodayString();
loadData();

// ============================================================
// AUTO REFRESH
// ============================================================

setInterval(loadData, 60 * 1000);
```
