import asyncio
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

import turso_http
from dotenv import load_dotenv
from pylxpweb import LuxpowerClient
from pylxpweb.devices.station import Station


load_dotenv()

POLL_SECONDS = 30
TESLA_HOST = os.getenv("TESLA_WALL_CONNECTOR_HOST", "192.168.1.121")

TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")


def turso(sql: str, params: tuple = ()) -> list[dict]:
    return turso_http.execute(TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, sql, params)


def number(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def ensure_column(table: str, name: str, sql_type: str) -> None:
    existing = {row["name"] for row in turso(f"PRAGMA table_info({table})")}
    if name not in existing:
        turso(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def initialise_database() -> None:
    turso(
        """
        CREATE TABLE IF NOT EXISTS inverter_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            station_name TEXT NOT NULL,
            inverter_serial TEXT NOT NULL,
            inverter_model TEXT
        )
        """
    )

    inverter_columns = {
        "pv1_power_w": "REAL",
        "pv2_power_w": "REAL",
        "pv_total_power_w": "REAL",
        "pv1_voltage_v": "REAL",
        "pv2_voltage_v": "REAL",
        "pv1_current_a": "REAL",
        "pv2_current_a": "REAL",
        "battery_soc_percent": "REAL",
        "battery_voltage_v": "REAL",
        "battery_charge_power_w": "REAL",
        "battery_discharge_power_w": "REAL",
        "output_power_w": "REAL",
        "output_power_l1_w": "REAL",
        "output_power_l2_w": "REAL",
        "output_voltage_v": "REAL",
        "output_frequency_hz": "REAL",
        "utility_power_w": "REAL",
        "utility_voltage_v": "REAL",
        "utility_frequency_hz": "REAL",
        "inverter_temp_c": "REAL",
        "radiator1_temp_c": "REAL",
        "radiator2_temp_c": "REAL",
        "battery_temp_c": "REAL",
        "yield_today_kwh": "REAL",
        "charge_today_kwh": "REAL",
        "discharge_today_kwh": "REAL",
        "usage_today_kwh": "REAL",
        "yield_lifetime_kwh": "REAL",
        "charge_lifetime_kwh": "REAL",
        "discharge_lifetime_kwh": "REAL",
        "usage_lifetime_kwh": "REAL",
    }

    for name, sql_type in inverter_columns.items():
        ensure_column("inverter_readings", name, sql_type)

    turso(
        """
        CREATE TABLE IF NOT EXISTS tesla_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            contactor_closed INTEGER NOT NULL,
            vehicle_connected INTEGER NOT NULL,
            charging_current_a REAL,
            grid_voltage_v REAL,
            grid_frequency_hz REAL,
            charging_power_w REAL,
            session_seconds REAL,
            session_energy_wh REAL,
            pcba_temp_c REAL,
            handle_temp_c REAL,
            mcu_temp_c REAL,
            evse_state INTEGER,
            alerts_json TEXT,
            lifetime_energy_wh REAL,
            charging_time_s REAL,
            charge_starts REAL
        )
        """
    )

    turso(
        """
        CREATE INDEX IF NOT EXISTS idx_inverter_time_serial
        ON inverter_readings(recorded_at, inverter_serial)
        """
    )

    turso(
        """
        CREATE INDEX IF NOT EXISTS idx_tesla_time
        ON tesla_readings(recorded_at)
        """
    )


def save_inverter_reading(
    station_name: str,
    inverter: Any,
    recorded_at: str,
) -> None:
    turso(
        """
        INSERT INTO inverter_readings (
            recorded_at,
            station_name,
            inverter_serial,
            inverter_model,
            pv1_power_w,
            pv2_power_w,
            pv_total_power_w,
            pv1_voltage_v,
            pv2_voltage_v,
            pv1_current_a,
            pv2_current_a,
            battery_soc_percent,
            battery_voltage_v,
            battery_charge_power_w,
            battery_discharge_power_w,
            output_power_w,
            output_power_l1_w,
            output_power_l2_w,
            output_voltage_v,
            output_frequency_hz,
            utility_power_w,
            utility_voltage_v,
            utility_frequency_hz,
            inverter_temp_c,
            radiator1_temp_c,
            radiator2_temp_c,
            battery_temp_c,
            yield_today_kwh,
            charge_today_kwh,
            discharge_today_kwh,
            usage_today_kwh,
            yield_lifetime_kwh,
            charge_lifetime_kwh,
            discharge_lifetime_kwh,
            usage_lifetime_kwh
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recorded_at,
            station_name,
            str(getattr(inverter, "serial_number", "unknown")),
            str(getattr(inverter, "model", "unknown")),
            number(getattr(inverter, "pv1_power", 0)),
            number(getattr(inverter, "pv2_power", 0)),
            number(getattr(inverter, "pv_total_power", 0)),
            number(getattr(inverter, "pv1_voltage", 0)),
            number(getattr(inverter, "pv2_voltage", 0)),
            number(getattr(inverter, "pv1_current", 0)),
            number(getattr(inverter, "pv2_current", 0)),
            number(getattr(inverter, "battery_soc", 0)),
            number(getattr(inverter, "battery_voltage", 0)),
            number(getattr(inverter, "battery_charge_power", 0)),
            number(getattr(inverter, "battery_discharge_power", 0)),
            number(getattr(inverter, "eps_power", 0)),
            number(getattr(inverter, "eps_power_l1", 0)),
            number(getattr(inverter, "eps_power_l2", 0)),
            number(getattr(inverter, "eps_voltage_r", 0)),
            number(getattr(inverter, "eps_frequency", 0)),
            number(getattr(inverter, "generator_power", 0)),
            number(getattr(inverter, "generator_voltage", 0)),
            number(getattr(inverter, "generator_frequency", 0)),
            number(getattr(inverter, "inverter_temperature", 0)),
            number(getattr(inverter, "radiator1_temperature", 0)),
            number(getattr(inverter, "radiator2_temperature", 0)),
            number(getattr(inverter, "battery_temperature", 0)),
            number(getattr(inverter, "total_energy_today", 0)),
            number(getattr(inverter, "energy_today_charging", 0)),
            number(getattr(inverter, "energy_today_discharging", 0)),
            number(getattr(inverter, "energy_today_usage", 0)),
            number(getattr(inverter, "total_energy_lifetime", 0)),
            number(getattr(inverter, "energy_lifetime_charging", 0)),
            number(getattr(inverter, "energy_lifetime_discharging", 0)),
            number(getattr(inverter, "energy_lifetime_usage", 0)),
        ),
    )


def fetch_json(url: str, timeout: float = 4.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "eg4-energy-dashboard/2.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_tesla(recorded_at: str) -> None:
    try:
        vitals = fetch_json(f"http://{TESLA_HOST}/api/1/vitals")
        lifetime = fetch_json(f"http://{TESLA_HOST}/api/1/lifetime")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Tesla collection error: {type(exc).__name__}: {exc}")
        return

    current_a = number(vitals.get("vehicle_current_a"))
    grid_v = number(vitals.get("grid_v"))
    charging_power_w = current_a * grid_v

    turso(
        """
        INSERT INTO tesla_readings (
            recorded_at,
            contactor_closed,
            vehicle_connected,
            charging_current_a,
            grid_voltage_v,
            grid_frequency_hz,
            charging_power_w,
            session_seconds,
            session_energy_wh,
            pcba_temp_c,
            handle_temp_c,
            mcu_temp_c,
            evse_state,
            alerts_json,
            lifetime_energy_wh,
            charging_time_s,
            charge_starts
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recorded_at,
            int(bool(vitals.get("contactor_closed"))),
            int(bool(vitals.get("vehicle_connected"))),
            current_a,
            grid_v,
            number(vitals.get("grid_hz")),
            charging_power_w,
            number(vitals.get("session_s")),
            number(vitals.get("session_energy_wh")),
            number(vitals.get("pcba_temp_c")),
            number(vitals.get("handle_temp_c")),
            number(vitals.get("mcu_temp_c")),
            int(number(vitals.get("evse_state"))),
            json.dumps(vitals.get("current_alerts", [])),
            number(lifetime.get("energy_wh")),
            number(lifetime.get("charging_time_s")),
            number(lifetime.get("charge_starts")),
        ),
    )

    status = "charging" if vitals.get("contactor_closed") and current_a > 0.2 else (
        "connected" if vitals.get("vehicle_connected") else "idle"
    )
    print(
        f"{recorded_at} | Tesla {status} | "
        f"{current_a:.1f} A | {grid_v:.1f} V | {charging_power_w:.0f} W"
    )


async def collect_eg4(client: LuxpowerClient, recorded_at: str) -> None:
    stations = await Station.load_all(client)

    for station in stations:
        station_name = getattr(station, "name", None) or "Unnamed station"

        for inverter in station.all_inverters:
            await inverter.refresh()
            save_inverter_reading(station_name, inverter, recorded_at)

            print(
                f"{recorded_at} | "
                f"Inverter {inverter.serial_number} | "
                f"Solar in {number(getattr(inverter, 'pv_total_power', 0)):.0f} W | "
                f"Power out {number(getattr(inverter, 'eps_power', 0)):.0f} W | "
                f"Battery {number(getattr(inverter, 'battery_soc', 0)):.0f}%"
            )


async def main() -> None:
    if not TURSO_DATABASE_URL or not TURSO_AUTH_TOKEN:
        raise RuntimeError("Missing TURSO_DATABASE_URL or TURSO_AUTH_TOKEN in .env")

    initialise_database()

    username = os.getenv("EG4_USERNAME")
    password = os.getenv("EG4_PASSWORD")
    base_url = os.getenv(
        "EG4_BASE_URL",
        "https://monitor.eg4electronics.com",
    )

    if not username or not password:
        raise RuntimeError("Missing EG4_USERNAME or EG4_PASSWORD in .env")

    async with LuxpowerClient(
        username=username,
        password=password,
        base_url=base_url,
    ) as client:
        while True:
            recorded_at = datetime.now(timezone.utc).isoformat()

            try:
                await collect_eg4(client, recorded_at)
            except Exception as exc:
                print(f"EG4 collection error: {type(exc).__name__}: {exc}")

            try:
                collect_tesla(recorded_at)
            except Exception as exc:
                print(f"Tesla collection error: {type(exc).__name__}: {exc}")
            await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCollector stopped.")