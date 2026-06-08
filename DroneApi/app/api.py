from __future__ import annotations

from fastapi import FastAPI, HTTPException

from DroneApi.app.command_executor import CommandExecutor
from DroneApi.app.drone_controller import DroneController
from DroneApi.models.models import (
    ConnectRequest,
    LocalPositionRequest,
    ModeRequest,
    MotorTestRequest,
    RawCommandRequest,
    SimRcRequest,
    TakeoffRequest,
    ThrottleRequest,
    VelocityBodyRequest,
    YawRequest,
)

app = FastAPI(title="Drone Control API")

drone_controller = DroneController()
command_executor = CommandExecutor(drone_controller)


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
            throttle_pwm=request.throttle_pwm,
            duration_seconds=request.duration_seconds,
            arm_first=request.arm_first
        )
        return {
            "success": True,
            "throttle_pwm": request.throttle_pwm,
            "duration_seconds": request.duration_seconds
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
