(() => {
const states = new WeakMap();
let activeDrag = null;

function initialize(container, dotNet, options) {
    if (!container) {
        return;
    }

    let state = states.get(container);
    if (state) {
        state.dotNet = dotNet;
        state.options = normalizeOptions(options);
        container.dataset.sortableDisabled = String(state.options.disabled);
        return;
    }

    state = {
        container,
        dotNet,
        options: normalizeOptions(options),
        onContainerPointerDown: null,
        onDocumentPointerDown: null,
        onPointerMove: null,
        onPointerUp: null,
    };

    state.onContainerPointerDown = event => beginInternalDrag(state, event);
    state.onDocumentPointerDown = event => beginExternalDrag(state, event);
    state.onPointerMove = event => updateDrag(event);
    state.onPointerUp = event => finishDrag(event);

    container.addEventListener("pointerdown", state.onContainerPointerDown);
    document.addEventListener("pointerdown", state.onDocumentPointerDown);
    document.addEventListener("pointermove", state.onPointerMove);
    document.addEventListener("pointerup", state.onPointerUp);
    document.addEventListener("pointercancel", state.onPointerUp);

    container.dataset.sortableDisabled = String(state.options.disabled);
    states.set(container, state);
}

function dispose(container) {
    const state = states.get(container);
    if (!state) {
        return;
    }

    container.removeEventListener("pointerdown", state.onContainerPointerDown);
    document.removeEventListener("pointerdown", state.onDocumentPointerDown);
    document.removeEventListener("pointermove", state.onPointerMove);
    document.removeEventListener("pointerup", state.onPointerUp);
    document.removeEventListener("pointercancel", state.onPointerUp);
    states.delete(container);
}

function normalizeOptions(options) {
    return {
        disabled: Boolean(options?.disabled),
        externalSelector: options?.externalSelector || "[data-sortable-template-kind]",
        externalDataAttribute: options?.externalDataAttribute || "sortableTemplateKind",
        placeholderClass: options?.placeholderClass || "sortable-placeholder",
    };
}

function beginInternalDrag(state, event) {
    if (!canStartDrag(state, event) || activeDrag) {
        return;
    }

    const item = event.target.closest("[data-sortable-item]");
    if (!item || !state.container.contains(item) || isInteractive(event.target)) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    activeDrag = {
        state,
        type: "internal",
        pointerId: event.pointerId,
        source: item,
        payload: item.dataset.sortableKey || "",
        oldIndex: sortableItems(state.container).indexOf(item),
        startX: event.clientX,
        startY: event.clientY,
        offsetX: event.clientX - item.getBoundingClientRect().left,
        offsetY: event.clientY - item.getBoundingClientRect().top,
        started: false,
        originalDisplay: item.style.display,
    };

    item.setPointerCapture?.(event.pointerId);
}

function beginExternalDrag(state, event) {
    if (!canStartDrag(state, event) || activeDrag || state.container.contains(event.target)) {
        return;
    }

    const source = event.target.closest(state.options.externalSelector);
    if (!source || isInteractive(event.target)) {
        return;
    }

    const payload = source.dataset[state.options.externalDataAttribute];
    if (!payload) {
        return;
    }

    event.preventDefault();
    event.stopPropagation();

    activeDrag = {
        state,
        type: "external",
        pointerId: event.pointerId,
        source,
        payload,
        oldIndex: -1,
        startX: event.clientX,
        startY: event.clientY,
        offsetX: event.clientX - source.getBoundingClientRect().left,
        offsetY: event.clientY - source.getBoundingClientRect().top,
        started: false,
    };

    source.setPointerCapture?.(event.pointerId);
}

function canStartDrag(state, event) {
    return !state.options.disabled && event.button === 0 && event.isPrimary !== false;
}

function updateDrag(event) {
    const drag = activeDrag;
    if (!drag || event.pointerId !== drag.pointerId) {
        return;
    }

    if (!drag.started) {
        const dx = event.clientX - drag.startX;
        const dy = event.clientY - drag.startY;
        if ((dx * dx) + (dy * dy) < 36) {
            return;
        }

        startVisualDrag(drag);
    }

    event.preventDefault();
    moveGhost(drag, event.clientX, event.clientY);
    updatePlaceholder(drag, event.clientX, event.clientY);
}

async function finishDrag(event) {
    const drag = activeDrag;
    if (!drag || event.pointerId !== drag.pointerId) {
        return;
    }

    activeDrag = null;

    if (!drag.started) {
        cleanupDrag(drag);
        return;
    }

    const newIndex = placeholderIndex(drag);
    const dropped = newIndex >= 0 && drag.placeholder?.parentElement === drag.state.container;
    cleanupDrag(drag);

    if (!dropped) {
        return;
    }

    if (drag.type === "external") {
        await drag.state.dotNet.invokeMethodAsync("NotifyExternalDrop", drag.payload, newIndex);
        return;
    }

    if (drag.oldIndex !== newIndex) {
        await drag.state.dotNet.invokeMethodAsync("NotifyMove", drag.payload, drag.oldIndex, newIndex);
    }
}

function startVisualDrag(drag) {
    const rect = drag.source.getBoundingClientRect();
    const ghost = drag.source.cloneNode(true);
    const placeholder = document.createElement("div");

    ghost.classList.add("sortable-drag-ghost");
    ghost.style.position = "fixed";
    ghost.style.left = `${rect.left}px`;
    ghost.style.top = `${rect.top}px`;
    ghost.style.width = `${rect.width}px`;
    ghost.style.height = `${rect.height}px`;
    ghost.style.pointerEvents = "none";

    placeholder.className = drag.state.options.placeholderClass;
    placeholder.style.width = `${rect.width}px`;
    placeholder.style.height = `${rect.height}px`;

    drag.ghost = ghost;
    drag.placeholder = placeholder;
    drag.started = true;

    document.body.appendChild(ghost);
    document.body.classList.add("sortable-dragging");

    const empty = drag.state.container.querySelector(":scope > [data-sortable-empty]");
    if (empty) {
        drag.emptyElement = empty;
        empty.style.display = "none";
    }

    if (drag.type === "internal") {
        drag.source.parentElement.insertBefore(placeholder, drag.source);
        drag.source.style.display = "none";
    }
}

function moveGhost(drag, clientX, clientY) {
    if (!drag.ghost) {
        return;
    }

    drag.ghost.style.left = `${clientX - drag.offsetX}px`;
    drag.ghost.style.top = `${clientY - drag.offsetY}px`;
}

function updatePlaceholder(drag, clientX, clientY) {
    const container = drag.state.container;
    const bounds = container.getBoundingClientRect();
    const isInside =
        clientX >= bounds.left - 80 &&
        clientX <= bounds.right + 80 &&
        clientY >= bounds.top - 80 &&
        clientY <= bounds.bottom + 80;

    if (!isInside) {
        if (drag.type === "external") {
            drag.placeholder?.remove();
        }
        return;
    }

    const items = sortableItems(container).filter(item => item !== drag.source && item.style.display !== "none");
    const before = items.find(item => {
        const rect = item.getBoundingClientRect();
        return clientY < rect.top + (rect.height / 2);
    });

    if (before) {
        container.insertBefore(drag.placeholder, before);
    } else {
        container.appendChild(drag.placeholder);
    }
}

function placeholderIndex(drag) {
    if (!drag.placeholder) {
        return -1;
    }

    return Array
        .from(drag.state.container.children)
        .filter(child => child === drag.placeholder || (child.hasAttribute("data-sortable-item") && child !== drag.source))
        .indexOf(drag.placeholder);
}

function cleanupDrag(drag) {
    drag.ghost?.remove();
    drag.placeholder?.remove();
    document.body.classList.remove("sortable-dragging");

    if (drag.source && drag.type === "internal") {
        drag.source.style.display = drag.originalDisplay || "";
    }

    if (drag.emptyElement) {
        drag.emptyElement.style.display = "";
    }
}

function sortableItems(container) {
    return Array.from(container.querySelectorAll(":scope > [data-sortable-item]"));
}

function isInteractive(target) {
    return Boolean(target.closest("input, select, textarea, button, a, label, [contenteditable='true']"));
}

window.droneForgeSortableList = {
    initialize,
    dispose,
};
})();
