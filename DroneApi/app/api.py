from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException

from app.command_executor import CommandExecutor
from app.drone_controller import DroneController
from DB.repository import DroneForgeRepository
from models.models import (
    ConnectRequest,
    ExecuteRouteRequest,
    GlobalPositionRequest,
    LocalPositionRequest,
    ModeRequest,
    RawCommandRequest,
    RouteCreateRequest,
    RoutePointRequest,
    SequenceCreateRequest,
    StoredCommandRequest,
    TakeoffRequest,
    ThrottleRequest,
    VelocityBodyRequest,
    VirtualJoystickRequest,
    YawRequest,
)

app = FastAPI(title="Drone Control API")

drone_controller = DroneController()
command_executor = CommandExecutor(drone_controller)
repository = DroneForgeRepository()


def _db_error(exception: Exception) -> HTTPException:
    if isinstance(exception, KeyError):
        return HTTPException(status_code=404, detail=str(exception))
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
            heartbeat_timeout_seconds=request.heartbeat_timeout_seconds,
        )

        return {
            "success": True,
            "message": "Verbunden",
            "connection": drone_controller.get_connection_info(),
        }
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/disconnect")
def disconnect() -> dict:
    try:
        drone_controller.disconnect()
        return {"success": True, "message": "Verbindung getrennt"}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.get("/status")
def get_status() -> dict:
    return drone_controller.get_status()


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
            arm_first=request.arm_first,
        )
        return {
            "success": True,
            "altitude_meters": request.altitude_meters,
            "mode": "GUIDED",
        }
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/throttle")
def throttle(request: ThrottleRequest) -> dict:
    try:
        drone_controller.send_throttle(
            throttle_pwm=request.throttle_pwm,
            duration_seconds=request.duration_seconds,
        )
        return {
            "success": True,
            "throttle_pwm": request.throttle_pwm,
            "duration_seconds": request.duration_seconds,
        }
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


@app.post("/velocity/body")
def send_velocity_body(request: VelocityBodyRequest) -> dict:
    try:
        drone_controller.move_body_for_duration(
            request.vx,
            request.vy,
            request.vz,
            request.duration_seconds,
        )
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/joystick/virtual")
def send_virtual_joystick(request: VirtualJoystickRequest) -> dict:
    try:
        drone_controller.send_virtual_joystick(
            request.forward,
            request.right,
            request.throttle,
            request.yaw,
            request.duration_seconds,
        )
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
            request.altitude_meters,
        )
        return {
            "success": True,
            "latitude_deg": request.latitude_deg,
            "longitude_deg": request.longitude_deg,
            "altitude_meters": request.altitude_meters,
        }
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.post("/yaw")
def set_yaw(request: YawRequest) -> dict:
    try:
        drone_controller.set_yaw(
            request.yaw_degrees,
            request.yaw_speed_deg_per_sec,
            request.is_relative,
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
            param7=request.param7,
        )
        return {"success": True}
    except Exception as exception:
        raise HTTPException(status_code=500, detail=str(exception))


@app.get("/db/health")
def get_database_health() -> dict:
    try:
        return repository.health()
    except Exception as exception:
        raise _db_error(exception)


@app.post("/sequences")
def create_sequence(request: SequenceCreateRequest) -> dict:
    try:
        return repository.create_sequence(
            request.name,
            [_model_to_dict(command) for command in request.commands],
        )
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


@app.post("/sequences/{sequence_id}/commands")
def add_command(sequence_id: str, request: StoredCommandRequest) -> dict:
    try:
        return repository.add_command(
            sequence_id,
            request.command,
            request.order_index,
            request.parameters,
        )
    except Exception as exception:
        raise _db_error(exception)


@app.post("/routes")
def create_route(request: RouteCreateRequest) -> dict:
    try:
        points = [_model_to_dict(point) for point in request.points]
        return repository.create_route(request.name, points, request.sequence_id)
    except Exception as exception:
        raise _db_error(exception)


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


@app.post("/routes/{route_id}/points")
def add_route_point(route_id: str, request: RoutePointRequest) -> dict:
    try:
        return repository.add_point(
            route_id,
            request.latitude,
            request.longitude,
            request.altitude_meters,
            request.order_index,
            request.depends_on_point_id,
        )
    except Exception as exception:
        raise _db_error(exception)


@app.post("/routes/{route_id}/execute-guided")
def execute_route_guided(route_id: str, request: ExecuteRouteRequest | None = None) -> dict:
    try:
        points = repository.get_route_points(route_id)
        if not points:
            raise ValueError("Route has no points.")

        drone_controller.set_mode("GUIDED")
        wait_seconds = request.wait_seconds_between_points if request else 0.2

        for point in points:
            drone_controller.goto_global_relative(
                point["latitude"],
                point["longitude"],
                point["altitude_meters"],
            )
            if wait_seconds > 0:
                time.sleep(wait_seconds)

        return {
            "success": True,
            "route_id": route_id,
            "points_executed": len(points),
            "mode": "GUIDED",
        }
    except Exception as exception:
        raise _db_error(exception)
