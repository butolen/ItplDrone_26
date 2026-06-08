db = db.getSiblingDB("droneforge");

db.createCollection("sequences", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "created_at", "updated_at"],
      properties: {
        name: { bsonType: "string" },
        created_at: { bsonType: "string" },
        updated_at: { bsonType: "string" }
      }
    }
  }
});

db.createCollection("commands", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["command", "sequence_id", "order_index", "created_at", "updated_at"],
      properties: {
        command: { bsonType: "string" },
        sequence_id: { bsonType: "string" },
        order_index: { bsonType: "int" },
        parameters: { bsonType: "object" },
        created_at: { bsonType: "string" },
        updated_at: { bsonType: "string" }
      }
    }
  }
});

db.createCollection("routes", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "created_at", "updated_at"],
      properties: {
        name: { bsonType: "string" },
        sequence_id: { bsonType: ["string", "null"] },
        created_at: { bsonType: "string" },
        updated_at: { bsonType: "string" }
      }
    }
  }
});

db.createCollection("points", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["route_id", "latitude", "longitude", "altitude_meters", "order_index", "created_at", "updated_at"],
      properties: {
        route_id: { bsonType: "string" },
        latitude: { bsonType: ["double", "int"] },
        longitude: { bsonType: ["double", "int"] },
        altitude_meters: { bsonType: ["double", "int"] },
        order_index: { bsonType: "int" },
        depends_on_point_id: { bsonType: ["string", "null"] },
        created_at: { bsonType: "string" },
        updated_at: { bsonType: "string" }
      }
    }
  }
});

db.sequences.createIndex({ name: 1 });
db.commands.createIndex({ sequence_id: 1, order_index: 1 });
db.routes.createIndex({ name: 1 });
db.points.createIndex({ route_id: 1, order_index: 1 }, { unique: true });
db.points.createIndex({ depends_on_point_id: 1 });
