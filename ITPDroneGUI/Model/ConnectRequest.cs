using System.Text.Json.Serialization;

public class ConnectRequest
{
    [JsonPropertyName("connection_string")]
    public string ConnectionString { get; set; } = "udpin:0.0.0.0:14551";

    [JsonPropertyName("baud_rate")]
    public int BaudRate { get; set; } = 57600;

    [JsonPropertyName("heartbeat_timeout_seconds")]
    public double HeartbeatTimeoutSeconds { get; set; } = 10.0;
}

public class ModeRequest
{
    [JsonPropertyName("mode")]
    public string Mode { get; set; } = "STABILIZE";
}

public class TakeoffRequest
{
    [JsonPropertyName("altitude_meters")]
    public double AltitudeMeters { get; set; } = 5.0;

    [JsonPropertyName("arm_first")]
    public bool ArmFirst { get; set; } = true;
}

public class ThrottleRequest
{
    [JsonPropertyName("throttle_pwm")]
    public int ThrottlePwm { get; set; } = 1500;

    [JsonPropertyName("duration_seconds")]
    public double DurationSeconds { get; set; } = 0.2;
}

public class VelocityBodyRequest
{
    [JsonPropertyName("vx")]
    public double Vx { get; set; }

    [JsonPropertyName("vy")]
    public double Vy { get; set; }

    [JsonPropertyName("vz")]
    public double Vz { get; set; }

    [JsonPropertyName("duration_seconds")]
    public double DurationSeconds { get; set; }
}
