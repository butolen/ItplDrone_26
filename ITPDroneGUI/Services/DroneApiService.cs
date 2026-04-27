using System.Net.Http.Json;
using System.Text.Json.Serialization;

public class DroneApiService
{
    private readonly HttpClient _httpClient;
    private readonly string _apiBaseUrl;

    public DroneApiService(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient;
        _apiBaseUrl = configuration["DroneApi:BaseUrl"] ?? "http://192.168.240.1:8000";
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

    public class LocalPositionRequest
    {
        [JsonPropertyName("x")]
        public double X { get; set; }

        [JsonPropertyName("y")]
        public double Y { get; set; }

        [JsonPropertyName("z")]
        public double Z { get; set; }
    }

    public class YawRequest
    {
        [JsonPropertyName("yaw_degrees")]
        public double YawDegrees { get; set; }

        [JsonPropertyName("yaw_speed_deg_per_sec")]
        public double YawSpeedDegPerSec { get; set; } = 20.0;

        [JsonPropertyName("is_relative")]
        public bool IsRelative { get; set; } = false;
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

    public async Task<T?> GetAsync<T>(string endpoint)
    {
        var response = await _httpClient.GetAsync($"{_apiBaseUrl}{endpoint}");
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<T>();
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
                    ResponseBody = responseBody
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
                ResponseBody = responseBody
            };
        }
        catch (Exception ex)
        {
            return new ApiResponse<T>
            {
                Success = false,
                ErrorMessage = ex.Message
            };
        }
    }

    public Task<ApiResponse<object>> Connect()
    {
        return PostAsync<object>("/connect", new ConnectRequest
        {
            ConnectionString = "udpin:0.0.0.0:14551",
            BaudRate = 57600,
            HeartbeatTimeoutSeconds = 10.0
        });
    }

    public Task<ApiResponse<object>> SetGuidedMode()
    {
        return PostAsync<object>("/mode", new ModeRequest
        {
            Mode = "GUIDED"
        });
    }

    public Task<ApiResponse<object>> SetMode(string mode)
    {
        return PostAsync<object>("/mode", new ModeRequest
        {
            Mode = mode
        });
    }

    public Task<ApiResponse<object>> Arm()
    {
        return PostAsync<object>("/arm");
    }

    public Task<ApiResponse<object>> Disarm()
    {
        return PostAsync<object>("/disarm");
    }

    public Task<ApiResponse<object>> Takeoff(double altitudeMeters = 5.0)
    {
        return PostAsync<object>("/takeoff", new TakeoffRequest
        {
            AltitudeMeters = altitudeMeters
        });
    }

    public Task<ApiResponse<object>> SendVelocity(double vx, double vy, double vz, double durationSeconds)
    {
        return PostAsync<object>("/velocity/body", new VelocityBodyRequest
        {
            Vx = vx,
            Vy = vy,
            Vz = vz,
            DurationSeconds = durationSeconds
        });
    }

    public Task<ApiResponse<object>> MoveForward()
    {
        return SendVelocity(2, 0, 0, 2);
    }

    public Task<ApiResponse<object>> MoveBack()
    {
        return SendVelocity(-2, 0, 0, 2);
    }

    public Task<ApiResponse<object>> MoveLeft()
    {
        return SendVelocity(0, -2, 0, 2);
    }

    public Task<ApiResponse<object>> MoveRight()
    {
        return SendVelocity(0, 2, 0, 2);
    }

    public Task<ApiResponse<object>> MoveUp()
    {
        return SendVelocity(0, 0, -1, 2);
    }

    public Task<ApiResponse<object>> MoveDown()
    {
        return SendVelocity(0, 0, 1, 2);
    }

    public Task<ApiResponse<object>> Stop()
    {
        return SendVelocity(0, 0, 0, 1);
    }

    public Task<ApiResponse<object>> GoToLocalPosition(double x, double y, double z)
    {
        return PostAsync<object>("/position/local", new LocalPositionRequest
        {
            X = x,
            Y = y,
            Z = z
        });
    }

    public Task<ApiResponse<object>> Yaw(double yawDegrees, double yawSpeed = 20.0, bool isRelative = false)
    {
        return PostAsync<object>("/yaw", new YawRequest
        {
            YawDegrees = yawDegrees,
            YawSpeedDegPerSec = yawSpeed,
            IsRelative = isRelative
        });
    }

    public Task<ApiResponse<object>> Land()
    {
        return PostAsync<object>("/land");
    }

    public Task<ApiResponse<object>> ReturnToLaunch()
    {
        return PostAsync<object>("/rtl");
    }

    public Task<ApiResponse<object>> Disconnect()
    {
        return PostAsync<object>("/disconnect");
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
            Param7 = param7
        });
    }
}