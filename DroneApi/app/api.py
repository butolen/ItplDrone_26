from __future__ import annotations

import time
import math
from typing import Any

from fastapi import FastAPI, HTTPException

from DroneApi.DB.repository import DroneForgeRepository
from DroneApi.app.command_executor import CommandExecutor
from DroneApi.app.drone_controller import DroneController
from DroneApi.models.models import (
    ConnectRequest,
    ExecuteRouteRequest,
    GlobalPositionRequest,
    LocalPositionRequest,
    ModeRequest,
    MotorTestRequest,
    RawCommandRequest,
    RouteCreateRequest,
    RoutePointRequest,
    SequenceCreateRequest,
    SimRcRequest,
    StoredCommandRequest,
    TakeoffRequest,
    ThrottleRequest,
    VelocityBodyRequest,
    YawRequest,
)

app = FastAPI(title="Drone Control API")

drone_controller = DroneController()
command_executor = CommandExecutor(drone_controller)
repository = DroneForgeRepository()


def _rc_response(channels: list[int], duration_seconds: float, release_after: bool) -> dict:
    return {
        "success": True,
        "mavlink_message": "RC_CHANNELS_OVERRIDE",
        "channels": {
            "roll": channels[0],
            "pitch": channels[1],
            "throttle": channels[2],
            "yaw": channels[3],
            "aux1": channels[4],
            "aux2": channels[5],
            "aux3": channels[6],
            "aux4": channels[7],
        },
        "duration_seconds": duration_seconds,
        "release_after": release_after
    }


def _db_error(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
    if isinstance(exception, ValueError):
        return HTTPException(status_code=409, detail=str(exception))
    return HTTPException(status_code=500, detail=str(exception))


def _model_to_dict(model: Any) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@app.post("/connect")
def connect(request: ConnectRequest) -> dict:
    try:
        drone_controller.connect(
            connection_string=request.connection_string,
            baud_rate=request.baud_rate,
            heartbeat_timeout_seconds=request.heartbeat_timeout_seconds
        )

        return {
            "success": True,
            "message": "Verbunden",
            "connection": drone_controller.get_connection_info()
        }
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/disconnect")
def disconnect() -> dict:
    try:
        drone_controller.disconnect()
        return {
            "success": True,
            "message": "Verbindung getrennt"
        }
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.get("/status")
def get_status() -> dict:
    return drone_controller.get_status()


@app.get("/telemetry")
def get_telemetry() -> dict:
    return drone_controller.get_telemetry()


@app.post("/mode")
def set_mode(request: ModeRequest) -> dict:
    try:
        drone_controller.set_mode(request.mode.value)
        return {"success": True, "mode": request.mode.value}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/arm")
def arm() -> dict:
    try:
        drone_controller.arm()
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/disarm")
def disarm() -> dict:
    try:
        drone_controller.disarm()
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/takeoff")
def takeoff(request: TakeoffRequest) -> dict:
    try:
        drone_controller.takeoff(
            altitude_meters=request.altitude_meters,
            arm_first=request.arm_first
        )
        return {
            "success": True,
            "altitude_meters": request.altitude_meters
        }
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/throttle")
def throttle(request: ThrottleRequest) -> dict:
    try:
        duration_seconds = drone_controller.send_throttle(
            throttle_pwm=request.throttle_pwm,
            duration_seconds=request.duration_seconds
        )
        return {
            "success": True,
            "throttle_pwm": request.throttle_pwm,
            "mavlink_message": "SET_ATTITUDE_TARGET",
            "thrust": drone_controller.pwm_to_thrust(request.throttle_pwm),
            "duration_seconds": duration_seconds
        }
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/motor/test")
def motor_test(request: MotorTestRequest) -> dict:
    try:
        result = drone_controller.run_motor_test(
            motor=request.motor,
            throttle_percent=request.throttle_percent,
            duration_seconds=request.duration_seconds
        )
        return {
            "success": True,
            "motor": request.motor,
            "throttle_percent": request.throttle_percent,
            "duration_seconds": request.duration_seconds,
            "mavlink_message": "MAV_CMD_DO_MOTOR_TEST",
            "result": result
        }
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/sim/rc")
def simulate_rc(request: SimRcRequest) -> dict:
    try:
        channels = drone_controller.send_simulated_rc(
            forward=request.forward,
            right=request.right,
            up=request.up,
            yaw=request.yaw,
            roll_pwm=request.roll_pwm,
            pitch_pwm=request.pitch_pwm,
            throttle_pwm=request.throttle_pwm,
            yaw_pwm=request.yaw_pwm,
            aux1_pwm=request.aux1_pwm,
            aux2_pwm=request.aux2_pwm,
            aux3_pwm=request.aux3_pwm,
            aux4_pwm=request.aux4_pwm,
            duration_seconds=request.duration_seconds,
            release_after=request.release_after
        )
        return _rc_response(channels, request.duration_seconds, request.release_after)
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/sim/rc/body")
def simulate_rc_body(request: VelocityBodyRequest) -> dict:
    try:
        channels = drone_controller.send_simulated_rc(
            forward=request.vx,
            right=request.vy,
            up=-request.vz,
            duration_seconds=request.duration_seconds,
            release_after=request.duration_seconds > 0
        )
        return _rc_response(channels, request.duration_seconds, request.duration_seconds > 0)
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/sim/rc/yaw")
def simulate_rc_yaw(request: YawRequest) -> dict:
    try:
        direction = 1.0 if request.yaw_degrees >= 0 else -1.0
        amount = min(abs(request.yaw_speed_deg_per_sec) / 100.0, 1.0)
        channels = drone_controller.send_simulated_rc(
            yaw=direction * amount,
            duration_seconds=0.5,
            release_after=True
        )
        return _rc_response(channels, 0.5, True)
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/sim/rc/release")
def release_simulated_rc() -> dict:
    try:
        drone_controller.release_rc_override()
        return {"success": True, "mavlink_message": "RC_CHANNELS_OVERRIDE", "released": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/land")
def land() -> dict:
    try:
        drone_controller.land()
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/rtl")
def rtl() -> dict:
    try:
        drone_controller.rtl()
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/position/local")
def goto_local_position(request: LocalPositionRequest) -> dict:
    try:
        drone_controller.goto_local_ned(request.x, request.y, request.z)
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/position/global")
def goto_global_position(request: GlobalPositionRequest) -> dict:
    try:
        drone_controller.goto_global_relative(
            request.latitude_deg,
            request.longitude_deg,
            request.altitude_meters
        )
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/yaw")
def yaw(request: YawRequest) -> dict:
    try:
        drone_controller.set_yaw(
            yaw_degrees=request.yaw_degrees,
            yaw_speed_deg_per_sec=request.yaw_speed_deg_per_sec,
            is_relative=request.is_relative
        )
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/command/raw")
def send_raw_command(request: RawCommandRequest) -> dict:
    try:
        drone_controller.send_raw_command(
            command_id=request.command_id,
            param1=request.param1,
            param2=request.param2,
            param3=request.param3,
            param4=request.param4,
            param5=request.param5,
            param6=request.param6,
            param7=request.param7
        )
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.get("/db/health")
def database_health() -> dict:
    try:
        return repository.health()
    except Exception as exception:
        raise _db_error(exception)


@app.post("/sequences")
def create_sequence(request: SequenceCreateRequest) -> dict:
    try:
        commands = [_model_to_dict(command) for command in request.commands]
        return repository.create_sequence(request.name, commands, overwrite=request.overwrite)
    except Exception as exception:
        raise _db_error(exception)


@app.get("/sequences")
def list_sequences() -> list[dict]:
    try:
        return repository.list_sequences()
    except Exception as exception:
        raise _db_error(exception)


@app.get("/sequences/{sequence_id}")
def get_sequence(sequence_id: str) -> dict:
    try:
        return repository.get_sequence(sequence_id)
    except Exception as exception:
        raise _db_error(exception)


@app.delete("/sequences/{sequence_id}")
def delete_sequence(sequence_id: str) -> dict:
    try:
        return repository.delete_sequence(sequence_id)
    except Exception as exception:
        raise _db_error(exception)


@app.post("/sequences/{sequence_id}/commands")
def add_sequence_command(sequence_id: str, request: StoredCommandRequest) -> dict:
    try:
        return repository.add_command(
            sequence_id=sequence_id,
            command=request.command,
            order_index=request.order_index,
            parameters=request.parameters
        )
    except Exception as exception:
        raise _db_error(exception)


@app.post("/routes")
def create_route(request: RouteCreateRequest) -> dict:
    try:
        points = [_model_to_dict(point) for point in request.points]
        return repository.create_route(
            name=request.name,
            sequence_id=request.sequence_id,
            points=points,
            overwrite=request.overwrite
        )
    except Exception as exception:
        raise _db_error(exception)


@app.post("/navigation/routes")
def create_navigation_route(request: RouteCreateRequest) -> dict:
    try:
        points = [_model_to_dict(point) for point in request.points]
        return repository.create_route(
            name=request.name,
            sequence_id=None,
            points=points,
            overwrite=request.overwrite
        )
    except Exception as exception:
        raise _db_error(exception)


@app.get("/navigation/routes")
def list_navigation_routes() -> list[dict]:
    try:
        return repository.list_routes()
    except Exception as exception:
        raise _db_error(exception)


@app.get("/navigation/routes/{route_id}")
def get_navigation_route(route_id: str) -> dict:
    try:
        return repository.get_route(route_id)
    except Exception as exception:
        raise _db_error(exception)


@app.delete("/navigation/routes/{route_id}")
def delete_navigation_route(route_id: str) -> dict:
    try:
        return repository.delete_route(route_id)
    except Exception as exception:
        raise _db_error(exception)


@app.post("/navigation/routes/{route_id}/execute-guided")
def execute_navigation_route(route_id: str, request: ExecuteRouteRequest | None = None) -> dict:
    return execute_guided_route(route_id, request)


@app.get("/routes")
def list_routes() -> list[dict]:
    try:
        return repository.list_routes()
    except Exception as exception:
        raise _db_error(exception)


@app.get("/routes/{route_id}")
def get_route(route_id: str) -> dict:
    try:
        return repository.get_route(route_id)
    except Exception as exception:
        raise _db_error(exception)


@app.delete("/routes/{route_id}")
def delete_route(route_id: str) -> dict:
    try:
        return repository.delete_route(route_id)
    except Exception as exception:
        raise _db_error(exception)


@app.post("/routes/{route_id}/points")
def add_route_point(route_id: str, request: RoutePointRequest) -> dict:
    try:
        return repository.add_point(
            route_id=route_id,
            latitude=request.latitude,
            longitude=request.longitude,
            altitude_meters=request.altitude_meters,
            order_index=request.order_index,
            depends_on_point_id=request.depends_on_point_id
        )
    except Exception as exception:
        raise _db_error(exception)


@app.post("/routes/{route_id}/execute-guided")
def execute_guided_route(route_id: str, request: ExecuteRouteRequest | None = None) -> dict:
    try:
        points = repository.get_route_points(route_id)
        wait_seconds = request.wait_seconds_between_points if request else 3.0
        executed_points = 0

        for index, point in enumerate(points, start=1):
            altitude = float(point["altitude_meters"])
            ground_altitude = _prepare_for_takeoff()
            target_altitude = ground_altitude + max(1.0, altitude)
            drone_controller.takeoff(altitude_meters=target_altitude, arm_first=False)
            drone_controller.goto_global_relative(
                point["latitude"],
                point["longitude"],
                target_altitude
            )
            _wait_for_route_point(point, target_altitude=target_altitude, timeout_seconds=120.0)
            drone_controller.land()
            _wait_for_landing(timeout_seconds=90.0)
            executed_points = index

            if wait_seconds > 0:
                time.sleep(wait_seconds)

        return {
            "success": True,
            "route_id": route_id,
            "points_executed": executed_points,
            "mode": "LAND"
        }
    except Exception as exception:
        raise _db_error(exception)


def _prepare_for_takeoff(timeout_seconds: float = 30.0) -> float:
    end_time = time.time() + timeout_seconds
    stable_since: float | None = None
    stable_reference_altitude: float | None = None

    while time.time() < end_time:
        telemetry = drone_controller.get_telemetry()
        altitude = float(telemetry.get("relative_alt") or 0.0)
        armed = bool(telemetry.get("armed"))

        if stable_reference_altitude is None or abs(altitude - stable_reference_altitude) > 0.05:
            stable_reference_altitude = altitude
            stable_since = time.time()
        elif stable_since is not None and time.time() - stable_since >= 3.0 and not armed:
            drone_controller.set_mode("GUIDED")
            time.sleep(0.5)
            drone_controller.arm()
            return stable_reference_altitude

        if armed and stable_since is not None and time.time() - stable_since >= 3.0:
            try:
                drone_controller.disarm()
            except Exception:
                pass

        time.sleep(0.5)

    raise TimeoutError("Drone did not become ready for the next takeoff.")


def _wait_for_route_point(point: dict, target_altitude: float, timeout_seconds: float) -> None:
    target_latitude = float(point["latitude"])
    target_longitude = float(point["longitude"])
    end_time = time.time() + timeout_seconds

    while time.time() < end_time:
        telemetry = drone_controller.get_telemetry()
        latitude = float(telemetry.get("latitude") or 0.0)
        longitude = float(telemetry.get("longitude") or 0.0)
        altitude = float(telemetry.get("relative_alt") or 0.0)

        if latitude and longitude:
            distance_meters = _distance_meters(latitude, longitude, target_latitude, target_longitude)
            if distance_meters <= 2.5 and abs(altitude - target_altitude) <= 1.0:
                return

        time.sleep(0.5)

    raise TimeoutError(f"Route point not reached: {target_latitude:.7f}, {target_longitude:.7f}")


def _wait_for_landing(timeout_seconds: float) -> None:
    end_time = time.time() + timeout_seconds
    stable_since: float | None = None
    stable_reference_altitude: float | None = None

    while time.time() < end_time:
        telemetry = drone_controller.get_telemetry()
        altitude = float(telemetry.get("relative_alt") or 0.0)
        armed = bool(telemetry.get("armed"))
        mode = str(telemetry.get("mode") or "").upper()

        if mode == "LAND":
            if stable_reference_altitude is None or abs(altitude - stable_reference_altitude) > 0.05:
                stable_reference_altitude = altitude
                stable_since = time.time()
            elif stable_since is not None and time.time() - stable_since >= 3.0:
                try:
                    drone_controller.disarm()
                except Exception:
                    pass

                time.sleep(0.75)
                telemetry = drone_controller.get_telemetry()
                if not bool(telemetry.get("armed")):
                    return

                stable_since = time.time()
        else:
            stable_since = None
            stable_reference_altitude = None

        if stable_since is not None and time.time() - stable_since >= 3.0 and not armed:
            return

        time.sleep(0.5)

    raise TimeoutError("Landing timeout before next route point.")


def _distance_meters(first_latitude: float, first_longitude: float, second_latitude: float, second_longitude: float) -> float:
    latitude_scale = 111_320.0
    average_latitude = math.radians((first_latitude + second_latitude) / 2.0)
    longitude_scale = latitude_scale * math.cos(average_latitude)
    north = (second_latitude - first_latitude) * latitude_scale
    east = (second_longitude - first_longitude) * longitude_scale
    return (north * north + east * east) ** 0.5
