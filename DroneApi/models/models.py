from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FlightMode(str, Enum):
    STABILIZE = "STABILIZE"
    GUIDED = "GUIDED"
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
    altitude_meters: float = Field(..., gt=0.0)


class VelocityBodyRequest(BaseModel):
    vx: float
    vy: float
    vz: float
    duration_seconds: float = Field(default=0.0, ge=0.0)


class LocalPositionRequest(BaseModel):
    x: float
    y: float
    z: float


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