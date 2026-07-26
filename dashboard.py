import json
import math
import os
import textwrap

import libsql
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def _secret_or_env(name: str) -> str:
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, "")


TURSO_DATABASE_URL = _secret_or_env("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = _secret_or_env("TURSO_AUTH_TOKEN")

SYSTEM_CAPACITY_W = 12_000
RESERVE_MARGIN_W = 1_500
TESLA_CONFIGURED_MAX_A = 43

LOCAL_TIMEZONE = "America/New_York"

# Rough, informal visual thresholds - not manufacturer specs. Tune these if
# you know the real limits for your inverter/battery.
TEMP_WARN_C = 45
TEMP_HOT_C = 60

# Battery colour tiers, per your spec.
BATTERY_GREEN_AT = 70
BATTERY_RED_AT = 30

# Very rough US-grid-average estimate for the "CO2 avoided" stat - not a
# precise figure, just a fun order-of-magnitude number.
CO2_KG_PER_KWH = 0.38

COLOUR_SOLAR = "#ffd84f"
COLOUR_BATTERY_GREEN = "#69ef79"
COLOUR_BATTERY_YELLOW = "#ffd84f"
COLOUR_BATTERY_RED = "#ff6b6b"
COLOUR_HOME = "#4ca9ff"
COLOUR_TESLA = "#ff6b6b"
COLOUR_TESLA_ON = "#69ef79"
COLOUR_SYSTEM = "#f5f7fb"
COLOUR_IDLE = "#3a4a5c"
COLOUR_CYAN = "#54e5ef"
COLOUR_PURPLE = "#ba74ff"


st.set_page_config(
    page_title="Home Energy Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# Only page-chrome CSS lives in st.markdown, and it never contains a <div>,
# so there's no risk of Streamlit's Markdown parser treating any of it as
# an indented code block. Everything with real HTML structure below is
# rendered through a single st.iframe call instead, which sidesteps that
# whole class of bug (see build_dashboard_html).
st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(
                circle at 50% -15%,
                rgba(39, 103, 164, 0.22),
                transparent 35%
            ),
            #050d16;
        color: #f5f7fb;
    }

    header[data-testid="stHeader"] {
        background: transparent;
    }

    .block-container {
        max-width: 1550px;
        padding-top: 1.1rem;
        padding-bottom: 3rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _rows_to_frame(cursor, parse_dates: list[str] | None = None) -> pd.DataFrame:
    columns = [description[0] for description in cursor.description]
    frame = pd.DataFrame(cursor.fetchall(), columns=columns)
    for column in parse_dates or []:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column])
    return frame


@st.cache_data(ttl=8)
def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not TURSO_DATABASE_URL or not TURSO_AUTH_TOKEN:
        return pd.DataFrame(), pd.DataFrame()

    connection = libsql.connect(
        database=TURSO_DATABASE_URL,
        auth_token=TURSO_AUTH_TOKEN,
    )
    try:
        cursor = connection.execute(
            "SELECT * FROM inverter_readings ORDER BY recorded_at"
        )
        inverter_data = _rows_to_frame(cursor, parse_dates=["recorded_at"])

        try:
            cursor = connection.execute(
                "SELECT * FROM tesla_readings ORDER BY recorded_at"
            )
            tesla_data = _rows_to_frame(cursor, parse_dates=["recorded_at"])
        except Exception:
            tesla_data = pd.DataFrame()
    finally:
        connection.close()

    return inverter_data, tesla_data


def number(value) -> float:
    try:
        numeric_value = float(value)
        if math.isnan(numeric_value):
            return 0.0
        return numeric_value
    except (TypeError, ValueError):
        return 0.0


def has_column(frame: pd.DataFrame, name: str) -> bool:
    return name in frame.columns


def column_or_zero(frame: pd.DataFrame, name: str) -> pd.Series:
    if name in frame.columns:
        return frame[name]
    return pd.Series([0.0] * len(frame))


def watts(value: float) -> str:
    value = number(value)
    if abs(value) >= 1000:
        return f"{value / 1000:.2f} kW"
    return f"{value:,.0f} W"


def kwh(value: float) -> str:
    return f"{number(value):,.1f} kWh"


def kwh_from_wh(value: float) -> str:
    return f"{number(value) / 1000:,.2f} kWh"


def battery_tier_colour(soc: float) -> str:
    if soc > BATTERY_GREEN_AT:
        return COLOUR_BATTERY_GREEN
    if soc <= BATTERY_RED_AT:
        return COLOUR_BATTERY_RED
    return COLOUR_BATTERY_YELLOW


def temp_colour(value: float) -> str:
    if value >= TEMP_HOT_C:
        return COLOUR_TESLA
    if value >= TEMP_WARN_C:
        return COLOUR_SOLAR
    return COLOUR_BATTERY_GREEN


# ---------------------------------------------------------------------------
# Icon library - flat, simple shapes sized to read clearly at the ~40px
# card scale they're actually displayed at.
# ---------------------------------------------------------------------------

def icon_solar(active: bool) -> str:
    colour = COLOUR_SOLAR if active else COLOUR_IDLE
    return f"""
    <svg viewBox="0 0 64 64" class="node-icon">
        <g stroke="{colour}" stroke-width="3" stroke-linecap="round" fill="none" opacity="{'1' if active else '.5'}">
            <circle cx="32" cy="24" r="9" fill="{colour}" stroke="none"/>
            <line x1="32" y1="4" x2="32" y2="10"/>
            <line x1="14" y1="12" x2="18.5" y2="16.5"/>
            <line x1="50" y1="12" x2="45.5" y2="16.5"/>
            <line x1="8" y1="24" x2="14" y2="24"/>
            <line x1="56" y1="24" x2="50" y2="24"/>
        </g>
        <g transform="translate(10,38)">
            <rect x="0" y="0" width="44" height="20" rx="2" fill="#111a24" stroke="{colour}" stroke-width="2"/>
            <line x1="11" y1="0" x2="11" y2="20" stroke="{colour}" stroke-width="1.5" opacity=".7"/>
            <line x1="22" y1="0" x2="22" y2="20" stroke="{colour}" stroke-width="1.5" opacity=".7"/>
            <line x1="33" y1="0" x2="33" y2="20" stroke="{colour}" stroke-width="1.5" opacity=".7"/>
            <line x1="0" y1="10" x2="44" y2="10" stroke="{colour}" stroke-width="1.5" opacity=".7"/>
        </g>
    </svg>
    """


def icon_battery(soc_percent: float) -> str:
    colour = battery_tier_colour(soc_percent)
    fraction = max(0.0, min(1.0, soc_percent / 100.0))
    fill_width = round(40 * fraction)
    return f"""
    <svg viewBox="0 0 64 64" class="node-icon">
        <rect x="6" y="20" width="48" height="26" rx="4" fill="none" stroke="{colour}" stroke-width="3"/>
        <rect x="56" y="27" width="5" height="12" rx="1.5" fill="{colour}"/>
        <rect x="10" y="24" width="{fill_width}" height="18" rx="2" fill="{colour}" opacity=".85"/>
    </svg>
    """


def icon_home(active: bool) -> str:
    colour = COLOUR_HOME if active else COLOUR_IDLE
    return f"""
    <svg viewBox="0 0 64 64" class="node-icon">
        <g fill="none" stroke="{colour}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10 30 L32 10 L54 30"/>
            <path d="M16 26 L16 54 L48 54 L48 26"/>
            <rect x="27" y="38" width="10" height="16" fill="{colour}" stroke="none" opacity=".85"/>
        </g>
    </svg>
    """


def icon_inverter() -> str:
    return f"""
    <svg viewBox="0 0 64 64" class="node-icon">
        <rect x="12" y="6" width="40" height="52" rx="6" fill="none" stroke="{COLOUR_SYSTEM}" stroke-width="3"/>
        <path d="M20 38 L28 30 L34 36 L44 22" fill="none" stroke="{COLOUR_TESLA_ON}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="20" cy="47" r="2.6" fill="{COLOUR_SYSTEM}"/>
        <circle cx="28" cy="47" r="2.6" fill="{COLOUR_SYSTEM}"/>
        <circle cx="36" cy="47" r="2.6" fill="{COLOUR_SYSTEM}"/>
    </svg>
    """


def icon_tesla_connector(charging: bool, connected: bool) -> str:
    """A simplified, clean Gen-3 Wall Connector glyph: body + coiled
    cable + handle, legible at small size, with an LED colour that
    reflects live state."""
    if charging:
        led = COLOUR_TESLA_ON
    elif connected:
        led = COLOUR_CYAN
    else:
        led = "#5b6673"

    return f"""
    <svg viewBox="0 0 64 80" class="node-icon tesla-icon">
        <path d="M20 18 C8 24 5 38 7 50 C9 62 18 72 30 75" fill="none"
              stroke="#1b2027" stroke-width="6" stroke-linecap="round"/>
        <rect x="18" y="6" width="28" height="46" rx="7"
              fill="#eef0f2" stroke="#ffffff" stroke-width="1.5"/>
        <rect x="24" y="14" width="16" height="20" rx="3" fill="#0c0f12"/>
        <rect x="30.5" y="16" width="3" height="16" rx="1.5" fill="{led}"/>
        <path d="M27 40 C31 37 33 37 37 40 C35.4 41.6 33.6 42.4 32 42.6 L32 45.5 L30 45.5 L30 42.6 C28.4 42.4 28.6 41.6 27 40 Z"
              fill="#9aa2a9"/>
        <path d="M46 46 C54 49 58 55 59 62" fill="none" stroke="#1b2027" stroke-width="5" stroke-linecap="round"/>
        <g transform="translate(52 62) rotate(18)">
            <rect x="0" y="0" width="12" height="16" rx="3" fill="#20262c" stroke="#6c757c" stroke-width="1.4"/>
            <rect x="2.5" y="2.5" width="7" height="4.5" rx="1.5" fill="#0c0f12"/>
        </g>
    </svg>
    """


def icon_leaf() -> str:
    return f"""
    <svg viewBox="0 0 64 64" class="node-icon">
        <path d="M14 50 C10 30 22 12 50 10 C50 38 34 50 14 50 Z"
              fill="none" stroke="{COLOUR_BATTERY_GREEN}" stroke-width="3" stroke-linejoin="round"/>
        <path d="M16 48 C28 34 38 24 48 14" fill="none" stroke="{COLOUR_BATTERY_GREEN}" stroke-width="2.4" stroke-linecap="round"/>
    </svg>
    """


def icon_thermometer(colour: str) -> str:
    return f"""
    <svg viewBox="0 0 32 64" class="temp-icon">
        <rect x="12" y="6" width="8" height="34" rx="4" fill="none" stroke="{colour}" stroke-width="2.5"/>
        <circle cx="16" cy="46" r="9" fill="{colour}" opacity=".2" stroke="{colour}" stroke-width="2.5"/>
        <circle cx="16" cy="46" r="4" fill="{colour}"/>
        <rect x="14" y="14" width="4" height="26" rx="2" fill="{colour}"/>
    </svg>
    """


def dedent_html(value: str) -> str:
    """Used only for content going into st.iframe (a real <iframe>, not
    Streamlit's Markdown renderer), so indentation here is purely cosmetic
    for reading the source - it has no effect on how the browser renders
    the page."""
    return textwrap.dedent(value).strip()


def build_dashboard_html(context: dict) -> str:
    nodes = context["nodes"]
    edges = context["edges"]
    strings = context["strings"]
    temps = context["temps"]

    node_html = []
    for node in nodes:
        state_class = "node-active" if node["active"] else "node-idle"
        node_html.append(
            f"""
            <div class="flow-node {state_class}" style="left:{node['x']}%; top:{node['y']}%;">
                <div class="node-icon-wrap" style="--accent:{node['colour']}">{node['icon']}</div>
                <div class="node-label">{node['label']}</div>
                <div class="node-value" style="color:{node['colour'] if node['active'] else '#7d8ba0'}">{node['value']}</div>
                <div class="node-sub">{node['sub']}</div>
            </div>
            """
        )

    edge_svgs = []
    dot_svgs = []
    for edge in edges:
        path_id = edge["id"]
        edge_svgs.append(
            f"""
            <path id="{path_id}" d="{edge['d']}" fill="none"
                  stroke="{edge['colour'] if edge['active'] else '#1d2733'}"
                  stroke-width="{'0.55' if edge['active'] else '0.35'}"
                  stroke-linecap="round" opacity="{'0.55' if edge['active'] else '0.6'}"/>
            """
        )
        if edge["active"]:
            for i in range(3):
                delay = i * (edge["duration"] / 3)
                dot_svgs.append(
                    f"""
                    <circle r="0.9" fill="{edge['colour']}">
                        <animateMotion dur="{edge['duration']}s" begin="-{delay}s"
                                        repeatCount="indefinite" rotate="auto">
                            <mpath href="#{path_id}"/>
                        </animateMotion>
                    </circle>
                    """
                )

    string_rows = []
    for s in strings:
        pct = max(0.0, min(100.0, s["share"]))
        string_rows.append(
            f"""
            <div class="string-row">
                <div class="string-label">{s['label']}</div>
                <div class="string-bar-track">
                    <div class="string-bar-fill" style="width:{pct}%; background:{COLOUR_SOLAR};"></div>
                </div>
                <div class="string-stats">
                    <span>{watts(s['power'])}</span>
                    <span>{s['voltage']:.1f} V</span>
                    <span>{s['current']:.1f} A</span>
                </div>
            </div>
            """
        )

    temp_chips = []
    for t in temps:
        colour = temp_colour(t["value"])
        temp_chips.append(
            f"""
            <div class="temp-chip">
                <div class="temp-icon-wrap" style="color:{colour}">{icon_thermometer(colour)}</div>
                <div class="temp-label">{t['label']}</div>
                <div class="temp-value" style="color:{colour}">{t['value']:.0f}°C</div>
            </div>
            """
        )

    html = f"""
    <!doctype html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
    * {{ box-sizing: border-box; }}

    body {{
        margin: 0;
        overflow: hidden;
        background: transparent;
        color: #f5f7fb;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    .dashboard {{
        display: flex;
        flex-direction: column;
        gap: 14px;
        padding-bottom: 6px;
    }}

    .top-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}

    .brand-title {{ font-size: 30px; font-weight: 900; }}
    .brand-sub {{ font-size: 14px; color: {COLOUR_BATTERY_GREEN}; margin-top: 2px; }}

    .status-pill {{
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        background: rgba(53, 204, 88, 0.12);
        border: 1px solid rgba(53, 204, 88, 0.32);
        border-radius: 999px;
        font-size: 13px;
    }}

    .dot {{
        width: 8px; height: 8px;
        background: {COLOUR_BATTERY_GREEN};
        border-radius: 50%;
        box-shadow: 0 0 10px {COLOUR_BATTERY_GREEN};
    }}

    .updated-note {{ color: #9eb0c4; font-size: 13px; margin-top: 6px; text-align: right; }}

    .metric-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px;
    }}

    .card {{
        padding: 16px 17px;
        background: linear-gradient(180deg, rgba(17, 31, 47, 0.98), rgba(9, 21, 34, 0.98));
        border: 1px solid #26384e;
        border-radius: 16px;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.025);
    }}

    .metric-label {{
        margin-bottom: 8px; font-size: 12px; font-weight: 800;
        letter-spacing: 0.5px; text-transform: uppercase; color: #9eb0c4;
    }}

    .metric-value {{ margin-bottom: 6px; font-size: 27px; font-weight: 900; line-height: 1; }}
    .metric-note {{ color: #9eb0c4; font-size: 12.5px; line-height: 1.35; }}

    .main-row {{
        display: grid;
        grid-template-columns: 3.1fr 1fr;
        gap: 14px;
        align-items: start;
    }}

    .flow-canvas {{
        position: relative;
        height: 600px;
        background:
            radial-gradient(circle at 50% 48%, rgba(49, 120, 181, 0.16), transparent 42%),
            linear-gradient(180deg, #091624, #050d16);
        border: 1px solid #26384e;
        border-radius: 18px;
        overflow: hidden;
    }}

    .flow-title {{
        position: absolute; top: 16px; left: 20px; z-index: 5;
        font-size: 13px; font-weight: 850; letter-spacing: 0.6px; color: {COLOUR_BATTERY_GREEN};
    }}

    .flow-svg {{ position: absolute; inset: 0; width: 100%; height: 100%; z-index: 1; }}

    .flow-node {{
        position: absolute;
        transform: translate(-50%, -50%);
        width: 168px;
        z-index: 3;
        text-align: center;
        padding: 12px 10px 13px;
        background: linear-gradient(180deg, rgba(17, 31, 47, 0.98), rgba(9, 21, 34, 0.98));
        border: 1px solid #2b3f58;
        border-radius: 16px;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.03);
        transition: box-shadow .3s ease, border-color .3s ease;
    }}

    .flow-node.node-active {{
        border-color: var(--accent);
        box-shadow: 0 0 0 1px var(--accent) inset, 0 12px 28px rgba(0, 0, 0, 0.35);
    }}

    .node-icon-wrap {{ display: flex; justify-content: center; margin-bottom: 6px; }}
    .node-icon {{ width: 38px; height: 38px; }}
    .tesla-icon {{ width: 30px; height: 38px; }}

    .node-label {{
        font-size: 12px; font-weight: 800; letter-spacing: 0.4px;
        text-transform: uppercase; color: #9eb0c4; margin-bottom: 4px;
    }}

    .node-value {{ font-size: 20px; font-weight: 900; line-height: 1.1; }}
    .node-sub {{ margin-top: 3px; font-size: 11.5px; color: #8698ac; }}

    .panel-title {{
        margin-bottom: 12px; font-size: 13px; font-weight: 800;
        letter-spacing: 0.45px; text-transform: uppercase;
    }}

    .detail-grid {{
        display: grid; grid-template-columns: minmax(0, 1fr) auto;
        gap: 9px 14px; align-items: center; font-size: 13.5px;
    }}
    .detail-grid span {{ color: #a5b5c6; }}
    .detail-grid strong {{ color: #f5f7fb; white-space: nowrap; }}

    .rec-value {{ font-size: 42px; font-weight: 950; text-align: center; margin: 4px 0 6px; }}
    .rec-note {{ text-align: center; color: #9eb0c4; font-size: 12.5px; margin-bottom: 14px; }}

    .lower-row {{
        display: grid;
        grid-template-columns: 1.3fr 1fr 1fr;
        gap: 14px;
        align-items: start;
    }}

    .stat-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
    }}

    .stat-block {{
        padding: 11px 12px;
        background: rgba(255,255,255,0.02);
        border: 1px solid #223245;
        border-radius: 12px;
    }}

    .stat-block-label {{ font-size: 11px; color: #8698ac; text-transform: uppercase; letter-spacing: .4px; margin-bottom: 4px; }}
    .stat-block-value {{ font-size: 19px; font-weight: 900; }}
    .stat-block-sub {{ font-size: 11px; color: #8698ac; margin-top: 2px; }}

    .co2-strip {{
        margin-top: 12px;
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 12px;
        background: rgba(105, 239, 121, 0.08);
        border: 1px solid rgba(105, 239, 121, 0.28);
        border-radius: 12px;
        font-size: 12.5px;
        color: #cfe9d3;
    }}

    .co2-strip svg {{ width: 22px; height: 22px; flex-shrink: 0; }}

    .temp-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
    }}

    .temp-chip {{
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        padding: 12px 8px;
        background: rgba(255,255,255,0.02);
        border: 1px solid #223245;
        border-radius: 12px;
    }}

    .temp-icon-wrap {{ margin-bottom: 4px; }}
    .temp-icon {{ width: 20px; height: 40px; }}
    .temp-label {{ font-size: 10.5px; color: #8698ac; text-transform: uppercase; letter-spacing: .3px; margin-bottom: 2px; }}
    .temp-value {{ font-size: 19px; font-weight: 900; }}

    .string-row {{
        display: grid;
        grid-template-columns: 130px 1fr 150px;
        align-items: center;
        gap: 10px;
        margin-bottom: 10px;
        font-size: 12.5px;
    }}

    .string-label {{ color: #a5b5c6; font-weight: 700; line-height: 1.25; }}
    .string-bar-track {{ height: 8px; border-radius: 5px; background: rgba(255,255,255,0.06); overflow: hidden; }}
    .string-bar-fill {{ height: 100%; border-radius: 5px; }}
    .string-stats {{ display: flex; gap: 8px; justify-content: flex-end; color: #cdd8e4; font-variant-numeric: tabular-nums; }}

    @media (max-width: 1150px) {{
        .metric-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .main-row {{ grid-template-columns: 1fr; }}
        .lower-row {{ grid-template-columns: 1fr; }}
    }}
    </style>
    </head>
    <body>
    <div class="dashboard">

        <div class="top-row">
            <div>
                <div class="brand-title">⚡ Home Energy Dashboard</div>
                <div class="brand-sub">Live EG4 and Tesla Wall Connector data</div>
            </div>
            <div>
                <div class="status-pill"><span class="dot"></span>Live</div>
                <div class="updated-note">Updated {context['updated_at']}</div>
            </div>
        </div>

        <div class="metric-grid">
            <div class="card">
                <div class="metric-label" style="color:{COLOUR_SOLAR}">Power coming in</div>
                <div class="metric-value">{watts(context['power_in'])}</div>
                <div class="metric-note">Solar and battery discharge</div>
            </div>
            <div class="card">
                <div class="metric-label" style="color:{COLOUR_HOME}">Power going out</div>
                <div class="metric-value">{watts(context['total_output'])}</div>
                <div class="metric-note">Car charging, kitchen and connected loads</div>
            </div>
            <div class="card">
                <div class="metric-label" style="color:{context['battery_colour']}">Battery level</div>
                <div class="metric-value" style="color:{context['battery_colour']}">{context['battery_soc']:.0f}%</div>
                <div class="metric-note">{context['battery_label']} · {context['battery_voltage']:.1f} V</div>
            </div>
            <div class="card">
                <div class="metric-label" style="color:{COLOUR_CYAN}">System headroom</div>
                <div class="metric-value">{watts(context['headroom'])}</div>
                <div class="metric-note">Room left before the {watts(SYSTEM_CAPACITY_W)} system limit</div>
            </div>
        </div>

        <div class="main-row">
            <div class="flow-canvas">
                <div class="flow-title">ENERGY FLOW</div>
                <svg class="flow-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
                    {''.join(edge_svgs)}
                </svg>
                <svg class="flow-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
                    {''.join(dot_svgs)}
                </svg>
                {''.join(node_html)}
            </div>

            <div class="side-panels">
                <div class="card" style="border-color:#6b3434; margin-bottom:14px;">
                    <div class="panel-title" style="color:{COLOUR_TESLA}">Tesla Wall Connector — actual</div>
                    <div style="font-size:21px; font-weight:900; margin-bottom:13px;">{context['tesla_status']}</div>
                    <div class="detail-grid">
                        <span>Vehicle connected</span><strong>{"Yes" if context['vehicle_connected'] else "No"}</strong>
                        <span>Contactor closed</span><strong>{"Yes" if context['contactor_closed'] else "No"}</strong>
                        <span>Current</span><strong>{context['tesla_current']:.1f} A</strong>
                        <span>Voltage</span><strong>{context['tesla_voltage']:.1f} V</strong>
                        <span>Power</span><strong>{watts(context['tesla_power'])}</strong>
                        <span>Last session</span><strong>{kwh_from_wh(context['session_energy_wh'])}</strong>
                        <span>Lifetime energy</span><strong>{kwh_from_wh(context['lifetime_energy_wh'])}</strong>
                        <span>Handle temperature</span><strong>{context['handle_temp']:.1f} °C</strong>
                        <span>Alerts</span><strong>{context['alert_count']}</strong>
                    </div>
                </div>

                <div class="card" style="border-color:#2c653c;">
                    <div class="panel-title" style="color:{COLOUR_BATTERY_GREEN}">Charging recommendation</div>
                    <div class="rec-value">{context['recommended_a']} A</div>
                    <div class="rec-note">Recommended current limit with a {watts(RESERVE_MARGIN_W)} reserve</div>
                    <div class="detail-grid">
                        <span>Configured maximum</span><strong>{TESLA_CONFIGURED_MAX_A} A</strong>
                        <span>Kitchen and other</span><strong>{watts(context['other_load'])}</strong>
                        <span>Current total output</span><strong>{watts(context['total_output'])}</strong>
                        <span>Available headroom</span><strong>{watts(context['headroom'])}</strong>
                    </div>
                </div>
            </div>
        </div>

        <div class="lower-row">
            <div class="card">
                <div class="panel-title" style="color:{COLOUR_SOLAR}">Lifetime stats</div>
                <div class="stat-grid">
                    <div class="stat-block">
                        <div class="stat-block-label">Solar produced</div>
                        <div class="stat-block-value" style="color:{COLOUR_SOLAR}">{kwh(context['yield_lifetime'])}</div>
                        <div class="stat-block-sub">{kwh(context['yield_today'])} today</div>
                    </div>
                    <div class="stat-block">
                        <div class="stat-block-label">Delivered to home</div>
                        <div class="stat-block-value" style="color:{COLOUR_HOME}">{kwh(context['usage_lifetime'])}</div>
                        <div class="stat-block-sub">{kwh(context['usage_today'])} today</div>
                    </div>
                    <div class="stat-block">
                        <div class="stat-block-label">Charged to battery</div>
                        <div class="stat-block-value" style="color:{COLOUR_PURPLE}">{kwh(context['charge_lifetime'])}</div>
                        <div class="stat-block-sub">{kwh(context['charge_today'])} today</div>
                    </div>
                    <div class="stat-block">
                        <div class="stat-block-label">Discharged from battery</div>
                        <div class="stat-block-value" style="color:{COLOUR_PURPLE}">{kwh(context['discharge_lifetime'])}</div>
                        <div class="stat-block-sub">{kwh(context['discharge_today'])} today</div>
                    </div>
                </div>
                <div class="co2-strip">
                    {icon_leaf()}
                    <div>~{context['co2_avoided_kg']:,.0f} kg CO2 avoided over the system's life (rough estimate, {CO2_KG_PER_KWH} kg/kWh average grid mix)</div>
                </div>
            </div>

            <div class="card">
                <div class="panel-title" style="color:{COLOUR_TESLA}">System temperatures</div>
                <div class="temp-grid">
                    {''.join(temp_chips)}
                </div>
            </div>

            <div class="card">
                <div class="panel-title" style="color:{COLOUR_SOLAR}">Solar array detail</div>
                {''.join(string_rows)}
            </div>
        </div>
    </div>
    </body>
    </html>
    """
    return html


inverter_df, tesla_df = load_data()

if inverter_df.empty:
    st.error("No inverter readings yet. Start collector.py and wait for one collection cycle.")
    st.stop()


latest_inverter_time = inverter_df["recorded_at"].max()

latest_inverters = (
    inverter_df[inverter_df["recorded_at"] == latest_inverter_time]
    .sort_values("inverter_serial")
    .reset_index(drop=True)
)

latest_tesla = tesla_df.iloc[-1] if not tesla_df.empty else None


total_solar = number(latest_inverters["pv_total_power_w"].sum())
total_output = number(latest_inverters["output_power_w"].sum())
battery_charge = number(latest_inverters["battery_charge_power_w"].sum())
battery_discharge = number(latest_inverters["battery_discharge_power_w"].sum())
battery_soc = number(latest_inverters["battery_soc_percent"].mean())
battery_voltage = number(latest_inverters["battery_voltage_v"].mean())


if latest_tesla is not None:
    tesla_current = number(latest_tesla["charging_current_a"])
    tesla_voltage = number(latest_tesla["grid_voltage_v"])
    tesla_power = number(latest_tesla["charging_power_w"])
    vehicle_connected = bool(latest_tesla["vehicle_connected"])
    contactor_closed = bool(latest_tesla["contactor_closed"])
    session_energy_wh = number(latest_tesla["session_energy_wh"])
    lifetime_energy_wh = number(latest_tesla["lifetime_energy_wh"])
    handle_temp = number(latest_tesla["handle_temp_c"])
    try:
        alerts = json.loads(latest_tesla["alerts_json"] or "[]")
    except (json.JSONDecodeError, TypeError):
        alerts = []
else:
    tesla_current = tesla_voltage = tesla_power = 0.0
    vehicle_connected = contactor_closed = False
    session_energy_wh = lifetime_energy_wh = handle_temp = 0.0
    alerts = []


tesla_is_charging = contactor_closed and tesla_current > 0.2

if tesla_is_charging:
    tesla_status = "Charging"
elif vehicle_connected:
    tesla_status = "Connected"
else:
    tesla_status = "Idle"


other_load = max(total_output - tesla_power, 0.0)

battery_net = battery_discharge - battery_charge
if battery_net > 10:
    battery_label = "Discharging"
elif battery_net < -10:
    battery_label = "Charging"
else:
    battery_label = "Idle"
battery_flow = abs(battery_net)
battery_colour = battery_tier_colour(battery_soc)


available_for_tesla = max(SYSTEM_CAPACITY_W - other_load - RESERVE_MARGIN_W, 0.0)
recommended_a = min(
    TESLA_CONFIGURED_MAX_A,
    math.floor(available_for_tesla / max(tesla_voltage or 240, 1)),
)

headroom = max(SYSTEM_CAPACITY_W - total_output, 0.0)


if latest_inverter_time.tzinfo is None:
    latest_inverter_time = latest_inverter_time.tz_localize("UTC")
latest_local = latest_inverter_time.tz_convert(LOCAL_TIMEZONE)


# --- lifetime / today energy stats (summed across all inverters) ------

def lifetime_sum(column: str) -> float:
    return number(column_or_zero(latest_inverters, column).sum())


yield_lifetime = lifetime_sum("yield_lifetime_kwh")
charge_lifetime = lifetime_sum("charge_lifetime_kwh")
discharge_lifetime = lifetime_sum("discharge_lifetime_kwh")
usage_lifetime = lifetime_sum("usage_lifetime_kwh")

yield_today = lifetime_sum("yield_today_kwh")
charge_today = lifetime_sum("charge_today_kwh")
discharge_today = lifetime_sum("discharge_today_kwh")
usage_today = lifetime_sum("usage_today_kwh")

co2_avoided_kg = yield_lifetime * CO2_KG_PER_KWH


# --- system temperatures (worst-case across all inverters) -------------

temp_columns = [
    ("Internal", "inverter_temp_c"),
    ("Radiator 1", "radiator1_temp_c"),
    ("Radiator 2", "radiator2_temp_c"),
    ("Battery", "battery_temp_c"),
]

temps = []
for label, column in temp_columns:
    if has_column(latest_inverters, column):
        value = number(column_or_zero(latest_inverters, column).max())
    else:
        value = 0.0
    temps.append({"label": label, "value": value})


# --- per-string solar array detail --------------------------------------

strings = []
max_string_power = max(
    number(latest_inverters["pv1_power_w"].max() if "pv1_power_w" in latest_inverters else 0),
    number(latest_inverters["pv2_power_w"].max() if "pv2_power_w" in latest_inverters else 0),
    1.0,
)
for inverter_index, (_, row) in enumerate(latest_inverters.iterrows(), start=1):
    suffix = f" · Inverter {inverter_index}" if len(latest_inverters) > 1 else ""
    for string_num in (1, 2):
        power_col = f"pv{string_num}_power_w"
        voltage_col = f"pv{string_num}_voltage_v"
        current_col = f"pv{string_num}_current_a"
        if power_col not in row:
            continue
        power = number(row[power_col])
        voltage = number(row.get(voltage_col, 0))
        current = number(row.get(current_col, 0))
        strings.append(
            {
                "label": f"Panel group {string_num}{suffix}",
                "power": power,
                "voltage": voltage,
                "current": current,
                "share": (power / max_string_power) * 100,
            }
        )


# --- assemble flow-diagram nodes and edges -----------------------------

solar_active = total_solar > 30
battery_active = battery_flow > 10
tesla_active = tesla_power > 20
home_active = other_load > 5

nodes = [
    {
        "id": "solar", "x": 18, "y": 18, "colour": COLOUR_SOLAR, "active": solar_active,
        "icon": icon_solar(solar_active), "label": "Solar panels",
        "value": watts(total_solar),
        "sub": "Producing now" if solar_active else "No sun right now",
    },
    {
        "id": "hub", "x": 50, "y": 50, "colour": COLOUR_SYSTEM, "active": True,
        "icon": icon_inverter(), "label": f"EG4 inverter{'s' if len(latest_inverters) > 1 else ''}",
        "value": watts(total_solar),
        "sub": f"{len(latest_inverters)} unit{'s' if len(latest_inverters) > 1 else ''} online",
    },
    {
        "id": "battery", "x": 82, "y": 18, "colour": battery_colour, "active": True,
        "icon": icon_battery(battery_soc), "label": "Battery bank",
        "value": f"{battery_soc:.0f}%",
        "sub": battery_label,
    },
    {
        "id": "home", "x": 30, "y": 86, "colour": COLOUR_HOME, "active": home_active,
        "icon": icon_home(home_active), "label": "Home loads",
        "value": watts(other_load),
        "sub": "Powering your home" if home_active else "Minimal draw",
    },
    {
        "id": "tesla", "x": 70, "y": 86, "colour": COLOUR_TESLA_ON if tesla_active else COLOUR_TESLA,
        "active": tesla_active,
        "icon": icon_tesla_connector(tesla_is_charging, vehicle_connected), "label": "Car charger",
        "value": watts(tesla_power),
        "sub": tesla_status,
    },
]

edges = [
    {
        "id": "edge-solar", "d": "M18,18 L50,50",
        "colour": COLOUR_SOLAR, "active": solar_active, "duration": 2.2,
    },
    {
        "id": "edge-battery",
        "d": "M82,18 L50,50" if battery_net > 10 else "M50,50 L82,18",
        "colour": battery_colour, "active": battery_active, "duration": 2.0,
    },
    {
        "id": "edge-home", "d": "M50,50 L30,86",
        "colour": COLOUR_HOME, "active": home_active, "duration": 1.8,
    },
    {
        "id": "edge-tesla", "d": "M50,50 L70,86",
        "colour": COLOUR_TESLA_ON, "active": tesla_active, "duration": 1.6,
    },
]

context = {
    "nodes": nodes,
    "edges": edges,
    "strings": strings,
    "temps": temps,
    "updated_at": latest_local.strftime("%-I:%M:%S %p"),
    "power_in": total_solar + battery_discharge,
    "total_output": total_output,
    "battery_flow": battery_flow,
    "battery_label": battery_label,
    "battery_soc": battery_soc,
    "battery_voltage": battery_voltage,
    "battery_colour": battery_colour,
    "headroom": headroom,
    "tesla_status": tesla_status,
    "vehicle_connected": vehicle_connected,
    "contactor_closed": contactor_closed,
    "tesla_current": tesla_current,
    "tesla_voltage": tesla_voltage,
    "tesla_power": tesla_power,
    "session_energy_wh": session_energy_wh,
    "lifetime_energy_wh": lifetime_energy_wh,
    "handle_temp": handle_temp,
    "alert_count": len(alerts),
    "recommended_a": recommended_a,
    "other_load": other_load,
    "yield_lifetime": yield_lifetime,
    "charge_lifetime": charge_lifetime,
    "discharge_lifetime": discharge_lifetime,
    "usage_lifetime": usage_lifetime,
    "yield_today": yield_today,
    "charge_today": charge_today,
    "discharge_today": discharge_today,
    "usage_today": usage_today,
    "co2_avoided_kg": co2_avoided_kg,
}


dashboard_html = dedent_html(build_dashboard_html(context))

if hasattr(st, "iframe"):
    # Streamlit >= 1.51 replacement for components.html. height="content"
    # (the default) auto-measures the page so adding panels never clips.
    st.iframe(dashboard_html, height="content")
else:
    components.html(dashboard_html, height=1500, scrolling=True)


st.markdown("### Power over time")

history = (
    inverter_df
    .groupby("recorded_at")
    .agg(
        solar=("pv_total_power_w", "sum"),
        loads=("output_power_w", "sum"),
        battery_charge=("battery_charge_power_w", "sum"),
        battery_discharge=("battery_discharge_power_w", "sum"),
    )
)

history_colours = [COLOUR_SOLAR, COLOUR_HOME, COLOUR_PURPLE, "#9d6bd6"]
history_names = {
    "solar": "Power from solar",
    "loads": "Total power going out",
    "battery_charge": "Power charging battery",
    "battery_discharge": "Power coming from battery",
}

if not tesla_df.empty:
    tesla_history = tesla_df.set_index("recorded_at")[["charging_power_w"]]
    history = history.join(tesla_history, how="outer").sort_index().ffill()
    history_names["charging_power_w"] = "Tesla charging power"
    history_colours.append(COLOUR_TESLA)

history = history.rename(columns=history_names)

st.line_chart(
    history,
    height=290,
    color=history_colours[: len(history.columns)],
)


with st.expander("Raw but renamed details"):
    display_columns = {
        "inverter_serial": "Inverter",
        "pv1_power_w": "Panel group 1 output",
        "pv2_power_w": "Panel group 2 output",
        "pv_total_power_w": "Total solar coming in",
        "output_power_w": "Power going out",
        "battery_charge_power_w": "Power going into battery",
        "battery_discharge_power_w": "Power coming from battery",
        "battery_soc_percent": "Battery level",
        "battery_voltage_v": "Battery voltage",
    }
    available_columns = [c for c in display_columns if c in latest_inverters.columns]
    display_data = latest_inverters[available_columns].rename(columns=display_columns)

    st.dataframe(display_data, hide_index=True, width="stretch")


st.caption(
    "Tesla values come directly from the Wall Connector's local vitals "
    "endpoint. EG4 values come from the EG4 monitoring cloud and may "
    "update less frequently. Temperature colour bands and the CO2 estimate "
    "are informal, adjustable defaults, not manufacturer specs."
)