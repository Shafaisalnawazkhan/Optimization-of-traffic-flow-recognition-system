from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class TrafficDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS traffic_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    vehicle_count INTEGER NOT NULL,
                    density REAL NOT NULL,
                    congestion TEXT NOT NULL,
                    source_type TEXT NOT NULL
                )
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(traffic_results)")}
            for name in ("passed_count", "cars", "motorcycles", "buses", "trucks"):
                if name not in columns:
                    connection.execute(f"ALTER TABLE traffic_results ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
            if "risk_percentage" not in columns:
                connection.execute("ALTER TABLE traffic_results ADD COLUMN risk_percentage REAL NOT NULL DEFAULT 0")

    def add(self, session_id, timestamp, vehicle_count, density, congestion, source_type, passed_count=0, vehicle_types=None, risk_percentage=0):
        vehicle_types = vehicle_types or {}
        with self.lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO traffic_results (session_id,timestamp,vehicle_count,density,congestion,source_type,passed_count,cars,motorcycles,buses,trucks,risk_percentage) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, timestamp, vehicle_count, density, congestion, source_type, passed_count,
                 vehicle_types.get("Car", 0), vehicle_types.get("Motorcycle", 0),
                 vehicle_types.get("Bus", 0), vehicle_types.get("Truck", 0), risk_percentage),
            )

    def recent(self, limit=30):
        with self._connect() as connection:
            latest = connection.execute("SELECT session_id FROM traffic_results ORDER BY id DESC LIMIT 1").fetchone()
            if not latest:
                return []
            rows = connection.execute(
                "SELECT timestamp,vehicle_count,density,congestion,source_type,passed_count,cars,motorcycles,buses,trucks,risk_percentage FROM traffic_results WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (latest["session_id"], limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def all_results(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT timestamp,vehicle_count,density,congestion,source_type,passed_count,cars,motorcycles,buses,trucks,risk_percentage FROM traffic_results ORDER BY id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self):
        with self._connect() as connection:
            latest = connection.execute("SELECT session_id FROM traffic_results ORDER BY id DESC LIMIT 1").fetchone()
            if not latest:
                return {"samples": 0, "average_vehicles": 0, "average_density": 0, "peak_vehicles": 0, "total_passed": 0, "cars": 0, "motorcycles": 0, "buses": 0, "trucks": 0, "average_risk": 0, "peak_risk": 0}
            row = connection.execute("""
                SELECT COUNT(*) samples, COALESCE(ROUND(AVG(vehicle_count),1),0) average_vehicles,
                       COALESCE(ROUND(AVG(density),1),0) average_density, COALESCE(MAX(vehicle_count),0) peak_vehicles,
                       COALESCE(MAX(passed_count),0) total_passed, COALESCE(MAX(cars),0) cars,
                       COALESCE(MAX(motorcycles),0) motorcycles, COALESCE(MAX(buses),0) buses, COALESCE(MAX(trucks),0) trucks,
                       COALESCE(ROUND(AVG(risk_percentage),1),0) average_risk, COALESCE(MAX(risk_percentage),0) peak_risk
                FROM traffic_results WHERE session_id=?
            """, (latest["session_id"],)).fetchone()
        return dict(row)

    def clear(self):
        with self.lock, self._connect() as connection:
            connection.execute("DELETE FROM traffic_results")
