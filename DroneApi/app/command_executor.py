from __future__ import annotations

from app.drone_controller import DroneController


class CommandExecutor:
    def __init__(self, drone_controller: DroneController) -> None:
        self._drone_controller = drone_controller

    def initialize_for_guided_flight(self, takeoff_altitude_meters: float) -> None:
        self._drone_controller.set_mode("GUIDED")
        self._drone_controller.arm()
        self._drone_controller.takeoff(takeoff_altitude_meters)

    def move_forward(self, speed_meters_per_second: float, duration_seconds: float) -> None:
        self._drone_controller.move_body_for_duration(speed_meters_per_second, 0.0, 0.0, duration_seconds)

    def move_backward(self, speed_meters_per_second: float, duration_seconds: float) -> None:
        self._drone_controller.move_body_for_duration(-speed_meters_per_second, 0.0, 0.0, duration_seconds)

    def move_right(self, speed_meters_per_second: float, duration_seconds: float) -> None:
        self._drone_controller.move_body_for_duration(0.0, speed_meters_per_second, 0.0, duration_seconds)

    def move_left(self, speed_meters_per_second: float, duration_seconds: float) -> None:
        self._drone_controller.move_body_for_duration(0.0, -speed_meters_per_second, 0.0, duration_seconds)

    def move_up(self, speed_meters_per_second: float, duration_seconds: float) -> None:
        self._drone_controller.move_body_for_duration(0.0, 0.0, -speed_meters_per_second, duration_seconds)

    def move_down(self, speed_meters_per_second: float, duration_seconds: float) -> None:
        self._drone_controller.move_body_for_duration(0.0, 0.0, speed_meters_per_second, duration_seconds)

    def rotate_to(self, yaw_degrees: float) -> None:
        self._drone_controller.set_yaw(yaw_degrees)

    def land(self) -> None:
        self._drone_controller.land()

    def rtl(self) -> None:
        self._drone_controller.rtl()