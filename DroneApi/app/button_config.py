from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_SERIAL_PORT = "COM4"
DEFAULT_BAUD_RATE = 115200


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ButtonConfig:
    serial_port: str = DEFAULT_SERIAL_PORT
    baud_rate: int = DEFAULT_BAUD_RATE
    flight_mode: str = "STABILIZE"
    # Every press adds 1/press_steps to the throttle level (0..1).
    press_steps: int = 20
    # A press holds the level this long, then it halves every decay_half_life_seconds.
    press_hold_seconds: float = 0.3
    decay_half_life_seconds: float = 0.3
    # A level just above 0 maps to min_throttle_pwm (in STABILIZE throttle drives the
    # motors directly, so the first press is clearly visible), level 1 to max_throttle_pwm.
    min_throttle_pwm: int = 1300
    max_throttle_pwm: int = 2000
    loop_hz: float = 50.0
    arm_retry_seconds: float = 2.0
    disable_auto_disarm: bool = True
    force_arm: bool = False
    dry_run: bool = False
    open_settle_seconds: float = 2.0
    heartbeat_timeout_seconds: float = 3.0
    reconnect_interval_seconds: float = 2.0
    read_timeout_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> ButtonConfig:
        return cls(
            serial_port=os.getenv("BUTTON_SERIAL_PORT", DEFAULT_SERIAL_PORT),
            baud_rate=int(os.getenv("BUTTON_BAUD_RATE", str(DEFAULT_BAUD_RATE))),
            flight_mode=os.getenv("BUTTON_FLIGHT_MODE", "STABILIZE"),
            press_steps=int(os.getenv("BUTTON_PRESS_STEPS", "20")),
            press_hold_seconds=float(os.getenv("BUTTON_PRESS_HOLD_SECONDS", "0.3")),
            decay_half_life_seconds=float(os.getenv("BUTTON_DECAY_HALF_LIFE_SECONDS", "0.3")),
            min_throttle_pwm=int(os.getenv("BUTTON_MIN_THROTTLE_PWM", "1300")),
            max_throttle_pwm=int(os.getenv("BUTTON_MAX_THROTTLE_PWM", "2000")),
            disable_auto_disarm=_env_flag("BUTTON_DISABLE_AUTO_DISARM", True),
            force_arm=_env_flag("BUTTON_FORCE_ARM", False),
            dry_run=_env_flag("BUTTON_DRY_RUN", False),
        )
