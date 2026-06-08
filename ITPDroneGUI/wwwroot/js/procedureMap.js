const states = new WeakMap();

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

function normalizeOptions(options) {
    return {
        initialWidth: clamp(Number(options?.initialWidth) || 300, 240, 760),
        initialHeight: clamp(Number(options?.initialHeight) || 266, 210, 620),
        minWidth: Number(options?.minWidth) || 240,
        minHeight: Number(options?.minHeight) || 210,
        maxWidth: Number(options?.maxWidth) || 760,
        maxHeight: Number(options?.maxHeight) || 620,
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
}

function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}
