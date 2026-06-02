using Microsoft.Data.Sqlite;

public sealed class ProcedureStorageService
{
    private readonly string connectionString;

    public ProcedureStorageService(IWebHostEnvironment environment)
    {
        var dataDirectory = Path.Combine(environment.ContentRootPath, "Data");
        Directory.CreateDirectory(dataDirectory);

        var databasePath = Path.Combine(dataDirectory, "droneforge.db");
        connectionString = new SqliteConnectionStringBuilder
        {
            DataSource = databasePath,
        }.ToString();

        EnsureDatabase();
    }

    public async Task<IReadOnlyList<SavedRouteSummary>> GetRoutesAsync()
    {
        await using var connection = new SqliteConnection(connectionString);
        await connection.OpenAsync();

        await using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, name, updated_utc
            FROM saved_routes
            ORDER BY updated_utc DESC, id DESC;
            """;

        var routes = new List<SavedRouteSummary>();
        await using var reader = await command.ExecuteReaderAsync();
        while (await reader.ReadAsync())
        {
            routes.Add(new SavedRouteSummary(
                reader.GetInt32(0),
                reader.GetString(1),
                DateTimeOffset.Parse(reader.GetString(2))));
        }

        return routes;
    }

    public async Task<SavedRouteDetail?> GetRouteAsync(int id)
    {
        await using var connection = new SqliteConnection(connectionString);
        await connection.OpenAsync();

        await using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT id, name, route_json, updated_utc
            FROM saved_routes
            WHERE id = $id;
            """;
        command.Parameters.AddWithValue("$id", id);

        await using var reader = await command.ExecuteReaderAsync();
        if (!await reader.ReadAsync())
        {
            return null;
        }

        return new SavedRouteDetail(
            reader.GetInt32(0),
            reader.GetString(1),
            reader.GetString(2),
            DateTimeOffset.Parse(reader.GetString(3)));
    }

    public async Task<int> SaveRouteAsync(int? id, string name, string routeJson)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");

        await using var connection = new SqliteConnection(connectionString);
        await connection.OpenAsync();

        if (id is not null)
        {
            await using var update = connection.CreateCommand();
            update.CommandText = """
                UPDATE saved_routes
                SET name = $name,
                    route_json = $route_json,
                    updated_utc = $updated_utc
                WHERE id = $id;
                """;
            update.Parameters.AddWithValue("$id", id.Value);
            update.Parameters.AddWithValue("$name", name);
            update.Parameters.AddWithValue("$route_json", routeJson);
            update.Parameters.AddWithValue("$updated_utc", now);

            if (await update.ExecuteNonQueryAsync() > 0)
            {
                return id.Value;
            }
        }

        await using var insert = connection.CreateCommand();
        insert.CommandText = """
            INSERT INTO saved_routes (name, route_json, created_utc, updated_utc)
            VALUES ($name, $route_json, $created_utc, $updated_utc)
            RETURNING id;
            """;
        insert.Parameters.AddWithValue("$name", name);
        insert.Parameters.AddWithValue("$route_json", routeJson);
        insert.Parameters.AddWithValue("$created_utc", now);
        insert.Parameters.AddWithValue("$updated_utc", now);

        return Convert.ToInt32(await insert.ExecuteScalarAsync());
    }

    public async Task AddLogAsync(string category, string message, string? details = null)
    {
        await using var connection = new SqliteConnection(connectionString);
        await connection.OpenAsync();

        await using var command = connection.CreateCommand();
        command.CommandText = """
            INSERT INTO procedure_logs (created_utc, category, message, details)
            VALUES ($created_utc, $category, $message, $details);
            """;
        command.Parameters.AddWithValue("$created_utc", DateTimeOffset.UtcNow.ToString("O"));
        command.Parameters.AddWithValue("$category", category);
        command.Parameters.AddWithValue("$message", message);
        command.Parameters.AddWithValue("$details", (object?)details ?? DBNull.Value);
        await command.ExecuteNonQueryAsync();
    }

    private void EnsureDatabase()
    {
        using var connection = new SqliteConnection(connectionString);
        connection.Open();

        using var command = connection.CreateCommand();
        command.CommandText = """
            CREATE TABLE IF NOT EXISTS saved_routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                route_json TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                updated_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS procedure_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_utc TEXT NOT NULL,
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT NULL
            );
            """;
        command.ExecuteNonQuery();
    }
}

public sealed record SavedRouteSummary(int Id, string Name, DateTimeOffset UpdatedUtc);

public sealed record SavedRouteDetail(int Id, string Name, string RouteJson, DateTimeOffset UpdatedUtc);
