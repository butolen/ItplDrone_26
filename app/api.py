from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.command_executor import CommandExecutor
from app.drone_controller import DroneController
from models.models import (
    ConnectRequest,
    LocalPositionRequest,
    ModeRequest,
    RawCommandRequest,
    TakeoffRequest,
    VelocityBodyRequest,
    YawRequest,
)

app = FastAPI(title="Drone Control API")

drone_controller = DroneController()
command_executor = CommandExecutor(drone_controller)


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
        drone_controller.takeoff(request.altitude_meters)
        return {"success": True, "altitude_meters": request.altitude_meters}
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
            request.duration_seconds
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


@app.post("/yaw")
def set_yaw(request: YawRequest) -> dict:
    try:
        drone_controller.set_yaw(
            request.yaw_degrees,
            request.yaw_speed_deg_per_sec,
            request.is_relative
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