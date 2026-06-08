from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FlightMode(str, Enum):
    STABILIZE = "STABILIZE"
    GUIDED = "GUIDED"
    GUIDED_NOGPS = "GUIDED_NOGPS"
    LAND = "LAND"
    RTL = "RTL"
    LOITER = "LOITER"
    ALT_HOLD = "ALT_HOLD"


class ConnectRequest(BaseModel):
    connection_string: str = Field(..., min_length=1)
    baud_rate: int = Field(default=57600, ge=1)
    heartbeat_timeout_seconds: float = Field(default=5.0, gt=0.0, le=60.0)


class ModeRequest(BaseModel):
    mode: FlightMode


class TakeoffRequest(BaseModel):
    altitude_meters: float = Field(default=5.0, ge=1.0, le=100.0)
    arm_first: bool = True


class ThrottleRequest(BaseModel):
    throttle_pwm: int = Field(..., ge=1000, le=2000)
    duration_seconds: float = Field(default=2.0, ge=0.0, le=30.0)


class SimRcRequest(BaseModel):
    forward: float | None = Field(default=None, ge=-1.0, le=1.0)
    right: float | None = Field(default=None, ge=-1.0, le=1.0)
    up: float | None = Field(default=None, ge=-1.0, le=1.0)
    yaw: float | None = Field(default=None, ge=-1.0, le=1.0)
    roll_pwm: int | None = Field(default=None, ge=1000, le=2000)
    pitch_pwm: int | None = Field(default=None, ge=1000, le=2000)
    throttle_pwm: int | None = Field(default=None, ge=1000, le=2000)
    yaw_pwm: int | None = Field(default=None, ge=1000, le=2000)
    aux1_pwm: int | None = Field(default=None, ge=1000, le=2000)
    aux2_pwm: int | None = Field(default=None, ge=1000, le=2000)
    aux3_pwm: int | None = Field(default=None, ge=1000, le=2000)
    aux4_pwm: int | None = Field(default=None, ge=1000, le=2000)
    duration_seconds: float = Field(default=0.0, ge=0.0, le=30.0)
    release_after: bool = False


class MotorTestRequest(BaseModel):
    motor: int = Field(..., ge=1, le=8)
    throttle_percent: float = Field(default=10.0, ge=0.0, le=100.0)
    duration_seconds: float = Field(default=2.0, gt=0.0, le=30.0)


class VelocityBodyRequest(BaseModel):
    vx: float = Field(default=0.0, ge=-1.0, le=1.0)
    vy: float = Field(default=0.0, ge=-1.0, le=1.0)
    vz: float = Field(default=0.0, ge=-1.0, le=1.0)
    duration_seconds: float = Field(default=0.0, ge=0.0)


class LocalPositionRequest(BaseModel):
    x: float
    y: float
    z: float


class GlobalPositionRequest(BaseModel):
    latitude_deg: float = Field(..., ge=-90.0, le=90.0)
    longitude_deg: float = Field(..., ge=-180.0, le=180.0)
    altitude_meters: float = Field(default=5.0, ge=0.0, le=100.0)


class YawRequest(BaseModel):
    yaw_degrees: float
    yaw_speed_deg_per_sec: float = Field(default=20.0, gt=0.0)
    is_relative: bool = False


class RawCommandRequest(BaseModel):
    command_id: int
    param1: float = 0.0
    param2: float = 0.0
    param3: float = 0.0
    param4: float = 0.0
    param5: float = 0.0
    param6: float = 0.0
    param7: float = 0.0


class StoredCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=400)
    order_index: int = Field(default=0, ge=0)
    parameters: dict = Field(default_factory=dict)


class SequenceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=45)
    commands: list[StoredCommandRequest] = Field(default_factory=list)
    overwrite: bool = False


class RoutePointRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    altitude_meters: float = Field(default=5.0, ge=0.0, le=100.0)
    order_index: int = Field(default=0, ge=0)
    depends_on_point_id: str | None = None


class RouteCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=45)
    sequence_id: str | None = None
    points: list[RoutePointRequest] = Field(default_factory=list)
    overwrite: bool = False


class ExecuteRouteRequest(BaseModel):
    wait_seconds_between_points: float = Field(default=3.0, ge=0.0, le=30.0)
