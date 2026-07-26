"""Minimal client for Turso's HTTP (Hrana-over-HTTP) API.

Uses plain `requests` only, no native/compiled dependency, so it works
identically on any CPU architecture (x86_64 Mac, ARM64 Streamlit Cloud,
or an old 32-bit ARMv6 Raspberry Pi Zero W) with no build step at all.

Reference: https://docs.turso.tech/sdk/http/quickstart
"""

import requests


class TursoHTTPError(RuntimeError):
    """Raised when Turso's HTTP API returns an error result."""


def _pipeline_url(database_url: str) -> str:
    # Turso hands out a libsql:// URL; the HTTP pipeline endpoint uses https://
    url = database_url.replace("libsql://", "https://", 1)
    return url.rstrip("/") + "/v2/pipeline"


def _to_arg(value):
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": repr(value)}
    return {"type": "text", "value": str(value)}


def _from_cell(cell):
    if cell is None:
        return None
    if not isinstance(cell, dict):
        return cell
    cell_type = cell.get("type")
    value = cell.get("value")
    if cell_type == "null" or value is None:
        return None
    if cell_type == "integer":
        return int(value)
    if cell_type == "float":
        return float(value)
    return value


def execute(
    database_url: str,
    auth_token: str,
    sql: str,
    params: tuple = (),
    timeout: float = 10.0,
) -> list[dict]:
    """Run one SQL statement against Turso over HTTP.

    Returns rows as a list of {column_name: value} dicts for SELECTs
    (and PRAGMA statements), or an empty list for writes/DDL.
    """
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": [_to_arg(value) for value in params],
                },
            },
            {"type": "close"},
        ]
    }

    response = requests.post(
        _pipeline_url(database_url),
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if not response.ok:
        raise TursoHTTPError(
            f"Turso HTTP {response.status_code} for {sql[:60]!r}: {response.text}"
        )
    data = response.json()

    first_result = data["results"][0]
    if first_result.get("type") == "error":
        raise TursoHTTPError(str(first_result.get("error")))

    execute_result = first_result["response"]["result"]
    columns = [
        column["name"] if isinstance(column, dict) else column
        for column in execute_result.get("cols", [])
    ]

    rows = []
    for raw_row in execute_result.get("rows", []):
        rows.append(
            {column: _from_cell(cell) for column, cell in zip(columns, raw_row)}
        )
    return rows