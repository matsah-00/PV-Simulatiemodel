"""
simulation.py

Doel:
- berekening uitvoeren:
    1. 3 dichtstbijzijnde KNMI stations zoeken
    2. GHI ophalen en interpoleren
    3. zonnepositie berekenen
    4. GHI -> DHI/DNI
    5. DHI/DNI -> GTI/POA
    6. PAC en energie berekenen
    7. 10-min data omzetten naar uurdata
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

import pandas as pd

from pv_sim_v2.knmi_client import fetch_interpolated_ghi_from_nearest_stations
from pv_sim_v2.solar import add_solar_position
from pv_sim_v2.irradiance import add_dhi_dni_erbs, add_poa_irradiance
from pv_sim_v2.pv_model import add_pac, calculate_total_energy_kwh, resample_to_hourly


def run_pv_simulation(
    latitude: float,
    longitude: float,
    start_local: str,
    end_local: str,
    tilt_deg: float,
    surface_azimuth_deg: float,
    pr: float,
    pstc_kwp: float,
    albedo: float = 0.20,
    timezone_name: str = "Europe/Amsterdam",
) -> Tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]:
    """
    Draai de volledige PV simulatie.

    Retourneert:
    - summary dict
    - 10-minuten DataFrame
    - uur DataFrame
    """
    # 1. Interpoleer GHI op basis van de 3 dichtstbijzijnde stations
    used_stations, df_10min = fetch_interpolated_ghi_from_nearest_stations(
        latitude=latitude,
        longitude=longitude,
        start_local=start_local,
        end_local=end_local,
        timezone_name=timezone_name,
        n_stations=3,
        distance_power=2.0,
        search_pool=10,
    )

    # 2. Zonnepositie toevoegen
    df_10min = add_solar_position(df_10min, latitude=latitude, longitude=longitude)

    # 3. GHI opdelen in diffuse en directe component
    df_10min = add_dhi_dni_erbs(df_10min)

    # 4. Naar paneelvlak omzetten
    df_10min = add_poa_irradiance(
        df_10min,
        tilt_deg=tilt_deg,
        surface_azimuth_deg=surface_azimuth_deg,
        albedo=albedo,
    )

    # 5. PAC berekenen
    df_10min = add_pac(df_10min, pstc_kwp=pstc_kwp, pr=pr)

    # 6. Totale energie berekenen op 10-min resolutie
    total_energy_kwh_10min = calculate_total_energy_kwh(df_10min)

    # 7. Maak uurdata op basis van de 10-min data
    df_hourly = resample_to_hourly(df_10min)

    # 8. Totale energie op uurniveau
    total_energy_kwh_hourly = 0.0
    if not df_hourly.empty and "hourly_energy_kwh" in df_hourly.columns:
        total_energy_kwh_hourly = float(df_hourly["hourly_energy_kwh"].sum())

    # Stations samenvatten
    station_lines = []
    for idx, station in enumerate(used_stations, start=1):
        station_lines.append(
            {
                "station_rank": idx,
                "station_id": station["id"],
                "station_name": station["name"],
                "distance_km": round(float(station["distance_km"]), 2),
                "weight": round(float(station["weight"]), 4),
            }
        )

    summary = {
        "input_latitude": latitude,
        "input_longitude": longitude,
        "stations_used": station_lines,
        "start_local": start_local,
        "end_local": end_local,
        "tilt_deg": tilt_deg,
        "surface_azimuth_deg": surface_azimuth_deg,
        "pr": pr,
        "pstc_kwp": pstc_kwp,
        "total_energy_kwh_10min": round(total_energy_kwh_10min, 3),
        "total_energy_kwh_hourly": round(total_energy_kwh_hourly, 3),
        "peak_pac_kw": round(float(df_10min["pac_kw"].max()), 3),
        "mean_poa_wm2": round(float(df_10min["poa_global"].mean()), 3),
    }

    return summary, df_10min, df_hourly