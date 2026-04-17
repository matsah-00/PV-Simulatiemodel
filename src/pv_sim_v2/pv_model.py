"""
pv_model.py

Doel:
- AC vermogen berekenen uit POA/GTI, PSTC en PR
- totale energie over de periode berekenen
- 10-minuten data omzetten naar uurdata

Volgens jouw model:
PAC(t) = PSTC * (POA / 1000) * PR
"""

from __future__ import annotations

import pandas as pd


def add_pac(df: pd.DataFrame, pstc_kwp: float, pr: float) -> pd.DataFrame:
    """
    Voeg PAC toe aan het DataFrame.

    Parameters:
    - pstc_kwp: DC nameplate power in kWp
    - pr: performance ratio, bijv. 0.82

    Belangrijk:
    - Als poa_global leeg is, blijft pac_kw ook leeg
    """
    result = df.copy()

    result["pac_kw"] = pstc_kwp * (result["poa_global"] / 1000.0) * pr
    result.loc[result["poa_global"].isna(), "pac_kw"] = pd.NA
    result.loc[result["pac_kw"] < 0, "pac_kw"] = 0.0

    return result


def calculate_total_energy_kwh(df: pd.DataFrame) -> float:
    """
    Integreer het tijdsafhankelijke AC vermogen naar totale energie in kWh.

    We bepalen het tijdsinterval uit de mediane stapgrootte van de tijdreeks.
    """
    if len(df) < 2:
        return 0.0

    time_deltas_hours = (
        df["time"].sort_values().diff().dropna().dt.total_seconds() / 3600.0
    )

    if time_deltas_hours.empty:
        return 0.0

    dt_hours = float(time_deltas_hours.median())

    total_energy_kwh = float((df["pac_kw"] * dt_hours).sum())

    return total_energy_kwh


def resample_to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """
    Zet 10-minuten simulatie-uitvoer om naar uurdata.

    Werkwijze:
    - tijd wordt index
    - stralings- en vermogenswaarden worden gemiddeld per uur
    - energie wordt opnieuw bepaald op basis van gemiddeld uurvermogen

    Let op:
    - Voor irradiance (ghi, dhi, dni, poa) is een uurgemiddelde logisch
    - Voor pac_kw gebruiken we ook een uurgemiddelde
    - Daarna berekenen we hourly_energy_kwh = pac_kw * 1 uur
    """
    if df.empty:
        return df.copy()

    hourly = df.copy()

    # Zorg dat tijd de index is
    hourly = hourly.sort_values("time").set_index("time")

    # Kolommen die gemiddeld mogen worden per uur
    mean_columns = [
        "ghi",
        "kt",
        "dhi",
        "dni",
        "solar_zenith_deg",
        "solar_azimuth_deg",
        "cos_zenith",
        "extraterrestrial_normal_wm2",
        "extraterrestrial_horizontal_wm2",
        "poa_direct",
        "poa_diffuse",
        "poa_ground",
        "gti",
        "poa_global",
        "cos_aoi",
        "pac_kw",
    ]

    # Neem alleen kolommen die echt bestaan
    mean_columns = [col for col in mean_columns if col in hourly.columns]

    hourly_df = hourly[mean_columns].resample("1h").mean()

    # Verwijder volledig lege uren
    hourly_df = hourly_df.dropna(how="all")

    # Voeg energie per uur toe
    if "pac_kw" in hourly_df.columns:
        hourly_df["hourly_energy_kwh"] = hourly_df["pac_kw"] * 1.0

    hourly_df = hourly_df.reset_index()

    return hourly_df