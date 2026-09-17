from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from DroneApi.app.button_config import ButtonConfig
from DroneApi.app.drone_controller import DroneController

logger = logging.getLogger(__name__)

AUTO_DISARM_PARAM = "DISARM_DELAY"
STATUS_POLL_SECONDS = 0.5


class PropSpinner:
    """Exhibition mode for the push button.

    Every press adds one step to a throttle level (0..1) and keeps it alive for
    press_hold_seconds. A background loop turns the level into RC throttle at
    loop_hz, so mashing the button winds the motors up towards max_throttle_pwm and
    stopping drops them to idle almost at once. The first press arms the drone in
    flight_mode, after that it stays armed.
    request_spin() never blocks.
    """

    def __init__(
        self,
        drone_controller: DroneController,
        config: ButtonConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._drone_controller = drone_controller
        self._config = config
        self._clock = clock
        self._lock = threading.Lock()
        self._level = 0.0
        self._last_press = float("-inf")
        self._last_decay = float("-inf")
        self._presses = 0
        self._armed = False
        self._streaming = False
        self._auto_disarm_disabled = False
        self._next_arm_attempt = 0.0
        self._next_status_poll = 0.0
        self._last_sent_pwm: Optional[int] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="prop-spinner", daemon=True)
        self._thread.start()
        logger.info(
            "[PROPS] loop started: %d steps, %.2f s per press, throttle %d..%d in %s",
            self._config.press_steps,
            self._config.press_hold_seconds,
            self._config.min_throttle_pwm,
            self._config.max_throttle_pwm,
            self._config.flight_mode
        )

    def stop(self) -> None:
        self._stop_event.set()

        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)

        self._thread = None

    def request_spin(self, source: str) -> dict[str, Any]:
        with self._lock:
            self._decay_locked()
            self._level = min(1.0, self._level + 1.0 / self._config.press_steps)
            self._last_press = self._clock()
            self._presses += 1
            level = self._level

        logger.info(
            "[PROPS] press (source=%s): level %.2f -> throttle %d%s",
            source,
            level,
            self.level_to_pwm(level),
            " (dry run)" if self._config.dry_run else ""
        )

        if self._config.dry_run:
            return self._result("dry_run", "Dry run active, no MAVLink commands sent.")

        if not self._drone_controller.is_connected():
            return self._result("not_connected", "Keine aktive MAVLink-Verbindung.")

        return self._result("pressed", "Throttle level raised.")

    def reset(self) -> None:
        with self._lock:
            self._level = 0.0
        self._streaming = False

    def state(self) -> dict[str, Any]:
        with self._lock:
            self._decay_locked()
            level = self._level

        return {
            "level": round(level, 3),
            "throttle_pwm": self.level_to_pwm(level),
            "last_sent_pwm": self._last_sent_pwm,
            "presses": self._presses,
            "armed": self._armed,
            "streaming": self._streaming,
        }

    def level_to_pwm(self, level: float) -> int:
        if level <= 0.0:
            return DroneController.RC_MIN

        span = self._config.max_throttle_pwm - self._config.min_throttle_pwm
        return int(round(self._config.min_throttle_pwm + min(level, 1.0) * span))

    def tick(self) -> None:
        if self._config.dry_run:
            return

        if not self._drone_controller.is_connected():
            self._armed = False
            self._streaming = False
            return

        now = self._clock()
        if now >= self._next_status_poll:
            self._next_status_poll = now + STATUS_POLL_SECONDS
            self._refresh_armed_state()

        # Read after the status refresh: a detected disarm zeroes the level, and a
        # stale level would re-arm the drone right after someone disarmed it.
        with self._lock:
            self._decay_locked()
            level = self._level

        if not self._armed:
            if level > 0 and now >= self._next_arm_attempt:
                self._arm()
            return

        if level > 0:
            self._streaming = True

        if not self._streaming:
            return

        # Same RC_CHANNELS_OVERRIDE path as the GUI joystick (/sim/rc): sticks
        # centred, throttle on CH3. Sent every tick so the override never times out.
        pwm = self.level_to_pwm(level)
        self._drone_controller.send_simulated_rc(
            throttle_pwm=pwm,
            duration_seconds=0.0,
            release_after=False,
        )
        self._last_sent_pwm = pwm

    def _run(self) -> None:
        period = 1.0 / self._config.loop_hz

        while not self._stop_event.is_set():
            started = self._clock()
            try:
                self.tick()
            except Exception:
                logger.exception("[PROPS] loop error")
                self._streaming = False
            self._stop_event.wait(max(0.0, period - (self._clock() - started)))

    def _refresh_armed_state(self) -> None:
        armed = bool(self._drone_controller.get_status().get("armed", False))

        if self._armed and not armed:
            logger.warning("[PROPS] drone reports DISARMED, stopping throttle stream")
            if self._streaming:
                self._drone_controller.release_rc_override()
            self._streaming = False
            with self._lock:
                self._level = 0.0

        self._armed = armed

    def _arm(self) -> None:
        config = self._config

        try:
            if config.disable_auto_disarm and not self._auto_disarm_disabled:
                self._drone_controller.set_param(AUTO_DISARM_PARAM, 0)
                self._auto_disarm_disabled = True
                logger.info("[PROPS] %s=0 sent, autopilot will not auto-disarm", AUTO_DISARM_PARAM)

            if config.force_arm:
                logger.warning(
                    "[PROPS] force_arm is enabled: arming with param2=%d bypasses the pre-arm checks",
                    DroneController.FORCE_ARM_MAGIC
                )

            self._drone_controller.set_mode(config.flight_mode)
            self._drone_controller.arm(force=config.force_arm)
        except Exception:
            logger.exception("[PROPS] arming failed, next try in %.1f s", config.arm_retry_seconds)
            self._next_arm_attempt = self._clock() + config.arm_retry_seconds
            with self._lock:
                self._level = 0.0
            return

        self._armed = True
        self._streaming = True
        self._next_status_poll = self._clock() + STATUS_POLL_SECONDS
        logger.info("[PROPS] armed in %s, staying armed", config.flight_mode)

    def _decay_locked(self) -> None:
        # Each press holds the level for press_hold_seconds. After that it halves
        # every decay_half_life_seconds until it is below half a step, then idles.
        # press_hold_seconds <= 0 disables the decay: the level only goes up.
        config = self._config
        if config.press_hold_seconds <= 0:
            return

        now = self._clock()
        decay_start = max(self._last_press + config.press_hold_seconds, self._last_decay)
        if now <= decay_start:
            return
        self._last_decay = now

        if config.decay_half_life_seconds <= 0:
            self._level = 0.0
            return

        self._level *= 0.5 ** ((now - decay_start) / config.decay_half_life_seconds)
        if self._level < 0.5 / config.press_steps:
            self._level = 0.0

    def _result(self, outcome: str, message: str) -> dict[str, Any]:
        return {
            "success": True,
            "started": outcome == "pressed",
            "outcome": outcome,
            "message": message,
            **self.state(),
        }
