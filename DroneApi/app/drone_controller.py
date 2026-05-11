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
    CONTROL_PWM_RANGE = 400
    DEFAULT_THROTTLE_DURATION_SECONDS = 2.0
    MAVLINK_CONTROL_INTERVAL_SECONDS = 0.05

    def __init__(self) -> None:
        self._master: Optional[mavutil.mavfile] = None
        self._lock = threading.Lock()
        self._last_heartbeat_time: Optional[float] = None
        self._connected: bool = False
        self._connection_string: Optional[str] = None
        self._baud_rate: Optional[int] = None

    @property
    def master(self) -> mavutil.mavfile:
        if self._master is None:
            raise RuntimeError("Keine aktive MAVLink-Verbindung.")
        return self._master

    def connect(
        self,
        connection_string: str,
        baud_rate: int = 57600,
        heartbeat_timeout_seconds: float = 5.0
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
                mode_mapping[mode_name]
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
                armed = (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0
                print(f"[ARM] Status: {'ARMED' if armed else 'DISARMED'}")
                if armed:
                    print("[ARM] OK")
                    return

        raise RuntimeError("Arm failed")

    def disarm(self) -> None:
        self.stop_motors()
        with self._lock:
            self.master.arducopter_disarm()

    def takeoff(
        self,
        throttle_pwm: int = 1600,
        duration_seconds: float = 2.0,
        arm_first: bool = False
    ) -> None:
        if arm_first:
            self.arm()

        self.send_throttle(throttle_pwm, duration_seconds)

    def land(self, throttle_pwm: int = 1200, duration_seconds: float = 2.0) -> None:
        self.send_throttle(throttle_pwm, duration_seconds)
        self.stop_motors()

    def rtl(self) -> None:
        raise RuntimeError("RTL needs GPS. Use /land or /throttle for this no-GPS setup.")

    def send_throttle(self, throttle_pwm: int, duration_seconds: float = 0.0) -> float:
        effective_duration = duration_seconds
        if effective_duration <= 0:
            effective_duration = self.DEFAULT_THROTTLE_DURATION_SECONDS

        thrust = self.pwm_to_thrust(throttle_pwm)
        end_time = time.time() + effective_duration

        while True:
            with self._lock:
                self.master.mav.set_attitude_target_send(
                    int((time.time() * 1000) % 0xFFFFFFFF),
                    self.master.target_system,
                    self.master.target_component,
                    7,
                    [1.0, 0.0, 0.0, 0.0],
                    0.0,
                    0.0,
                    0.0,
                    thrust
                )

            if time.time() >= end_time:
                break

            time.sleep(self.MAVLINK_CONTROL_INTERVAL_SECONDS)

        return effective_duration

    def stop_motors(self) -> None:
        self.send_throttle(self.RC_MIN, duration_seconds=0.2)

    def send_velocity_body(self, vx: float, vy: float, vz: float) -> None:
        roll = self.RC_NEUTRAL + self._scaled_control(vy)
        pitch = self.RC_NEUTRAL - self._scaled_control(vx)
        throttle = self.RC_NEUTRAL - self._scaled_control(vz)
        self.send_rc_override(roll=roll, pitch=pitch, throttle=throttle)

    def move_body_for_duration(
        self,
        vx: float,
        vy: float,
        vz: float,
        duration_seconds: float
    ) -> None:
        if duration_seconds <= 0:
            self.send_velocity_body(vx, vy, vz)
            return

        end_time = time.time() + duration_seconds
        while time.time() < end_time:
            self.send_velocity_body(vx, vy, vz)
            time.sleep(0.1)

        self.release_rc_override()

    def goto_local_ned(self, x: float, y: float, z: float) -> None:
        raise RuntimeError("Local position control needs GPS/position estimate. Use /sim/rc instead.")

    def set_yaw(
        self,
        yaw_degrees: float,
        yaw_speed_deg_per_sec: float = 20.0,
        is_relative: bool = False
    ) -> None:
        direction = 1 if yaw_degrees >= 0 else -1
        amount = min(abs(yaw_speed_deg_per_sec) / 100.0, 1.0)
        yaw_pwm = self.RC_NEUTRAL + int(direction * amount * self.CONTROL_PWM_RANGE)
        self.send_rc_override(yaw=yaw_pwm, duration_seconds=0.5)

    def send_simulated_rc(
        self,
        forward: float | None = None,
        right: float | None = None,
        up: float | None = None,
        yaw: float | None = None,
        roll_pwm: int | None = None,
        pitch_pwm: int | None = None,
        throttle_pwm: int | None = None,
        yaw_pwm: int | None = None,
        aux1_pwm: int | None = None,
        aux2_pwm: int | None = None,
        aux3_pwm: int | None = None,
        aux4_pwm: int | None = None,
        duration_seconds: float = 0.0,
        release_after: bool = False
    ) -> list[int]:
        roll = roll_pwm if roll_pwm is not None else self._axis_to_pwm(right)
        pitch = pitch_pwm if pitch_pwm is not None else self._axis_to_pwm(forward, invert=True)
        throttle = throttle_pwm if throttle_pwm is not None else self._axis_to_pwm(up)
        yaw_channel = yaw_pwm if yaw_pwm is not None else self._axis_to_pwm(yaw)

        return self.send_rc_override(
            roll=roll,
            pitch=pitch,
            throttle=throttle,
            yaw=yaw_channel,
            aux1=aux1_pwm,
            aux2=aux2_pwm,
            aux3=aux3_pwm,
            aux4=aux4_pwm,
            duration_seconds=duration_seconds,
            release_after=release_after
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

    def run_motor_test(
        self,
        motor: int,
        throttle_percent: float = 10.0,
        duration_seconds: float = 2.0,
        ack_timeout_seconds: float = 3.0
    ) -> dict[str, Any]:
        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
                0,
                motor,
                0,
                throttle_percent,
                duration_seconds,
                0,
                0,
                0
            )

        end_time = time.time() + ack_timeout_seconds
        while time.time() < end_time:
            with self._lock:
                ack = self.master.recv_match(type="COMMAND_ACK", blocking=True, timeout=0.2)

            if ack is None or int(ack.command) != mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST:
                continue

            return {
                "ack": True,
                "command": int(ack.command),
                "result": int(ack.result),
                "result_name": mavutil.mavlink.enums["MAV_RESULT"][int(ack.result)].name
            }

        return {"ack": False}

    def send_rc_override(
        self,
        roll: int | None = None,
        pitch: int | None = None,
        throttle: int | None = None,
        yaw: int | None = None,
        aux1: int | None = None,
        aux2: int | None = None,
        aux3: int | None = None,
        aux4: int | None = None,
        duration_seconds: float = 0.0,
        release_after: bool = False
    ) -> list[int]:
        channels = [
            self._pwm_or_ignore(roll),
            self._pwm_or_ignore(pitch),
            self._pwm_or_ignore(throttle),
            self._pwm_or_ignore(yaw),
            self._pwm_or_ignore(aux1),
            self._pwm_or_ignore(aux2),
            self._pwm_or_ignore(aux3),
            self._pwm_or_ignore(aux4),
        ]

        end_time = time.time() + duration_seconds
        while True:
            with self._lock:
                self.master.mav.rc_channels_override_send(
                    self.master.target_system,
                    self.master.target_component,
                    *channels
                )

            if duration_seconds <= 0 or time.time() >= end_time:
                break

            time.sleep(0.1)

        if release_after:
            self.release_rc_override()

        return channels

    def release_rc_override(self) -> None:
        with self._lock:
            self.master.mav.rc_channels_override_send(
                self.master.target_system,
                self.master.target_component,
                0, 0, 0, 0, 0, 0, 0, 0
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

        result: dict[str, Any] = {
            "connected": True,
            "connection": self.get_connection_info(),
            "last_heartbeat_time": self._last_heartbeat_time,
        }

        if heartbeat is not None:
            result["base_mode"] = int(heartbeat.base_mode)
            result["custom_mode"] = int(heartbeat.custom_mode)
            result["armed"] = (heartbeat.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0
            self._last_heartbeat_time = time.time()

        if attitude is not None:
            result["roll"] = float(attitude.roll)
            result["pitch"] = float(attitude.pitch)
            result["yaw"] = float(attitude.yaw)

        if altitude is not None:
            result["altitude_local_m"] = float(altitude.altitude_local)
            result["altitude_relative_m"] = float(altitude.altitude_relative)

        return result

    def reboot_autopilot(self) -> None:
        print("[REBOOT] Sende Reboot")
        with self._lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
                0,
                1, 0, 0, 0, 0, 0, 0
            )

    def _recv_status(self):
        with self._lock:
            return self.master.recv_match(
                type=["STATUSTEXT", "HEARTBEAT"],
                blocking=True,
                timeout=0.5
            )

    def _is_network_connection(self, connection_string: str) -> bool:
        return connection_string.lower().startswith(("tcp:", "udp:", "udpin:", "udpout:"))

    def _scaled_control(self, value: float) -> int:
        value = max(-1.0, min(1.0, value))
        return int(value * self.CONTROL_PWM_RANGE)

    def _axis_to_pwm(self, value: float | None, invert: bool = False) -> int | None:
        if value is None:
            return None

        scaled = self._scaled_control(value)
        if invert:
            scaled = -scaled

        return self.RC_NEUTRAL + scaled

    def _pwm_or_ignore(self, value: int | None) -> int:
        if value is None:
            return self.RC_IGNORE
        return max(self.RC_MIN, min(self.RC_MAX, int(value)))

    def pwm_to_thrust(self, pwm: int) -> float:
        pwm = max(self.RC_MIN, min(self.RC_MAX, int(pwm)))
        return (pwm - self.RC_MIN) / (self.RC_MAX - self.RC_MIN)

    @staticmethod
    def _mavlink_text_to_str(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip("\x00")
        if isinstance(value, bytearray):
            return bytes(value).decode("utf-8", errors="replace").strip("\x00")
        return str(value).strip("\x00")
