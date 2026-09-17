from __future__ import annotations

from typing import Any, Optional

from DroneApi.app.button_config import ButtonConfig
from DroneApi.app.prop_spinner import PropSpinner


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeDroneController:
    def __init__(self, armed: bool = False, arm_error: Optional[Exception] = None) -> None:
        self.calls: list[str] = []
        self.sent_pwm: list[int] = []
        self.armed = armed
        self.connected = True
        self._arm_error = arm_error

    def is_connected(self) -> bool:
        return self.connected

    def get_status(self) -> dict[str, Any]:
        return {"connected": self.connected, "armed": self.armed}

    def set_param(self, name: str, value: float) -> None:
        self.calls.append(f"param:{name}={value:g}")

    def set_mode(self, mode_name: str) -> None:
        self.calls.append(f"mode:{mode_name}")

    def arm(self, timeout: float = 10.0, force: bool = False) -> None:
        self.calls.append(f"arm:force={force}")
        if self._arm_error is not None:
            raise self._arm_error
        self.armed = True

    def send_simulated_rc(self, throttle_pwm: int, duration_seconds: float, release_after: bool) -> list[int]:
        self.sent_pwm.append(throttle_pwm)
        return []

    def release_rc_override(self) -> None:
        self.calls.append("release")


def build(controller: FakeDroneController, **overrides: Any) -> tuple[PropSpinner, FakeClock]:
    clock = FakeClock()
    return PropSpinner(controller, ButtonConfig(**overrides), clock=clock), clock


def test_press_is_non_blocking_and_only_raises_the_level() -> None:
    controller = FakeDroneController()
    spinner, _ = build(controller)

    result = spinner.request_spin(source="button")

    assert result["outcome"] == "pressed"
    assert result["level"] == 0.05
    assert controller.calls == [], "arming happens in the loop, not in the press"


def test_first_tick_after_press_arms_in_alt_hold_and_streams_throttle() -> None:
    controller = FakeDroneController()
    spinner, _ = build(controller)

    spinner.request_spin(source="button")
    spinner.tick()

    assert controller.calls == ["param:DISARM_DELAY=0", "mode:STABILIZE", "arm:force=False"]
    spinner.tick()
    assert controller.sent_pwm == [1335], "one press = level 0.05 -> 1300 + 0.05 * 700"


def test_each_press_adds_a_step_up_to_the_ceiling() -> None:
    controller = FakeDroneController(armed=True)
    spinner, _ = build(controller)

    levels = [spinner.request_spin(source="button")["level"] for _ in range(25)]

    assert levels[:3] == [0.05, 0.1, 0.15]
    assert levels[-1] == 1.0
    spinner.tick()
    assert controller.sent_pwm[-1] == 2000


def test_level_holds_then_halves_back_to_idle() -> None:
    controller = FakeDroneController(armed=True)
    spinner, clock = build(controller)

    for _ in range(20):
        spinner.request_spin(source="button")
    spinner.tick()
    assert controller.sent_pwm[-1] == 2000

    clock.advance(0.29)
    spinner.tick()
    assert controller.sent_pwm[-1] == 2000, "still inside the 0.3 s hold"

    clock.advance(0.31)
    assert spinner.state()["level"] == 0.5, "one half-life after the hold"

    clock.advance(0.3)
    assert spinner.state()["level"] == 0.25

    clock.advance(1.0)
    spinner.tick()
    assert spinner.state()["level"] == 0.0
    assert controller.sent_pwm[-1] == 1000, "keeps streaming idle throttle while armed"


def test_presses_inside_the_hold_stack_up_without_loss() -> None:
    controller = FakeDroneController(armed=True)
    spinner, clock = build(controller)

    for _ in range(10):
        spinner.request_spin(source="button")
        clock.advance(0.25)

    assert spinner.state()["level"] == 0.5


def test_slower_presses_still_build_up_a_little() -> None:
    controller = FakeDroneController(armed=True)
    spinner, clock = build(controller)

    for _ in range(20):
        spinner.request_spin(source="button")
        clock.advance(0.45)

    level = spinner.state()["level"]
    assert 0.1 < level < 0.3, "about 3 presses/s settles a few steps up"


def test_zero_half_life_drops_straight_to_idle_after_the_hold() -> None:
    controller = FakeDroneController(armed=True)
    spinner, clock = build(controller, decay_half_life_seconds=0.0)

    for _ in range(10):
        spinner.request_spin(source="button")
    clock.advance(0.31)

    assert spinner.state()["level"] == 0.0


def test_hold_zero_disables_decay_for_throttle_testing() -> None:
    controller = FakeDroneController(armed=True)
    spinner, clock = build(
        controller, press_hold_seconds=0.0, min_throttle_pwm=1000, press_steps=50
    )

    for _ in range(3):
        spinner.request_spin(source="button")
        clock.advance(10.0)
    spinner.tick()

    assert controller.sent_pwm == [1060], "+20 per press, still there after 30 s"


def test_already_armed_drone_is_not_armed_again() -> None:
    controller = FakeDroneController(armed=True)
    spinner, _ = build(controller)

    spinner.request_spin(source="button")
    spinner.tick()

    assert controller.calls == []
    assert controller.sent_pwm == [1335]


def test_stops_streaming_when_the_drone_gets_disarmed() -> None:
    controller = FakeDroneController()
    spinner, clock = build(controller)
    spinner.request_spin(source="button")
    spinner.tick()
    spinner.tick()

    controller.armed = False
    clock.advance(1.0)
    spinner.tick()
    sent_before = len(controller.sent_pwm)
    spinner.tick()

    assert "release" in controller.calls
    assert len(controller.sent_pwm) == sent_before
    assert spinner.state()["level"] == 0.0


def test_failed_arm_waits_before_retrying() -> None:
    controller = FakeDroneController(arm_error=RuntimeError("Arm failed: PreArm"))
    spinner, clock = build(controller, disable_auto_disarm=False)

    spinner.request_spin(source="button")
    spinner.tick()
    spinner.request_spin(source="button")
    spinner.tick()

    assert controller.calls.count("arm:force=False") == 1

    clock.advance(2.5)
    spinner.request_spin(source="button")
    spinner.tick()
    assert controller.calls.count("arm:force=False") == 2
    assert controller.sent_pwm == []


def test_not_connected_sends_nothing() -> None:
    controller = FakeDroneController()
    controller.connected = False
    spinner, _ = build(controller)

    result = spinner.request_spin(source="button")
    spinner.tick()

    assert result["outcome"] == "not_connected"
    assert controller.calls == []
    assert controller.sent_pwm == []


def test_dry_run_sends_no_mavlink_commands() -> None:
    controller = FakeDroneController()
    spinner, _ = build(controller, dry_run=True)

    result = spinner.request_spin(source="api")
    spinner.tick()

    assert result["outcome"] == "dry_run"
    assert controller.calls == []
    assert controller.sent_pwm == []


def test_force_arm_flag_is_forwarded() -> None:
    controller = FakeDroneController()
    spinner, _ = build(controller, force_arm=True, disable_auto_disarm=False)

    spinner.request_spin(source="button")
    spinner.tick()

    assert controller.calls == ["mode:STABILIZE", "arm:force=True"]
