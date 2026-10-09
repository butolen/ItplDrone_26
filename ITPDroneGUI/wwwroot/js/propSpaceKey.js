// Spacebar as a software twin of the hardware prop button (press_on_button, PD2).
// The firmware sends one "BTN" per debounced press, so one keypress is one spin:
// auto-repeat while the key is held is dropped.

let state = null;

export function register(dotNet) {
    unregister();

    const onKeyDown = event => {
        if (!isSpace(event)) {
            return;
        }

        // Auto-repeat would queue dozens of presses per second; the button cannot.
        if (event.repeat) {
            return;
        }

        if (event.ctrlKey || event.altKey || event.metaKey) {
            return;
        }

        // Typing a space stays typing, and a focused button keeps its native
        // space-activates-click behaviour instead of spinning twice.
        if (isTypingTarget(event.target) || isActivatableTarget(event.target)) {
            return;
        }

        // No page scroll.
        event.preventDefault();
        dotNet.invokeMethodAsync("OnSpacebarPressed");
    };

    state = { dotNet, onKeyDown };
    document.addEventListener("keydown", onKeyDown);
}

export function unregister() {
    if (!state) {
        return;
    }

    document.removeEventListener("keydown", state.onKeyDown);
    state = null;
}

function isSpace(event) {
    return event.code === "Space" || event.key === " " || event.key === "Spacebar";
}

function isTypingTarget(target) {
    if (!target) {
        return false;
    }

    if (target.isContentEditable) {
        return true;
    }

    return target.tagName === "INPUT"
        || target.tagName === "TEXTAREA"
        || target.tagName === "SELECT";
}

function isActivatableTarget(target) {
    if (!target || !target.closest) {
        return false;
    }

    return target.closest("button, a[href], [role=button]") !== null;
}
