from __future__ import annotations

import threading
import time
from typing import Any, Optional

from pymavlink import mavutil


class DroneController:
    def __init__(self) -> None:
        self._master: Optional[mavutil.mavfile] = None
        self._lock = threading.Lock()
        self._last_heartbeat_time: Optional[float] = None
        self._connected: bool = False

    @property
    def master(self) -> mavutil.mavfile:
        if self._master is None:
            raise RuntimeError("Keine aktive MAVLink-Verbindung.")
        return self._master

    def connect(
        self,
        connection_string: str,
        baud_rate: int = 57600,
        heartbeat_timeout_seconds: double = 5.0
    ) -> None:
        with self._lock:
            if self._master is not None:
                try:
                    self._master.close()
                except Exception:
                    pass

            self._master = None
            self._connected = False
            self._last_heartbeat_time = None

            try:
                if self._is_network_connection(connection_string):
                    master = mavutil.mavlink_connection(connection_string)
                else:
                    master = mavutil.mavlink_connection(connection_string, baud=baud_rate)

                heartbeat = master.wait_heartbeat(timeout=heartbeat_timeout_seconds)
                if heartbeat is None:
                    master.close()
                    raise RuntimeError(
                        f"Kein Heartbeat innerhalb von {heartbeat_timeout_seconds} Sekunden empfangen."
                    )

                self._master = master
                self._connected = True
                self._last_heartbeat_time = time.time()

            except Exception:
                self._master = None
                self._connected = False
                self._last_heartbeat_time = None
                raise

    def disconnect(self) -> None:
        with self._lock:
            if self._master is not None:
                try:
                    self._master.close()
                except Exception:
                    pass

            self._master = None
            self._connected = False
            self._last_heartbeat_time = None

    def _is_network_connection(self, connection_string: str) -> bool:
        lowered = connection_string.lower()
        return (
            lowered.startswith("tcp:")
            or lowered.startswith("udp:")
            or lowered.startswith("udpin:")
            or lowered.startswith("udpout:")
        )

    def is_connected(self) -> bool:
        return self._connected and self._master is not None

    def get_connection_info(self) -> dict[str, Any]:
        if not self.is_connected():
            return {
                "connected": False,
                "target_system": None,
                "target_component": None
            }

        return {
            "connected": True,
            "target_system": self.master.target_system,
            "target_component": self.master.target_component,
            "last_heartbeat_time": self._last_heartbeat_time
        }

    def set_mode(self, mode_name: str) -> None:
        with self._lock:
            mode_mapping = self.master.mode_mapping()
            if mode_mapping is None:
                raise RuntimeError("Mode-Mapping konnte nicht geladen werden.")

            if mode_name not in mode_mapping:
                raise ValueError(f"Unbekannter Modus: {mode_name}")

            mode_id = mode_mapping[mode_name]
            self.master.mav.set_mode_send(
                self.master.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id
            )

    def arm(self) -> None:
        with self._lock:
            self.master.arducopter_arm()
            self.master.motors_armed_wait()

    def disarm(self) -> None:
        with self._lock:
            self.master.arducopter_disarm()
            self.master.motors_disarmed_wait()

    def takeoff(self, altitude_meters: float) -> None:
        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                0,
                0, 0, 0, 0,
                0, 0, altitude_meters
            )

    def land(self) -> None:
        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_LAND,
                0,
                0, 0, 0, 0,
                0, 0, 0
            )

    def rtl(self) -> None:
        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
                0,
                0, 0, 0, 0,
                0, 0, 0
            )

    def send_velocity_body(self, vx: float, vy: float, vz: float) -> None:
        with self._lock:
            self.master.mav.set_position_target_local_ned_send(
                0,
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_FRAME_BODY_NED,
                0b0000111111000111,
                0, 0, 0,
                vx, vy, vz,
                0, 0, 0,
                0, 0
            )

    def move_body_for_duration(self, vx: float, vy: float, vz: float, duration_seconds: float) -> None:
        if duration_seconds <= 0:
            self.send_velocity_body(vx, vy, vz)
            return

        end_time = time.time() + duration_seconds
        while time.time() < end_time:
            self.send_velocity_body(vx, vy, vz)
            time.sleep(0.1)

        self.send_velocity_body(0.0, 0.0, 0.0)

    def goto_local_ned(self, x: float, y: float, z: float) -> None:
        with self._lock:
            self.master.mav.set_position_target_local_ned_send(
                0,
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                0b0000111111111000,
                x, y, z,
                0, 0, 0,
                0, 0, 0,
                0, 0
            )

    def set_yaw(self, yaw_degrees: float, yaw_speed_deg_per_sec: float = 20.0, is_relative: bool = False) -> None:
        relative_flag = 1 if is_relative else 0

        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_CONDITION_YAW,
                0,
                yaw_degrees,
                yaw_speed_deg_per_sec,
                1,
                relative_flag,
                0, 0, 0
            )

    def send_raw_command(
        self,
        command_id: int,
        param1: float = 0.0,
        param2: float = 0.0,
        param3: float = 0.0,
        param4: float = 0.0,
        param5: float = 0.0,
        param6: float = 0.0,
        param7: float = 0.0
    ) -> None:
        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                command_id,
                0,
                param1,
                param2,
                param3,
                param4,
                param5,
                param6,
                param7
            )

    def get_status(self) -> dict[str, Any]:
        if not self.is_connected():
            return {
                "connected": False
            }

        heartbeat = self.master.recv_match(type="HEARTBEAT", blocking=False)
        global_position = self.master.recv_match(type="GLOBAL_POSITION_INT", blocking=False)
        gps = self.master.recv_match(type="GPS_RAW_INT", blocking=False)

        result: dict[str, Any] = {
            "connected": True,
            "target_system": self.master.target_system,
            "target_component": self.master.target_component,
            "last_heartbeat_time": self._last_heartbeat_time
        }

        if heartbeat is not None:
            result["base_mode"] = int(heartbeat.base_mode)
            result["custom_mode"] = int(heartbeat.custom_mode)
            self._last_heartbeat_time = time.time()

        if global_position is not None:
            result["latitude"] = float(global_position.lat / 1e7)
            result["longitude"] = float(global_position.lon / 1e7)
            result["relative_altitude_m"] = float(global_position.relative_alt / 1000.0)

        if gps is not None:
            result["gps_fix_type"] = int(gps.fix_type)
            result["satellites_visible"] = int(gps.satellites_visible)

        return result