from __future__ import annotations

import threading
import time
from typing import Any, Optional

from pymavlink import mavutil


class DroneController:
    RC_MIN = 1000
    RC_NEUTRAL = 1500
    RC_MAX = 2000
    RC_IGNORE = 65535

    def __init__(self) -> None:
        self._master: Optional[mavutil.mavfile] = None
        self._lock = threading.Lock()
        self._last_heartbeat_time: Optional[float] = None
        self._connected = False
        self._connection_string: Optional[str] = None
        self._baud_rate: Optional[int] = None
        self._last_relative_altitude_m: Optional[float] = None

    @property
    def master(self) -> mavutil.mavfile:
        if self._master is None:
            raise RuntimeError("Keine aktive MAVLink-Verbindung.")
        return self._master

    def connect(
        self,
        connection_string: str,
        baud_rate: int = 57600,
        heartbeat_timeout_seconds: float = 5.0,
    ) -> None:
        print(f"[CONNECT] Verbinde mit {connection_string} ...")

        with self._lock:
            if self._master is not None:
                try:
                    self._master.close()
                except Exception:
                    pass

            self._master = None
            self._connected = False

        if self._is_network_connection(connection_string):
            master = mavutil.mavlink_connection(connection_string)
        else:
            master = mavutil.mavlink_connection(connection_string, baud=baud_rate)

        heartbeat = master.wait_heartbeat(timeout=heartbeat_timeout_seconds)
        if heartbeat is None:
            try:
                master.close()
            except Exception:
                pass
            raise TimeoutError(
                f"No MAVLink heartbeat received within {heartbeat_timeout_seconds} seconds"
            )

        print("[CONNECT] Heartbeat empfangen")
        print(f"[CONNECT] System={master.target_system} Component={master.target_component}")

        with self._lock:
            self._master = master
            self._connected = True
            self._last_heartbeat_time = time.time()
            self._connection_string = connection_string
            self._baud_rate = baud_rate

        self._request_telemetry_streams()

    def disconnect(self) -> None:
        with self._lock:
            if self._master is not None:
                try:
                    self._master.close()
                except Exception:
                    pass

            self._master = None
            self._connected = False

    def set_mode(self, mode_name: str) -> None:
        with self._lock:
            mode_mapping = self.master.mode_mapping()
            if mode_mapping is None:
                raise RuntimeError("Mode-Mapping konnte nicht geladen werden.")

            if mode_name not in mode_mapping:
                raise ValueError(f"Unbekannter Modus: {mode_name}")

            self.master.mav.set_mode_send(
                self.master.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_mapping[mode_name],
            )

    def arm(self, timeout: float = 10.0) -> None:
        print("[ARM] Sende ARM")

        with self._lock:
            self.master.arducopter_arm()

        end = time.time() + timeout
        while time.time() < end:
            msg = self._recv_status()

            if msg is None:
                continue

            if msg.get_type() == "STATUSTEXT":
                print(f"[FC] {self._mavlink_text_to_str(msg.text)}")

            if msg.get_type() == "HEARTBEAT":
                armed = (
                    msg.base_mode
                    & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                ) != 0
                print(f"[ARM] Status: {'ARMED' if armed else 'DISARMED'}")
                if armed:
                    print("[ARM] OK")
                    return

        raise RuntimeError("Arm failed")

    def disarm(self) -> None:
        self.send_velocity_body(0.0, 0.0, 0.0)
        self.release_rc_override()
        with self._lock:
            self.master.arducopter_disarm()

    def takeoff(
        self,
        altitude_meters: float = 5.0,
        arm_first: bool = True,
        timeout: float = 45.0,
    ) -> None:
        self.release_rc_override()
        self.set_mode("GUIDED")
        self._drain_mavlink_messages(0.2)

        if arm_first:
            self.arm()

        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                altitude_meters,
            )

        end = time.time() + timeout
        while time.time() < end:
            altitude = self._relative_altitude_m(blocking_timeout=0.5, allow_cached=False)
            if altitude is not None:
                print(f"[TAKEOFF] Altitude: {altitude:.2f} / {altitude_meters:.2f} m")

            if altitude is not None and altitude >= altitude_meters - 0.25:
                self.send_velocity_body(0.0, 0.0, 0.0)
                return

        last_altitude = (
            f" Last altitude: {self._last_relative_altitude_m:.2f} m."
            if self._last_relative_altitude_m is not None
            else " No altitude telemetry received."
        )
        raise RuntimeError(f"Takeoff timeout before reaching {altitude_meters} m.{last_altitude}")

    def land(self) -> None:
        self.set_mode("LAND")

    def rtl(self) -> None:
        self.set_mode("RTL")

    def send_throttle(self, throttle_pwm: int, duration_seconds: float = 0.0) -> None:
        self.send_rc_override(
            throttle=throttle_pwm,
            duration_seconds=duration_seconds,
            release_after=duration_seconds > 0,
        )

    def send_velocity_body(self, vx: float, vy: float, vz: float) -> None:
        with self._lock:
            self.master.mav.set_position_target_local_ned_send(
                0,
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_FRAME_BODY_NED,
                3527,
                0,
                0,
                0,
                vx,
                vy,
                vz,
                0,
                0,
                0,
                0,
                0,
            )

    def move_body_for_duration(
        self,
        vx: float,
        vy: float,
        vz: float,
        duration_seconds: float,
    ) -> None:
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
                3576,
                x,
                y,
                z,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            )

    def set_yaw(
        self,
        yaw_degrees: float,
        yaw_speed_deg_per_sec: float = 20.0,
        is_relative: bool = False,
    ) -> None:
        direction = 1 if yaw_degrees >= 0 else -1
        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_CONDITION_YAW,
                0,
                abs(yaw_degrees),
                yaw_speed_deg_per_sec,
                direction,
                1 if is_relative else 0,
                0,
                0,
                0,
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
        param7: float = 0.0,
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
                param7,
            )

    def send_rc_override(
        self,
        roll: int | None = None,
        pitch: int | None = None,
        throttle: int | None = None,
        yaw: int | None = None,
        duration_seconds: float = 0.0,
        release_after: bool = False,
    ) -> None:
        channels = [
            self._pwm_or_ignore(roll),
            self._pwm_or_ignore(pitch),
            self._pwm_or_ignore(throttle),
            self._pwm_or_ignore(yaw),
            self.RC_IGNORE,
            self.RC_IGNORE,
            self.RC_IGNORE,
            self.RC_IGNORE,
        ]

        end_time = time.time() + duration_seconds
        while True:
            with self._lock:
                self.master.mav.rc_channels_override_send(
                    self.master.target_system,
                    self.master.target_component,
                    *channels,
                )

            if duration_seconds <= 0 or time.time() >= end_time:
                break

            time.sleep(0.1)

        if release_after:
            self.release_rc_override()

    def release_rc_override(self) -> None:
        with self._lock:
            self.master.mav.rc_channels_override_send(
                self.master.target_system,
                self.master.target_component,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            )

    def is_connected(self) -> bool:
        return self._connected and self._master is not None

    def get_connection_info(self) -> dict[str, Any]:
        return {
            "connected": self.is_connected(),
            "connection_string": self._connection_string,
            "baud_rate": self._baud_rate,
            "target_system": self._master.target_system if self._master else None,
            "target_component": self._master.target_component if self._master else None,
        }

    def get_status(self) -> dict[str, Any]:
        if not self.is_connected():
            return {"connected": False}

        heartbeat = self.master.recv_match(type="HEARTBEAT", blocking=False)
        attitude = self.master.recv_match(type="ATTITUDE", blocking=False)
        altitude = self.master.recv_match(type="ALTITUDE", blocking=False)
        global_position = self.master.recv_match(type="GLOBAL_POSITION_INT", blocking=False)
        local_position = self.master.recv_match(type="LOCAL_POSITION_NED", blocking=False)
        vfr_hud = self.master.recv_match(type="VFR_HUD", blocking=False)
        sys_status = self.master.recv_match(type="SYS_STATUS", blocking=False)
        battery_status = self.master.recv_match(type="BATTERY_STATUS", blocking=False)

        result: dict[str, Any] = {
            "connected": True,
            "connection": self.get_connection_info(),
            "last_heartbeat_time": self._last_heartbeat_time,
        }

        if heartbeat is not None:
            result["base_mode"] = int(heartbeat.base_mode)
            result["custom_mode"] = int(heartbeat.custom_mode)
            result["armed"] = (
                heartbeat.base_mode
                & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            ) != 0
            self._last_heartbeat_time = time.time()

        if attitude is not None:
            result["roll"] = float(attitude.roll)
            result["pitch"] = float(attitude.pitch)
            result["yaw"] = float(attitude.yaw)

        if altitude is not None:
            result["altitude_local_m"] = float(altitude.altitude_local)
            result["altitude_relative_m"] = self._remember_altitude(float(altitude.altitude_relative))

        if global_position is not None:
            result["relative_altitude_m"] = self._remember_altitude(float(global_position.relative_alt) / 1000.0)

        if local_position is not None:
            result["local_position_z_m"] = float(local_position.z)
            result["relative_altitude_m"] = self._remember_altitude(max(0.0, -float(local_position.z)))

        if vfr_hud is not None:
            result["vfr_altitude_m"] = float(vfr_hud.alt)

        if sys_status is not None:
            if int(sys_status.battery_remaining) >= 0:
                result["battery_remaining_percent"] = int(sys_status.battery_remaining)
            if int(sys_status.voltage_battery) > 0:
                result["battery_voltage_v"] = float(sys_status.voltage_battery) / 1000.0

        if battery_status is not None:
            remaining = int(getattr(battery_status, "battery_remaining", -1))
            if remaining >= 0:
                result["battery_remaining_percent"] = remaining

        return result

    def _relative_altitude_m(
        self,
        blocking_timeout: float = 0.5,
        allow_cached: bool = True,
    ) -> float | None:
        deadline = time.time() + blocking_timeout
        message_types = [
            "ALTITUDE",
            "GLOBAL_POSITION_INT",
            "LOCAL_POSITION_NED",
            "VFR_HUD",
        ]

        while time.time() <= deadline:
            remaining = max(0.05, deadline - time.time())

            with self._lock:
                message = self.master.recv_match(
                    type=message_types,
                    blocking=True,
                    timeout=remaining,
                )

            altitude = self._altitude_from_message(message)
            if altitude is not None:
                return self._remember_altitude(altitude)

        if allow_cached:
            return self._last_relative_altitude_m

        return None

    def _request_telemetry_streams(self) -> None:
        message_ids = [
            mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
            mavutil.mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED,
            mavutil.mavlink.MAVLINK_MSG_ID_ALTITUDE,
            mavutil.mavlink.MAVLINK_MSG_ID_VFR_HUD,
            mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
            mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS,
        ]

        with self._lock:
            for message_id in message_ids:
                self.master.mav.command_long_send(
                    self.master.target_system,
                    self.master.target_component,
                    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                    0,
                    message_id,
                    200000,
                    0,
                    0,
                    0,
                    0,
                    0,
                )

            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                4,
                1,
            )

    def _drain_mavlink_messages(self, duration_seconds: float) -> None:
        end_time = time.time() + duration_seconds
        while time.time() < end_time:
            with self._lock:
                message = self.master.recv_match(blocking=False)
            altitude = self._altitude_from_message(message)
            if altitude is not None:
                self._remember_altitude(altitude)

    def _altitude_from_message(self, message: Any) -> float | None:
        if message is None:
            return None

        message_type = message.get_type()
        if message_type == "ALTITUDE":
            return float(message.altitude_relative)
        if message_type == "GLOBAL_POSITION_INT":
            return float(message.relative_alt) / 1000.0
        if message_type == "LOCAL_POSITION_NED":
            return max(0.0, -float(message.z))

        return None

    def _remember_altitude(self, altitude_meters: float) -> float:
        self._last_relative_altitude_m = altitude_meters
        return altitude_meters

    def _recv_status(self):
        with self._lock:
            return self.master.recv_match(
                type=["STATUSTEXT", "HEARTBEAT"],
                blocking=True,
                timeout=0.5,
            )

    def _is_network_connection(self, connection_string: str) -> bool:
        return connection_string.lower().startswith(("tcp:", "udp:", "udpin:", "udpout:"))

    def _pwm_or_ignore(self, value: int | None) -> int:
        if value is None:
            return self.RC_IGNORE
        return max(self.RC_MIN, min(self.RC_MAX, int(value)))

    @staticmethod
    def _mavlink_text_to_str(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip("\x00")
        if isinstance(value, bytearray):
            return bytes(value).decode("utf-8", errors="replace").strip("\x00")
        return str(value).strip("\x00")
