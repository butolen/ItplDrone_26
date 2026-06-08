from __future__ import annotations

import os
import time
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


class DroneForgeRepository:
    def __init__(self) -> None:
        mongodb_uri = os.getenv("MONGODB_URI", "mongodb://root:root@localhost:27017/?authSource=admin")
        database_name = os.getenv("MONGODB_DATABASE", "droneforge")
        self._client: MongoClient = MongoClient(mongodb_uri, serverSelectionTimeoutMS=3000)
        self._db: Database = self._client[database_name]
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return

        self._db.sequences.create_index([("name", ASCENDING)])
        self._db.commands.create_index([("sequence_id", ASCENDING), ("order_index", ASCENDING)])
        self._db.routes.create_index([("name", ASCENDING)])
        self._db.points.create_index([("route_id", ASCENDING), ("order_index", ASCENDING)], unique=True)
        self._db.points.create_index([("depends_on_point_id", ASCENDING)])
        self._schema_ready = True

    @property
    def sequences(self) -> Collection:
        return self._db.sequences

    @property
    def commands(self) -> Collection:
        return self._db.commands

    @property
    def routes(self) -> Collection:
        return self._db.routes

    @property
    def points(self) -> Collection:
        return self._db.points

    def health(self) -> dict[str, Any]:
        self._client.admin.command("ping")
        self.ensure_schema()
        return {
            "success": True,
            "database": self._db.name,
            "collections": sorted(self._db.list_collection_names()),
        }

    def create_sequence(self, name: str, commands: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self.ensure_schema()
        now = self._now()
        sequence_id = self.sequences.insert_one(
            {
                "name": name,
                "created_at": now,
                "updated_at": now,
            }
        ).inserted_id

        for index, command in enumerate(commands or []):
            self.add_command(
                str(sequence_id),
                command=command["command"],
                order_index=command.get("order_index", index),
                parameters=command.get("parameters", {}),
            )

        return self.get_sequence(str(sequence_id))

    def list_sequences(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        return [
            self._serialize_sequence(sequence)
            for sequence in self.sequences.find().sort("created_at", ASCENDING)
        ]

    def get_sequence(self, sequence_id: str) -> dict[str, Any]:
        self.ensure_schema()
        sequence = self.sequences.find_one({"_id": self._object_id(sequence_id)})
        if sequence is None:
            raise KeyError(f"Sequence not found: {sequence_id}")

        result = self._serialize_sequence(sequence)
        result["commands"] = [
            self._serialize_command(command)
            for command in self.commands.find({"sequence_id": sequence_id}).sort("order_index", ASCENDING)
        ]
        return result

    def add_command(
        self,
        sequence_id: str,
        command: str,
        order_index: int,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        self._require_sequence(sequence_id)
        now = self._now()
        command_id = self.commands.insert_one(
            {
                "command": command,
                "sequence_id": sequence_id,
                "order_index": order_index,
                "parameters": parameters or {},
                "created_at": now,
                "updated_at": now,
            }
        ).inserted_id
        self.sequences.update_one({"_id": self._object_id(sequence_id)}, {"$set": {"updated_at": now}})
        return self._serialize_command(self.commands.find_one({"_id": command_id}))

    def create_route(
        self,
        name: str,
        points: list[dict[str, Any]] | None = None,
        sequence_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        if sequence_id:
            self._require_sequence(sequence_id)

        now = self._now()
        route_id = self.routes.insert_one(
            {
                "name": name,
                "sequence_id": sequence_id,
                "created_at": now,
                "updated_at": now,
            }
        ).inserted_id

        for index, point in enumerate(points or []):
            self.add_point(
                str(route_id),
                latitude=point["latitude"],
                longitude=point["longitude"],
                altitude_meters=point.get("altitude_meters", 5.0),
                order_index=point.get("order_index", index),
                depends_on_point_id=point.get("depends_on_point_id"),
            )

        return self.get_route(str(route_id))

    def list_routes(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        return [
            self._serialize_route(route, include_points=False)
            for route in self.routes.find().sort("created_at", ASCENDING)
        ]

    def get_route(self, route_id: str) -> dict[str, Any]:
        self.ensure_schema()
        route = self.routes.find_one({"_id": self._object_id(route_id)})
        if route is None:
            raise KeyError(f"Route not found: {route_id}")

        return self._serialize_route(route, include_points=True)

    def add_point(
        self,
        route_id: str,
        latitude: float,
        longitude: float,
        altitude_meters: float,
        order_index: int,
        depends_on_point_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        self._require_route(route_id)
        if depends_on_point_id:
            self._require_point(depends_on_point_id)

        now = self._now()
        point_id = self.points.insert_one(
            {
                "route_id": route_id,
                "latitude": latitude,
                "longitude": longitude,
                "altitude_meters": altitude_meters,
                "order_index": order_index,
                "depends_on_point_id": depends_on_point_id,
                "created_at": now,
                "updated_at": now,
            }
        ).inserted_id
        self.routes.update_one({"_id": self._object_id(route_id)}, {"$set": {"updated_at": now}})
        return self._serialize_point(self.points.find_one({"_id": point_id}))

    def get_route_points(self, route_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        self._require_route(route_id)
        return [
            self._serialize_point(point)
            for point in self.points.find({"route_id": route_id}).sort("order_index", ASCENDING)
        ]

    def _serialize_route(self, route: dict[str, Any], include_points: bool) -> dict[str, Any]:
        result = {
            "route_id": str(route["_id"]),
            "name": route["name"],
            "sequence_id": route.get("sequence_id"),
            "created_at": route["created_at"],
            "updated_at": route["updated_at"],
        }
        if include_points:
            result["points"] = self.get_route_points(str(route["_id"]))
        return result

    @staticmethod
    def _serialize_sequence(sequence: dict[str, Any]) -> dict[str, Any]:
        return {
            "sequence_id": str(sequence["_id"]),
            "name": sequence["name"],
            "created_at": sequence["created_at"],
            "updated_at": sequence["updated_at"],
        }

    @staticmethod
    def _serialize_command(command: dict[str, Any] | None) -> dict[str, Any]:
        if command is None:
            raise KeyError("Command not found")

        return {
            "command_id": str(command["_id"]),
            "command": command["command"],
            "sequence_id": command["sequence_id"],
            "order_index": command["order_index"],
            "parameters": command.get("parameters", {}),
            "created_at": command["created_at"],
            "updated_at": command["updated_at"],
        }

    @staticmethod
    def _serialize_point(point: dict[str, Any] | None) -> dict[str, Any]:
        if point is None:
            raise KeyError("Point not found")

        return {
            "point_id": str(point["_id"]),
            "route_id": point["route_id"],
            "latitude": point["latitude"],
            "longitude": point["longitude"],
            "altitude_meters": point["altitude_meters"],
            "order_index": point["order_index"],
            "depends_on_point_id": point.get("depends_on_point_id"),
            "created_at": point["created_at"],
            "updated_at": point["updated_at"],
        }

    def _require_sequence(self, sequence_id: str) -> None:
        if self.sequences.count_documents({"_id": self._object_id(sequence_id)}, limit=1) == 0:
            raise KeyError(f"Sequence not found: {sequence_id}")

    def _require_route(self, route_id: str) -> None:
        if self.routes.count_documents({"_id": self._object_id(route_id)}, limit=1) == 0:
            raise KeyError(f"Route not found: {route_id}")

    def _require_point(self, point_id: str) -> None:
        if self.points.count_documents({"_id": self._object_id(point_id)}, limit=1) == 0:
            raise KeyError(f"Point not found: {point_id}")

    @staticmethod
    def _object_id(value: str) -> ObjectId:
        if not ObjectId.is_valid(value):
            raise KeyError(f"Invalid MongoDB id: {value}")
        return ObjectId(value)

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
