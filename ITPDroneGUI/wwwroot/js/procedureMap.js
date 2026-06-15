const states = new WeakMap();
const mapStates = new WeakMap();

export function initializeResize(card, handle, dotNet, options) {
    if (!card || !handle) {
        return;
    }

    disposeResize(card);

    const state = {
        card,
        handle,
        dotNet,
        options: normalizeOptions(options),
        active: false,
        pointerId: null,
        width: 0,
        height: 0,
        startX: 0,
        startY: 0,
        startWidth: 0,
        startHeight: 0,
        onPointerDown: null,
        onPointerMove: null,
        onPointerUp: null,
        onMouseDown: null,
        onMouseMove: null,
        onMouseUp: null,
        isMouseDrag: false,
    };

    applySize(state, state.options.initialWidth, state.options.initialHeight);

    state.onPointerDown = event => beginResize(state, event);
    state.onPointerMove = event => resize(state, event);
    state.onPointerUp = event => endResize(state, event);
    state.onMouseDown = event => beginResize(state, event);
    state.onMouseMove = event => resize(state, event);
    state.onMouseUp = event => endResize(state, event);

    handle.addEventListener("pointerdown", state.onPointerDown);
    handle.addEventListener("mousedown", state.onMouseDown);
    document.addEventListener("pointermove", state.onPointerMove);
    document.addEventListener("pointerup", state.onPointerUp);
    document.addEventListener("pointercancel", state.onPointerUp);
    document.addEventListener("mousemove", state.onMouseMove);
    document.addEventListener("mouseup", state.onMouseUp);
    card.dataset.gpsResizeReady = "true";
    states.set(card, state);
}

export function disposeResize(card) {
    const state = states.get(card);
    if (!state) {
        return;
    }

    state.handle.removeEventListener("pointerdown", state.onPointerDown);
    state.handle.removeEventListener("mousedown", state.onMouseDown);
    document.removeEventListener("pointermove", state.onPointerMove);
    document.removeEventListener("pointerup", state.onPointerUp);
    document.removeEventListener("pointercancel", state.onPointerUp);
    document.removeEventListener("mousemove", state.onMouseMove);
    document.removeEventListener("mouseup", state.onMouseUp);
    document.body.classList.remove("gps-map-resizing");
    delete card.dataset.gpsResizeReady;
    states.delete(card);
}

export function initializeRouteMap(element, dotNet, options) {
    if (!element || typeof L === "undefined") {
        return;
    }

    disposeRouteMap(element);

    const center = [
        Number(options?.latitude) || 48.411008,
        Number(options?.longitude) || 15.593409,
    ];

    const map = L.map(element, {
        zoomControl: true,
        attributionControl: false,
    }).setView(center, Number(options?.zoom) || 17);

    const satellite = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
            maxZoom: 20,
        });

    const streets = L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 19,
        });

    satellite.addTo(map);

    const routeLayer = L.layerGroup().addTo(map);
    const droneLayer = L.layerGroup().addTo(map);
    const state = { map, routeLayer, droneLayer, polyline: null, routeBounds: null };
    mapStates.set(element, state);

    map.on("click", event => {
        dotNet?.invokeMethodAsync("AddRoutePointFromMap", event.latlng.lat, event.latlng.lng).catch(() => {});
    });

    refreshMapSize(state);
    setTimeout(() => refreshMapSize(state), 250);
}

export function updateRouteMap(element, routePoints, dronePosition, fitRoute) {
    const state = mapStates.get(element);
    if (!state) {
        return;
    }

    const points = Array.isArray(routePoints) ? routePoints : [];
    state.routeLayer.clearLayers();

    const latLngs = points
        .map(point => [Number(point.latitude), Number(point.longitude)])
        .filter(point => Number.isFinite(point[0]) && Number.isFinite(point[1]));

    if (latLngs.length > 0) {
        state.routeBounds = L.latLngBounds(latLngs);
        state.polyline = L.polyline(latLngs, {
            color: "#38bdf8",
            weight: 4,
            opacity: 0.95,
        }).addTo(state.routeLayer);

        latLngs.forEach((latLng, index) => {
            L.circleMarker(latLng, {
                radius: 7,
                color: "#ffffff",
                weight: 2,
                fillColor: "#0ea5e9",
                fillOpacity: 0.95,
            })
                .bindTooltip(String(index + 1), { permanent: true, direction: "center", className: "route-point-label" })
                .addTo(state.routeLayer);
        });

        if (fitRoute) {
            fitRouteBounds(state);
        }
    } else {
        state.routeBounds = null;
    }

    state.droneLayer.clearLayers();
    const droneLatitude = Number(dronePosition?.latitude);
    const droneLongitude = Number(dronePosition?.longitude);
    if (Number.isFinite(droneLatitude) && Number.isFinite(droneLongitude) && droneLatitude !== 0 && droneLongitude !== 0) {
        const marker = L.circleMarker([droneLatitude, droneLongitude], {
            radius: 8,
            color: "#ffffff",
            weight: 2,
            fillColor: "#22c55e",
            fillOpacity: 1,
        }).addTo(state.droneLayer);
        marker.bindTooltip("DRONE", { direction: "top" });

        if (latLngs.length === 0 && fitRoute) {
            state.map.setView([droneLatitude, droneLongitude], Math.max(state.map.getZoom(), 17));
        }
    }

    refreshMapSize(state);
}

export function centerRouteMapOnDrone(element, dronePosition) {
    const state = mapStates.get(element);
    if (!state) {
        return;
    }

    const droneLatitude = Number(dronePosition?.latitude);
    const droneLongitude = Number(dronePosition?.longitude);
    if (!Number.isFinite(droneLatitude) || !Number.isFinite(droneLongitude) || droneLatitude === 0 || droneLongitude === 0) {
        return;
    }

    state.map.setView([droneLatitude, droneLongitude], Math.max(state.map.getZoom(), 18));
    refreshMapSize(state);
}

export function disposeRouteMap(element) {
    const state = mapStates.get(element);
    if (!state) {
        return;
    }

    state.map.remove();
    mapStates.delete(element);
}

function normalizeOptions(options) {
    const minWidth = Number(options?.minWidth) || 240;
    const minHeight = Number(options?.minHeight) || 210;
    const maxWidth = Number(options?.maxWidth) || 760;
    const maxHeight = Number(options?.maxHeight) || 620;

    return {
        initialWidth: clamp(Number(options?.initialWidth) || 300, minWidth, maxWidth),
        initialHeight: clamp(Number(options?.initialHeight) || 266, minHeight, maxHeight),
        minWidth,
        minHeight,
        maxWidth,
        maxHeight,
    };
}

function beginResize(state, event) {
    const isMouseDrag = event.type.startsWith("mouse");
    if (event.button !== 0 || (!isMouseDrag && event.isPrimary === false)) {
        return;
    }

    const rect = state.card.getBoundingClientRect();
    state.active = true;
    state.pointerId = isMouseDrag ? "mouse" : event.pointerId;
    state.isMouseDrag = isMouseDrag;
    state.startX = event.clientX;
    state.startY = event.clientY;
    state.startWidth = rect.width;
    state.startHeight = rect.height;
    state.width = rect.width;
    state.height = rect.height;

    event.preventDefault();
    event.stopPropagation();
    if (!isMouseDrag) {
        state.handle.setPointerCapture?.(event.pointerId);
    }
    document.body.classList.add("gps-map-resizing");
}

function resize(state, event) {
    if (!state.active || !isActiveResizeEvent(state, event)) {
        return;
    }

    event.preventDefault();
    const maxWidth = Math.min(state.options.maxWidth, Math.max(state.options.minWidth, window.innerWidth - 40));
    const maxHeight = Math.min(state.options.maxHeight, Math.max(state.options.minHeight, window.innerHeight - 88));
    const width = clamp(state.startWidth + state.startX - event.clientX, state.options.minWidth, maxWidth);
    const height = clamp(state.startHeight + state.startY - event.clientY, state.options.minHeight, maxHeight);
    applySize(state, width, height);
}

function endResize(state, event) {
    if (!state.active || !isActiveResizeEvent(state, event)) {
        return;
    }

    state.active = false;
    state.pointerId = null;
    if (!state.isMouseDrag) {
        state.handle.releasePointerCapture?.(event.pointerId);
    }
    state.isMouseDrag = false;
    document.body.classList.remove("gps-map-resizing");
    state.dotNet?.invokeMethodAsync("SetGpsMapSizeFromBrowser", state.width, state.height).catch(() => {});
}

function isActiveResizeEvent(state, event) {
    if (state.isMouseDrag) {
        return event.type.startsWith("mouse");
    }

    return event.pointerId === state.pointerId;
}

function applySize(state, width, height) {
    state.width = width;
    state.height = height;
    state.card.style.width = `${Math.round(width)}px`;
    state.card.style.height = `${Math.round(height)}px`;

    const mapElement = state.card.querySelector(".gps-map");
    const mapState = mapElement ? mapStates.get(mapElement) : null;
    if (mapState) {
        setTimeout(() => {
            refreshMapSize(mapState);
            if (mapState.routeBounds) {
                fitRouteBounds(mapState);
            }
        }, 30);
    }
}

function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

function refreshMapSize(state) {
    setTimeout(() => {
        state.map.invalidateSize({ pan: false });
    }, 20);
}

function fitRouteBounds(state) {
    if (!state.routeBounds) {
        return;
    }

    if (state.routeBounds.getNorthEast().equals(state.routeBounds.getSouthWest())) {
        state.map.setView(state.routeBounds.getCenter(), Math.max(state.map.getZoom(), 18));
        return;
    }

    state.map.fitBounds(state.routeBounds.pad(0.22), { maxZoom: 19 });
}
