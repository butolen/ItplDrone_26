# DroneForge MongoDB

MongoDB bildet das ER-Diagramm als vier Collections ab:

- `sequences`: gespeicherte Missions-Sequenzen
- `commands`: einzelne Commands mit `sequence_id`
- `routes`: Routen-Metadaten mit optionaler `sequence_id`
- `points`: geordnete Koordinatenpunkte mit `route_id` und optionalem `depends_on_point_id`

## Start

```powershell
cd DroneApi\DB
docker compose up -d
```

Die API nutzt standardmaessig:

```text
MONGODB_URI=mongodb://root:root@localhost:27017/?authSource=admin
MONGODB_DATABASE=droneforge
MONGO_INITDB_ROOT_USERNAME=root
MONGO_INITDB_ROOT_PASSWORD=root
```

## API-Formate

Route anlegen:

```json
{
  "name": "Test route",
  "points": [
    { "latitude": 47.397742, "longitude": 8.545594, "altitude_meters": 5, "order_index": 0 },
    { "latitude": 47.397850, "longitude": 8.545800, "altitude_meters": 7, "order_index": 1 }
  ]
}
```

Guided-Ausfuehrung:

```text
POST /routes/{route_id}/execute-guided
```
