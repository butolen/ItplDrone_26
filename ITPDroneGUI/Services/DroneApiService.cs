using System.Net.Http.Json;
using System.Text.Json.Serialization;

public class DroneApiService
{
    private readonly HttpClient _httpClient;
    private readonly string _apiBaseUrl;

    public DroneApiService(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient;
        _apiBaseUrl = configuration["DroneApi:BaseUrl"] ?? "http://127.0.0.1:8000";
    }

    public class ApiResponse<T>
    {
        public bool Success { get; set; }
        public T? Data { get; set; }
        public string? ErrorMessage { get; set; }
        public string? ResponseBody { get; set; }
    }

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

    public class VirtualJoystickRequest
    {
        [JsonPropertyName("forward")]
        public double Forward { get; set; }

        [JsonPropertyName("right")]
        public double Right { get; set; }

        [JsonPropertyName("throttle")]
        public double Throttle { get; set; }

        [JsonPropertyName("yaw")]
        public double Yaw { get; set; }

        [JsonPropertyName("duration_seconds")]
        public double DurationSeconds { get; set; }
    }

    public class LocalPositionRequest
    {
        [JsonPropertyName("x")]
        public double X { get; set; }

        [JsonPropertyName("y")]
        public double Y { get; set; }

        [JsonPropertyName("z")]
        public double Z { get; set; }
    }

    public class GlobalPositionRequest
    {
        [JsonPropertyName("latitude_deg")]
        public double LatitudeDeg { get; set; }

        [JsonPropertyName("longitude_deg")]
        public double LongitudeDeg { get; set; }

        [JsonPropertyName("altitude_meters")]
        public double AltitudeMeters { get; set; }
    }

    public class YawRequest
    {
        [JsonPropertyName("yaw_degrees")]
        public double YawDegrees { get; set; }

        [JsonPropertyName("yaw_speed_deg_per_sec")]
        public double YawSpeedDegPerSec { get; set; } = 20.0;

        [JsonPropertyName("is_relative")]
        public bool IsRelative { get; set; }
    }

    public class RawCommandRequest
    {
        [JsonPropertyName("command_id")]
        public int CommandId { get; set; }

        [JsonPropertyName("param1")]
        public double Param1 { get; set; }

        [JsonPropertyName("param2")]
        public double Param2 { get; set; }

        [JsonPropertyName("param3")]
        public double Param3 { get; set; }

        [JsonPropertyName("param4")]
        public double Param4 { get; set; }

        [JsonPropertyName("param5")]
        public double Param5 { get; set; }

        [JsonPropertyName("param6")]
        public double Param6 { get; set; }

        [JsonPropertyName("param7")]
        public double Param7 { get; set; }
    }

    public async Task<ApiResponse<T>> PostAsync<T>(string endpoint, object? payload = null)
    {
        try
        {
            var content = JsonContent.Create(payload ?? new { });
            var response = await _httpClient.PostAsync($"{_apiBaseUrl}{endpoint}", content);
            var responseBody = await response.Content.ReadAsStringAsync();

            if (!response.IsSuccessStatusCode)
            {
                return new ApiResponse<T>
                {
                    Success = false,
                    ErrorMessage = $"Status {(int)response.StatusCode} {response.StatusCode}",
                    ResponseBody = responseBody,
                };
            }

            T? data = default;
            if (!string.IsNullOrWhiteSpace(responseBody))
            {
                try
                {
                    data = await response.Content.ReadFromJsonAsync<T>();
                }
                catch
                {
                    data = default;
                }
            }

            return new ApiResponse<T>
            {
                Success = true,
                Data = data,
                ResponseBody = responseBody,
            };
        }
        catch (Exception ex)
        {
            return new ApiResponse<T>
            {
                Success = false,
                ErrorMessage = ex.Message,
            };
        }
    }

    public Task<ApiResponse<object>> Connect(
        string connectionString = "udpin:0.0.0.0:14551",
        int baudRate = 57600,
        double heartbeatTimeoutSeconds = 10.0)
    {
        return PostAsync<object>("/connect", new ConnectRequest
        {
            ConnectionString = connectionString,
            BaudRate = baudRate,
            HeartbeatTimeoutSeconds = heartbeatTimeoutSeconds,
        });
    }

    public Task<string> GetStatus()
    {
        return _httpClient.GetStringAsync($"{_apiBaseUrl}/status");
    }

    public Task<ApiResponse<object>> SetMode(string mode)
    {
        return PostAsync<object>("/mode", new ModeRequest { Mode = mode });
    }

    public Task<ApiResponse<object>> Arm()
    {
        return PostAsync<object>("/arm");
    }

    public Task<ApiResponse<object>> Disarm()
    {
        return PostAsync<object>("/disarm");
    }

    public Task<ApiResponse<object>> Takeoff(double altitudeMeters = 5.0, bool armFirst = true)
    {
        return PostAsync<object>("/takeoff", new TakeoffRequest
        {
            AltitudeMeters = altitudeMeters,
            ArmFirst = armFirst,
        });
    }

    public Task<ApiResponse<object>> SendThrottle(int throttlePwm, double durationSeconds)
    {
        return PostAsync<object>("/throttle", new ThrottleRequest
        {
            ThrottlePwm = throttlePwm,
            DurationSeconds = durationSeconds,
        });
    }

    public Task<ApiResponse<object>> SendVelocity(double vx, double vy, double vz, double durationSeconds)
    {
        return PostAsync<object>("/velocity/body", new VelocityBodyRequest
        {
            Vx = vx,
            Vy = vy,
            Vz = vz,
            DurationSeconds = durationSeconds,
        });
    }

    public Task<ApiResponse<object>> SendVirtualJoystick(
        double forward,
        double right,
        double throttle,
        double yaw,
        double durationSeconds)
    {
        return PostAsync<object>("/joystick/virtual", new VirtualJoystickRequest
        {
            Forward = forward,
            Right = right,
            Throttle = throttle,
            Yaw = yaw,
            DurationSeconds = durationSeconds,
        });
    }

    public Task<ApiResponse<object>> Land()
    {
        return PostAsync<object>("/land");
    }

    public Task<ApiResponse<object>> Rtl()
    {
        return PostAsync<object>("/rtl");
    }

    public Task<ApiResponse<object>> Disconnect()
    {
        return PostAsync<object>("/disconnect");
    }

    public Task<ApiResponse<object>> GotoLocal(double x, double y, double z)
    {
        return PostAsync<object>("/position/local", new LocalPositionRequest
        {
            X = x,
            Y = y,
            Z = z,
        });
    }

    public Task<ApiResponse<object>> GotoGlobal(double latitudeDeg, double longitudeDeg, double altitudeMeters)
    {
        return PostAsync<object>("/position/global", new GlobalPositionRequest
        {
            LatitudeDeg = latitudeDeg,
            LongitudeDeg = longitudeDeg,
            AltitudeMeters = altitudeMeters,
        });
    }

    public Task<ApiResponse<object>> Yaw(double yawDegrees, double yawSpeed = 20.0, bool isRelative = false)
    {
        return PostAsync<object>("/yaw", new YawRequest
        {
            YawDegrees = yawDegrees,
            YawSpeedDegPerSec = yawSpeed,
            IsRelative = isRelative,
        });
    }

    public Task<ApiResponse<object>> RawCommand(
        int commandId,
        double param1 = 0,
        double param2 = 0,
        double param3 = 0,
        double param4 = 0,
        double param5 = 0,
        double param6 = 0,
        double param7 = 0)
    {
        return PostAsync<object>("/command/raw", new RawCommandRequest
        {
            CommandId = commandId,
            Param1 = param1,
            Param2 = param2,
            Param3 = param3,
            Param4 = param4,
            Param5 = param5,
            Param6 = param6,
            Param7 = param7,
        });
    }

    public class SensorData
    {
        public DateTime LastUpdate { get; set; } = DateTime.Now;

        [JsonPropertyName("gps_fix")]
        public int GpsFix { get; set; }

        [JsonPropertyName("gps_satellites")]
        public int GpsSatellites { get; set; }

        [JsonPropertyName("latitude")]
        public double Latitude { get; set; }

        [JsonPropertyName("longitude")]
        public double Longitude { get; set; }

        [JsonPropertyName("gps_altitude")]
        public double GpsAltitude { get; set; }

        [JsonPropertyName("ground_speed")]
        public double GroundSpeed { get; set; }

        [JsonPropertyName("cog")]
        public double Cog { get; set; }

        [JsonPropertyName("hdop")]
        public double Hdop { get; set; }

        [JsonPropertyName("relative_alt")]
        public double RelativeAlt { get; set; }

        [JsonPropertyName("absolute_alt")]
        public double AbsoluteAlt { get; set; }

        [JsonPropertyName("pressure")]
        public double Pressure { get; set; }

        [JsonPropertyName("accel_x")]
        public double AccelX { get; set; }

        [JsonPropertyName("accel_y")]
        public double AccelY { get; set; }

        [JsonPropertyName("accel_z")]
        public double AccelZ { get; set; }

        [JsonPropertyName("gyro_x")]
        public double GyroX { get; set; }

        [JsonPropertyName("gyro_y")]
        public double GyroY { get; set; }

        [JsonPropertyName("gyro_z")]
        public double GyroZ { get; set; }

        [JsonPropertyName("mag_x")]
        public int MagX { get; set; }

        [JsonPropertyName("mag_y")]
        public int MagY { get; set; }

        [JsonPropertyName("mag_z")]
        public int MagZ { get; set; }

        [JsonPropertyName("temperature")]
        public double Temperature { get; set; }

        [JsonPropertyName("compass_heading")]
        public double CompassHeading { get; set; }
    }

    public async Task<ApiResponse<SensorData>> GetTelemetry()
    {
        try
        {
            var response = await _httpClient.GetAsync($"{_apiBaseUrl}/telemetry");
            var responseBody = await response.Content.ReadAsStringAsync();

            if (!response.IsSuccessStatusCode)
            {
                return new ApiResponse<SensorData>
                {
                    Success = false,
                    ErrorMessage = $"HTTP {response.StatusCode}",
                    ResponseBody = responseBody
                };
            }

            var data = System.Text.Json.JsonSerializer.Deserialize<SensorData>(responseBody, new System.Text.Json.JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });

            return new ApiResponse<SensorData>
            {
                Success = true,
                Data = data,
                ResponseBody = responseBody
            };
        }
        catch (Exception ex)
        {
            return new ApiResponse<SensorData>
            {
                Success = false,
                ErrorMessage = ex.Message
            };
        }
    }
}
