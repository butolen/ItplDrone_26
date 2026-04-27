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
    public string Mode { get; set; } = "GUIDED";
}

public class TakeoffRequest
{
    [JsonPropertyName("altitude_meters")]
    public double AltitudeMeters { get; set; } = 5.0;
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