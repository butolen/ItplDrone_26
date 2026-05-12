# MavlinkSender Drone API

FastAPI service for sending MAVLink commands to a drone or flight controller.

This API can control a real vehicle. Test with props removed first. The API does not enforce a full safety workflow; it sends the MAVLink messages requested by the endpoint.

## Running

Start the API from the `DroneApi` folder:

```powershell
python main.py
```

FastAPI also exposes interactive docs when the server is running:

```text
http://localhost:8000/docs
```

## Supported Flight Modes

The `/mode` endpoint accepts these modes:

| Mode | Use |
| --- | --- |
| `STABILIZE` | Manual stabilization mode. Useful for RC-style control, depending on the flight controller setup. |
| `GUIDED` | Guided control with GPS or position estimate. Use for guided MAVLink commands when position data is available. |
| `GUIDED_NOGPS` | Guided control without GPS. Best fit for `/throttle` because it sends attitude/thrust setpoints. |
| `ALT_HOLD` | Holds altitude using onboard sensors. RC-style roll, pitch, throttle, yaw overrides may be used depending on firmware configuration. |
| `LAND` | Autopilot landing mode. |
| `RTL` | Return-to-launch mode. Requires GPS/home position. This project's `/rtl` endpoint currently rejects RTL for no-GPS setups. |
| `LOITER` | Holds position. Requires GPS or position estimate. |

Mode support depends on the firmware loaded on the flight controller. If the mode is not in `master.mode_mapping()`, `/mode` returns an error.

## Typical Command Order

For a no-GPS ESP32 drone using RC-style control:

```text
POST /connect
POST /mode {"mode": "STABILIZE"} or {"mode": "ALT_HOLD"}
POST /arm
POST /sim/rc repeatedly from your controller loop
POST /disarm
POST /disconnect
```

For attitude/thrust control:

```text
POST /connect
POST /mode {"mode": "GUIDED_NOGPS"}
POST /arm
POST /throttle
POST /disarm
POST /disconnect
```

## Common Values

PWM channel values use normal RC ranges:

| PWM | Meaning |
| --- | --- |
| `1000` | Minimum stick/channel value |
| `1500` | Neutral stick/channel value |
| `2000` | Maximum stick/channel value |
| `65535` | Ignore channel, used internally when a `/sim/rc` field is omitted |

For `/sim/rc`, channel mapping is:

| Field | RC Channel | Function |
| --- | --- | --- |
| `roll_pwm` | CH1 | Roll |
| `pitch_pwm` | CH2 | Pitch |
| `throttle_pwm` | CH3 | Throttle |
| `yaw_pwm` | CH4 | Yaw |
| `aux1_pwm` | CH5 | Aux 1 |
| `aux2_pwm` | CH6 | Aux 2 |
| `aux3_pwm` | CH7 | Aux 3 |
| `aux4_pwm` | CH8 | Aux 4 |

For GUI keyboard control, use normalized axes on `/sim/rc`:

| Key | Field | Value |
| --- | --- | --- |
| `W` | `forward` | `1.0` |
| `S` | `forward` | `-1.0` |
| `D` | `right` | `1.0` |
| `A` | `right` | `-1.0` |
| `Space` | `up` | `1.0` |
| Descend key, for example `Shift` | `up` | `-1.0` |
| Turn right key | `yaw` | `1.0` |
| Turn left key | `yaw` | `-1.0` |

Axis values can be combined. For example, holding `W` and `D` sends `{"forward": 1.0, "right": 1.0}`.

## Endpoints

### `POST /connect`

Opens the MAVLink connection and waits for a heartbeat.

Request:

```json
{
  "connection_string": "COM3",
  "baud_rate": 57600,
  "heartbeat_timeout_seconds": 5.0
}
```

Network examples:

```json
{
  "connection_string": "udp:127.0.0.1:14550"
}
```

Response:

```json
{
  "success": true,
  "message": "Verbunden",
  "connection": {
    "connected": true,
    "connection_string": "COM3",
    "baud_rate": 57600,
    "target_system": 1,
    "target_component": 1
  }
}
```

### `POST /disconnect`

Closes the active MAVLink connection.

Request body: none.

Response:

```json
{
  "success": true,
  "message": "Verbindung getrennt"
}
```

### `GET /status`

Returns connection status and the latest available heartbeat, attitude, and altitude data.

Request body: none.

Response example:

```json
{
  "connected": true,
  "connection": {
    "connected": true,
    "connection_string": "COM3",
    "baud_rate": 57600,
    "target_system": 1,
    "target_component": 1
  },
  "last_heartbeat_time": 1778480000.0,
  "base_mode": 81,
  "custom_mode": 0,
  "armed": false,
  "roll": 0.0,
  "pitch": 0.0,
  "yaw": 0.0,
  "altitude_local_m": 0.0,
  "altitude_relative_m": 0.0
}
```

### `POST /mode`

Sets the flight mode.

Supported request values:

```text
STABILIZE, GUIDED, GUIDED_NOGPS, LAND, RTL, LOITER, ALT_HOLD
```

Request:

```json
{
  "mode": "GUIDED_NOGPS"
}
```

Response:

```json
{
  "success": true,
  "mode": "GUIDED_NOGPS"
}
```

### `POST /arm`

Arms the vehicle and waits up to 10 seconds until a heartbeat reports armed state.

Request body: none.

Response:

```json
{
  "success": true
}
```

### `POST /disarm`

Sends minimum throttle briefly, then disarms the vehicle.

Request body: none.

Response:

```json
{
  "success": true
}
```

### `POST /takeoff`

Optional arm, then sends throttle using `SET_ATTITUDE_TARGET`.

Best mode: `GUIDED_NOGPS` for no-GPS attitude/thrust control, or `GUIDED` when position estimate/GPS is available.

Request:

```json
{
  "throttle_pwm": 1600,
  "duration_seconds": 2.0,
  "arm_first": false
}
```

Validation:

| Field | Range |
| --- | --- |
| `throttle_pwm` | `1000..2000` |
| `duration_seconds` | `0..30` |
| `arm_first` | `true` or `false` |

Response:

```json
{
  "success": true,
  "throttle_pwm": 1600,
  "duration_seconds": 2.0
}
```

### `POST /throttle`

Sends repeated MAVLink `SET_ATTITUDE_TARGET` messages with neutral attitude and calculated thrust.

Best mode: `GUIDED_NOGPS` or `GUIDED`.

This endpoint does not arm or change mode. Set mode and arm before calling it.

Request:

```json
{
  "throttle_pwm": 1600,
  "duration_seconds": 2.0
}
```

Validation:

| Field | Range |
| --- | --- |
| `throttle_pwm` | `1000..2000` |
| `duration_seconds` | `0..30`; `0` falls back to the default duration of `2.0` seconds |

Throttle conversion:

```text
thrust = (throttle_pwm - 1000) / 1000
```

Examples:

| PWM | MAVLink thrust |
| --- | --- |
| `1000` | `0.0` |
| `1500` | `0.5` |
| `2000` | `1.0` |

Response:

```json
{
  "success": true,
  "throttle_pwm": 1600,
  "mavlink_message": "SET_ATTITUDE_TARGET",
  "thrust": 0.6,
  "duration_seconds": 2.0
}
```

### `POST /sim/rc`

Simulates an RC transmitter by sending MAVLink `RC_CHANNELS_OVERRIDE`.

Best modes: `STABILIZE`, `ALT_HOLD`, or another mode configured to accept RC input. This endpoint is the best fit for an ESP32 controller that should function like a real RC transmitter.

Use `duration_seconds: 0` when your ESP32 sends updates repeatedly in a loop. Use a positive duration if you want the API to stream the same RC command for that many seconds.

Request using GUI axes:

```json
{
  "forward": 1.0,
  "right": 0.0,
  "up": 0.0,
  "yaw": 0.0,
  "duration_seconds": 0.0,
  "release_after": false
}
```

Request using direct PWM override:

```json
{
  "forward": null,
  "right": null,
  "up": null,
  "yaw": null,
  "roll_pwm": 1500,
  "pitch_pwm": 1500,
  "throttle_pwm": 1200,
  "yaw_pwm": 1500,
  "aux1_pwm": 1000,
  "aux2_pwm": null,
  "aux3_pwm": null,
  "aux4_pwm": null,
  "duration_seconds": 0.0,
  "release_after": false
}
```

All axis and channel fields are optional. Omitted or `null` fields are sent as `65535`, which tells the flight controller to ignore that channel. Direct PWM values override axis values for the same channel. For example, if both `right` and `roll_pwm` are provided, `roll_pwm` wins.

Axis mapping:

```text
roll_pwm     = 1500 + right * 400
pitch_pwm    = 1500 - forward * 400
throttle_pwm = 1500 + up * 400
yaw_pwm      = 1500 + yaw * 400
```

Validation:

| Field | Range |
| --- | --- |
| `forward` | `-1..1` or `null` |
| `right` | `-1..1` or `null` |
| `up` | `-1..1` or `null` |
| `yaw` | `-1..1` or `null` |
| `roll_pwm` | `1000..2000` or `null` |
| `pitch_pwm` | `1000..2000` or `null` |
| `throttle_pwm` | `1000..2000` or `null` |
| `yaw_pwm` | `1000..2000` or `null` |
| `aux1_pwm` | `1000..2000` or `null` |
| `aux2_pwm` | `1000..2000` or `null` |
| `aux3_pwm` | `1000..2000` or `null` |
| `aux4_pwm` | `1000..2000` or `null` |
| `duration_seconds` | `0..30` |
| `release_after` | `true` or `false` |

Response:

```json
{
  "success": true,
  "mavlink_message": "RC_CHANNELS_OVERRIDE",
  "channels": {
    "roll": 1500,
    "pitch": 1500,
    "throttle": 1200,
    "yaw": 1500,
    "aux1": 1000,
    "aux2": 65535,
    "aux3": 65535,
    "aux4": 65535
  },
  "duration_seconds": 0.0,
  "release_after": false
}
```

### `POST /sim/rc/body`

Compatibility endpoint for body-frame movement values. It still sends `RC_CHANNELS_OVERRIDE`, so it lives under `/sim/rc`.

Prefer `/sim/rc` for new GUI code because its `forward`, `right`, `up`, and `yaw` fields map directly to keyboard controls.

Request:

```json
{
  "vx": 1.0,
  "vy": 0.0,
  "vz": 0.0,
  "duration_seconds": 0.0
}
```

Mapping:

```text
forward = vx
right = vy
up = -vz
```

Validation:

| Field | Range |
| --- | --- |
| `vx` | `-1..1` |
| `vy` | `-1..1` |
| `vz` | `-1..1` |
| `duration_seconds` | `>=0` |

Response shape is the same as `/sim/rc`.

### `POST /sim/rc/yaw`

Compatibility endpoint for yaw-only RC override. It still sends `RC_CHANNELS_OVERRIDE`, so it lives under `/sim/rc`.

Request:

```json
{
  "yaw_degrees": 20.0,
  "yaw_speed_deg_per_sec": 20.0,
  "is_relative": false
}
```

Current behavior:

```text
direction = sign(yaw_degrees)
amount = min(abs(yaw_speed_deg_per_sec) / 100, 1)
yaw_pwm = 1500 + direction * amount * 400
duration_seconds = 0.5
release_after = true
```

`is_relative` is accepted by the API, but the current implementation does not use it differently.

Response shape is the same as `/sim/rc`.

### `POST /sim/rc/release`

Releases all RC channel overrides by sending zero for channels 1-8.

Request body: none.

Response:

```json
{
  "success": true,
  "mavlink_message": "RC_CHANNELS_OVERRIDE",
  "released": true
}
```

### `POST /motor/test`

Sends MAVLink `MAV_CMD_DO_MOTOR_TEST` for one motor.

Use only with props removed. This endpoint is for motor testing, not normal flight control.

Request:

```json
{
  "motor": 1,
  "throttle_percent": 10.0,
  "duration_seconds": 2.0
}
```

Validation:

| Field | Range |
| --- | --- |
| `motor` | `1..8` |
| `throttle_percent` | `0..100` |
| `duration_seconds` | `>0..30` |

Response:

```json
{
  "success": true,
  "motor": 1,
  "throttle_percent": 10.0,
  "duration_seconds": 2.0,
  "mavlink_message": "MAV_CMD_DO_MOTOR_TEST",
  "result": {
    "ack": true,
    "command": 209,
    "result": 0,
    "result_name": "MAV_RESULT_ACCEPTED"
  }
}
```

### `POST /land`

Sends low throttle with `SET_ATTITUDE_TARGET`, then sends minimum throttle briefly.

Best mode: `GUIDED_NOGPS` or `GUIDED`, because it uses the same throttle path as `/throttle`.

Request body: none.

Response:

```json
{
  "success": true
}
```

### `POST /rtl`

Currently always returns an error:

```text
RTL needs GPS. Use /land or /throttle for this no-GPS setup.
```

RTL requires GPS/home position. The code intentionally rejects it for this no-GPS setup.

### `POST /position/local`

Currently always returns an error:

```text
Local position control needs GPS/position estimate. Use /sim/rc instead.
```

This endpoint is reserved for local-position control, but the current implementation does not support it. For no-GPS simulated RC movement, use `/sim/rc`.

Request:

```json
{
  "x": 0.0,
  "y": 0.0,
  "z": -1.0
}
```

### `POST /command/raw`

Sends a raw MAVLink `COMMAND_LONG`.

Use this only when you know the MAVLink command id and parameters.

Request:

```json
{
  "command_id": 400,
  "param1": 1.0,
  "param2": 0.0,
  "param3": 0.0,
  "param4": 0.0,
  "param5": 0.0,
  "param6": 0.0,
  "param7": 0.0
}
```

Response:

```json
{
  "success": true
}
```

## Error Behavior

Invalid JSON or out-of-range fields return FastAPI/Pydantic validation errors with HTTP `422`.

Runtime errors, such as no active MAVLink connection or unsupported flight mode, return HTTP `500` with the error text in `detail`.

Example:

```json
{
  "detail": "Keine aktive MAVLink-Verbindung."
}
```
