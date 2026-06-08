from __future__ import annotations

import threading
import time
import math
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
        self._last_battery_percent: Optional[int] = None
        self._last_battery_voltage_v: Optional[float] = None
        self._last_mode_name: Optional[str] = None
        self._last_armed: Optional[bool] = None
        self._last_base_mode: Optional[int] = None
        self._last_custom_mode: Optional[int] = None
        self._last_absolute_altitude_m: Optional[float] = None
        self._last_latitude_deg: Optional[float] = None
        self._last_longitude_deg: Optional[float] = None
        self._last_local_x_m: Optional[float] = None
        self._last_local_y_m: Optional[float] = None
        self._last_local_z_m: Optional[float] = None
        self._last_roll_rad: Optional[float] = None
        self._last_pitch_rad: Optional[float] = None
        self._last_yaw_rad: Optional[float] = None
        self._last_heading_deg: Optional[float] = None
        self._last_groundspeed_mps: Optional[float] = None
        self._last_climb_mps: Optional[float] = None
        self._last_gps_fix_type: Optional[int] = None
        self._last_satellites_visible: Optional[int] = None
        self._last_hdop: Optional[float] = None
        self._last_cog_deg: Optional[float] = None
        self._last_pressure_hpa: Optional[float] = None
        self._last_temperature_c: Optional[float] = None
        self._last_accel_x: Optional[float] = None
        self._last_accel_y: Optional[float] = None
        self._last_accel_z: Optional[float] = None
        self._last_gyro_x: Optional[float] = None
        self._last_gyro_y: Optional[float] = None
        self._last_gyro_z: Optional[float] = None
        self._last_mag_x: Optional[int] = None
        self._last_mag_y: Optional[int] = None
        self._last_mag_z: Optional[int] = None

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

        self._remember_armed(
            heartbeat.base_mode
            & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            != 0
        )
        mode_name = self._mode_name_from_custom_mode(int(heartbeat.custom_mode))
        if mode_name is not None:
            self._remember_mode(mode_name)

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
            self._remember_mode(mode_name)

    def arm(self, timeout: float = 10.0) -> None:
        print("[ARM] Sende ARM")

        self.release_rc_override()
        self._drain_mavlink_messages(0.2)

        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self._target_autopilot_component(),
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0,
                1,
                0,
                0,
                0,
                0,
                0,
                0,
            )

        end = time.time() + timeout
        status_texts: list[str] = []
        command_ack: str | None = None

        while time.time() < end:
            msg = self._recv_status()

            if msg is None:
                continue

            if msg.get_type() == "STATUSTEXT":
                text = self._mavlink_text_to_str(msg.text)
                status_texts.append(text)
                print(f"[FC] {text}")

            if msg.get_type() == "COMMAND_ACK":
                command = int(getattr(msg, "command", -1))
                if command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                    command_ack = self._command_ack_to_str(int(getattr(msg, "result", -1)))
                    print(f"[ARM] COMMAND_ACK: {command_ack}")

            if msg.get_type() == "HEARTBEAT":
                armed = (
                    msg.base_mode
                    & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                ) != 0
                print(f"[ARM] Status: {'ARMED' if armed else 'DISARMED'}")
                if armed:
                    self._remember_armed(True)
                    print("[ARM] OK")
                    return

        details = []
        if command_ack is not None:
            details.append(f"ACK={command_ack}")
        if status_texts:
            details.append("FC=" + " | ".join(status_texts[-6:]))

        suffix = f": {'; '.join(details)}" if details else ""
        raise RuntimeError(f"Arm failed{suffix}")

    def disarm(self) -> None:
        self.send_velocity_body(0.0, 0.0, 0.0)
        self.release_rc_override()
        with self._lock:
            self.master.arducopter_disarm()
        self._remember_armed(False)

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

    def send_virtual_joystick(
        self,
        forward: float,
        right: float,
        throttle: float,
        yaw: float,
        duration_seconds: float,
    ) -> None:
        pitch = int(round(max(-1.0, min(1.0, float(forward))) * 1000))
        roll = int(round(max(-1.0, min(1.0, float(right))) * 1000))
        throttle_value = int(round((max(-1.0, min(1.0, float(throttle))) + 1.0) * 500))
        yaw_value = int(round(max(-1.0, min(1.0, float(yaw))) * 1000))

        if duration_seconds <= 0:
            self._send_manual_control(pitch, roll, throttle_value, yaw_value)
            return

        end_time = time.time() + duration_seconds
        while time.time() < end_time:
            self._send_manual_control(pitch, roll, throttle_value, yaw_value)
            time.sleep(0.1)

        self._send_manual_control(0, 0, 500, 0)

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

    def goto_global_relative(
        self,
        latitude_deg: float,
        longitude_deg: float,
        altitude_meters: float,
    ) -> None:
        self.set_mode("GUIDED")
        with self._lock:
            self.master.mav.set_position_target_global_int_send(
                int(time.time() * 1000) & 0xFFFFFFFF,
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                3576,
                int(latitude_deg * 10_000_000),
                int(longitude_deg * 10_000_000),
                altitude_meters,
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

    def _send_guided_velocity_with_yaw_rate(
        self,
        vx: float,
        vy: float,
        vz: float,
        yaw_rate_rad_per_sec: float,
    ) -> None:
        with self._lock:
            self.master.mav.set_position_target_local_ned_send(
                0,
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_FRAME_BODY_NED,
                1479,
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
                yaw_rate_rad_per_sec,
            )

    def _send_manual_control(
        self,
        pitch: int,
        roll: int,
        throttle: int,
        yaw: int,
    ) -> None:
        with self._lock:
            self.master.mav.manual_control_send(
                self.master.target_system,
                pitch,
                roll,
                max(0, min(1000, throttle)),
                yaw,
                0,
            )

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

        self._drain_mavlink_messages(0.03)
        return self._status_snapshot()

    def get_telemetry(self) -> dict[str, Any]:
        if not self.is_connected():
            return self._empty_telemetry()

        self._drain_mavlink_messages(0.05)
        return {
            "gps_fix": self._last_gps_fix_type if self._last_gps_fix_type is not None else 0,
            "gps_satellites": self._last_satellites_visible if self._last_satellites_visible is not None else 0,
            "latitude": self._last_latitude_deg if self._last_latitude_deg is not None else 0.0,
            "longitude": self._last_longitude_deg if self._last_longitude_deg is not None else 0.0,
            "gps_altitude": self._last_absolute_altitude_m if self._last_absolute_altitude_m is not None else 0.0,
            "ground_speed": self._last_groundspeed_mps if self._last_groundspeed_mps is not None else 0.0,
            "cog": self._last_cog_deg if self._last_cog_deg is not None else self._heading_or_zero(),
            "hdop": self._last_hdop if self._last_hdop is not None else 0.0,
            "relative_alt": self._last_relative_altitude_m if self._last_relative_altitude_m is not None else 0.0,
            "absolute_alt": self._last_absolute_altitude_m if self._last_absolute_altitude_m is not None else 0.0,
            "pressure": self._last_pressure_hpa if self._last_pressure_hpa is not None else 0.0,
            "accel_x": self._last_accel_x if self._last_accel_x is not None else 0.0,
            "accel_y": self._last_accel_y if self._last_accel_y is not None else 0.0,
            "accel_z": self._last_accel_z if self._last_accel_z is not None else 0.0,
            "gyro_x": self._last_gyro_x if self._last_gyro_x is not None else 0.0,
            "gyro_y": self._last_gyro_y if self._last_gyro_y is not None else 0.0,
            "gyro_z": self._last_gyro_z if self._last_gyro_z is not None else 0.0,
            "mag_x": self._last_mag_x if self._last_mag_x is not None else 0,
            "mag_y": self._last_mag_y if self._last_mag_y is not None else 0,
            "mag_z": self._last_mag_z if self._last_mag_z is not None else 0,
            "temperature": self._last_temperature_c if self._last_temperature_c is not None else 0.0,
            "compass_heading": self._heading_or_zero(),
        }

    @staticmethod
    def _empty_telemetry() -> dict[str, Any]:
        return {
            "gps_fix": 0,
            "gps_satellites": 0,
            "latitude": 0.0,
            "longitude": 0.0,
            "gps_altitude": 0.0,
            "ground_speed": 0.0,
            "cog": 0.0,
            "hdop": 0.0,
            "relative_alt": 0.0,
            "absolute_alt": 0.0,
            "pressure": 0.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 0.0,
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
            "mag_x": 0,
            "mag_y": 0,
            "mag_z": 0,
            "temperature": 0.0,
            "compass_heading": 0.0,
        }

    def _heading_or_zero(self) -> float:
        return self._last_heading_deg if self._last_heading_deg is not None else 0.0

    def _status_snapshot(self) -> dict[str, Any]:
        return {
            "connected": True,
            "connection": self.get_connection_info(),
            "last_heartbeat_time": self._last_heartbeat_time,
            "base_mode": self._last_base_mode,
            "custom_mode": self._last_custom_mode,
            "altitude_relative_m": self._last_relative_altitude_m if self._last_relative_altitude_m is not None else 0.0,
            "relative_altitude_m": self._last_relative_altitude_m if self._last_relative_altitude_m is not None else 0.0,
            "absolute_altitude_m": self._last_absolute_altitude_m if self._last_absolute_altitude_m is not None else 0.0,
            "battery_remaining_percent": self._battery_percent_or_voltage_estimate(),
            "battery_voltage_v": self._last_battery_voltage_v if self._last_battery_voltage_v is not None else 0.0,
            "mode": self._last_mode_name or "UNKNOWN",
            "armed": self._last_armed if self._last_armed is not None else False,
            "latitude_deg": self._last_latitude_deg,
            "longitude_deg": self._last_longitude_deg,
            "local_position_x_m": self._last_local_x_m,
            "local_position_y_m": self._last_local_y_m,
            "local_position_z_m": self._last_local_z_m,
            "roll": self._last_roll_rad,
            "pitch": self._last_pitch_rad,
            "yaw": self._last_yaw_rad,
            "heading_deg": self._last_heading_deg,
            "groundspeed_mps": self._last_groundspeed_mps if self._last_groundspeed_mps is not None else 0.0,
            "climb_mps": self._last_climb_mps if self._last_climb_mps is not None else 0.0,
            "gps_fix_type": self._last_gps_fix_type if self._last_gps_fix_type is not None else 0,
            "satellites_visible": self._last_satellites_visible if self._last_satellites_visible is not None else 0,
        }

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
            mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
            mavutil.mavlink.MAVLINK_MSG_ID_VFR_HUD,
            mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
            mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS,
            mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
            mavutil.mavlink.MAVLINK_MSG_ID_RAW_IMU,
            mavutil.mavlink.MAVLINK_MSG_ID_SCALED_PRESSURE,
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

    def _drain_mavlink_messages(self, duration_seconds: float, max_messages: int = 300) -> None:
        end_time = time.time() + duration_seconds
        messages_read = 0

        while messages_read < max_messages and time.time() < end_time:
            with self._lock:
                message = self.master.recv_match(blocking=False)

            if message is None:
                time.sleep(0.005)
                continue

            messages_read += 1
            self._remember_message(message)

    def _remember_message(self, message: Any) -> None:
        if message is None:
            return

        message_type = message.get_type()

        if message_type == "HEARTBEAT":
            self._last_base_mode = int(message.base_mode)
            self._last_custom_mode = int(message.custom_mode)
            self._remember_armed(
                message.base_mode
                & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                != 0
            )
            mode_name = self._mode_name_from_custom_mode(int(message.custom_mode))
            if mode_name is not None:
                self._remember_mode(mode_name)
            self._last_heartbeat_time = time.time()
            return

        if message_type == "ATTITUDE":
            self._last_roll_rad = float(message.roll)
            self._last_pitch_rad = float(message.pitch)
            self._last_yaw_rad = float(message.yaw)
            self._last_heading_deg = (math.degrees(float(message.yaw)) + 360.0) % 360.0
            return

        if message_type == "ALTITUDE":
            self._last_absolute_altitude_m = float(message.altitude_amsl)
            self._remember_altitude(float(message.altitude_relative))
            return

        if message_type == "GLOBAL_POSITION_INT":
            self._last_latitude_deg = float(message.lat) / 10_000_000.0
            self._last_longitude_deg = float(message.lon) / 10_000_000.0
            self._last_absolute_altitude_m = float(message.alt) / 1000.0
            self._remember_altitude(float(message.relative_alt) / 1000.0)
            heading_raw = int(getattr(message, "hdg", 65535))
            if heading_raw != 65535:
                self._last_heading_deg = heading_raw / 100.0
                self._last_cog_deg = self._last_heading_deg
            vx = float(getattr(message, "vx", 0.0)) / 100.0
            vy = float(getattr(message, "vy", 0.0)) / 100.0
            self._last_groundspeed_mps = math.hypot(vx, vy)
            return

        if message_type == "LOCAL_POSITION_NED":
            self._last_local_x_m = float(message.x)
            self._last_local_y_m = float(message.y)
            self._last_local_z_m = float(message.z)
            self._remember_altitude(max(0.0, -float(message.z)))
            return

        if message_type == "VFR_HUD":
            self._last_absolute_altitude_m = float(message.alt)
            self._last_heading_deg = float(message.heading)
            self._last_groundspeed_mps = float(message.groundspeed)
            self._last_climb_mps = float(message.climb)
            return

        if message_type == "SYS_STATUS":
            if int(message.battery_remaining) >= 0:
                self._remember_battery_percent(int(message.battery_remaining))
            if int(message.voltage_battery) > 0:
                self._remember_battery_voltage(float(message.voltage_battery) / 1000.0)
            return

        if message_type == "BATTERY_STATUS":
            remaining = int(getattr(message, "battery_remaining", -1))
            if remaining >= 0:
                self._remember_battery_percent(remaining)
            voltages = getattr(message, "voltages", [])
            valid_voltages = [value for value in voltages if 0 < int(value) < 65535]
            if valid_voltages:
                self._remember_battery_voltage(sum(valid_voltages) / 1000.0)
            return

        if message_type == "GPS_RAW_INT":
            self._last_gps_fix_type = int(getattr(message, "fix_type", 0))
            self._last_satellites_visible = int(getattr(message, "satellites_visible", 0))
            eph = int(getattr(message, "eph", 65535))
            if eph != 65535:
                self._last_hdop = eph / 100.0
            cog = int(getattr(message, "cog", 65535))
            if cog != 65535:
                self._last_cog_deg = cog / 100.0
            lat = int(getattr(message, "lat", 0))
            lon = int(getattr(message, "lon", 0))
            if lat != 0 or lon != 0:
                self._last_latitude_deg = lat / 10_000_000.0
                self._last_longitude_deg = lon / 10_000_000.0
            alt = int(getattr(message, "alt", 0))
            if alt != 0:
                self._last_absolute_altitude_m = alt / 1000.0
            return

        if message_type == "RAW_IMU":
            self._last_accel_x = float(getattr(message, "xacc", 0.0)) / 1000.0
            self._last_accel_y = float(getattr(message, "yacc", 0.0)) / 1000.0
            self._last_accel_z = float(getattr(message, "zacc", 0.0)) / 1000.0
            self._last_gyro_x = float(getattr(message, "xgyro", 0.0)) / 1000.0
            self._last_gyro_y = float(getattr(message, "ygyro", 0.0)) / 1000.0
            self._last_gyro_z = float(getattr(message, "zgyro", 0.0)) / 1000.0
            self._last_mag_x = int(getattr(message, "xmag", 0))
            self._last_mag_y = int(getattr(message, "ymag", 0))
            self._last_mag_z = int(getattr(message, "zmag", 0))
            return

        if message_type == "SCALED_PRESSURE":
            self._last_pressure_hpa = float(getattr(message, "press_abs", 0.0))
            temp_raw = int(getattr(message, "temperature", 0))
            self._last_temperature_c = temp_raw / 100.0

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

    def _remember_battery_percent(self, battery_percent: int) -> int:
        self._last_battery_percent = battery_percent
        return battery_percent

    def _remember_battery_voltage(self, voltage_v: float) -> float:
        self._last_battery_voltage_v = voltage_v
        return voltage_v

    def _battery_percent_or_voltage_estimate(self) -> int:
        if self._last_battery_percent is not None:
            return self._last_battery_percent

        if self._last_battery_voltage_v is None:
            return 0

        # ArduPilot SITL sometimes exposes voltage but no percentage. Estimate a
        # 3S LiPo range so the GUI can still show a useful numeric battery value.
        estimated = round((self._last_battery_voltage_v - 10.5) / (12.6 - 10.5) * 100)
        return max(0, min(100, estimated))

    def _remember_mode(self, mode_name: str) -> str:
        self._last_mode_name = mode_name
        return mode_name

    def _remember_armed(self, armed: bool) -> bool:
        self._last_armed = armed
        return armed

    def _mode_name_from_custom_mode(self, custom_mode: int) -> str | None:
        mode_mapping = self.master.mode_mapping()
        if mode_mapping is None:
            return None

        reverse_mapping = {mode_id: mode_name for mode_name, mode_id in mode_mapping.items()}
        return reverse_mapping.get(custom_mode)

    def _recv_status(self):
        with self._lock:
            return self.master.recv_match(
                type=["STATUSTEXT", "COMMAND_ACK", "HEARTBEAT"],
                blocking=True,
                timeout=0.5,
            )

    def _target_autopilot_component(self) -> int:
        target_component = int(getattr(self.master, "target_component", 0) or 0)
        if target_component > 0:
            return target_component

        return mavutil.mavlink.MAV_COMP_ID_AUTOPILOT1

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

    @staticmethod
    def _command_ack_to_str(result: int) -> str:
        result_names = {}
        for constant_name, display_name in (
            ("MAV_RESULT_ACCEPTED", "ACCEPTED"),
            ("MAV_RESULT_TEMPORARILY_REJECTED", "TEMPORARILY_REJECTED"),
            ("MAV_RESULT_DENIED", "DENIED"),
            ("MAV_RESULT_UNSUPPORTED", "UNSUPPORTED"),
            ("MAV_RESULT_FAILED", "FAILED"),
            ("MAV_RESULT_IN_PROGRESS", "IN_PROGRESS"),
            ("MAV_RESULT_CANCELLED", "CANCELLED"),
        ):
            constant_value = getattr(mavutil.mavlink, constant_name, None)
            if constant_value is not None:
                result_names[int(constant_value)] = display_name

        return result_names.get(result, f"UNKNOWN({result})")
