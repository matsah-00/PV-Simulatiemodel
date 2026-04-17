"""
solar.py

Doel:
- zonnepositie berekenen voor elk tijdstip
- extraterrestrische instraling bepalen
- hulpkolommen leveren voor de irradiance-berekeningen

Aannames:
- input timestamps zijn timezone-aware
- lengtegraad positief voor oost
- azimuth-conventie:
    0   = noord
    90  = oost
    180 = zuid
    270 = west
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_solar_position(df: pd.DataFrame, latitude: float, longitude: float) -> pd.DataFrame:
    """
    Voeg zonnepositie toe aan het DataFrame.

    Outputkolommen:
    - day_of_year
    - solar_zenith_deg
    - solar_azimuth_deg
    - cos_zenith
    - extraterrestrial_normal_wm2
    - extraterrestrial_horizontal_wm2
    """
    result = df.copy()

    times = pd.DatetimeIndex(result["time"])

    # Dagnummer in het jaar
    day_of_year = times.dayofyear.to_numpy()

    # Kloktijd in uren
    hour_decimal = (
        times.hour.to_numpy()
        + times.minute.to_numpy() / 60.0
        + times.second.to_numpy() / 3600.0
    )

    # Tijdzone-offset in uren, inclusief zomer-/wintertijd
    utc_offset_hours = np.array(
        [timestamp.utcoffset().total_seconds() / 3600.0 for timestamp in times]
    )

    # Fractioneel jaar (NOAA benadering)
    gamma = 2.0 * np.pi / 365.0 * (day_of_year - 1 + (hour_decimal - 12.0) / 24.0)

    # Equation of time in minuten
    equation_of_time_min = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2 * gamma)
        - 0.040849 * np.sin(2 * gamma)
    )

    # Declination in radialen
    declination_rad = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2 * gamma)
        + 0.000907 * np.sin(2 * gamma)
        - 0.002697 * np.cos(3 * gamma)
        + 0.00148 * np.sin(3 * gamma)
    )

    latitude_rad = np.radians(latitude)

    # True Solar Time
    # 4 * longitude werkt in minuten
    time_offset_min = equation_of_time_min + 4.0 * longitude - 60.0 * utc_offset_hours
    true_solar_time_min = hour_decimal * 60.0 + time_offset_min

    # Hour angle in graden en radialen
    hour_angle_deg = true_solar_time_min / 4.0 - 180.0
    hour_angle_rad = np.radians(hour_angle_deg)

    # Cosinus van de zenithoek
    cos_zenith = (
        np.sin(latitude_rad) * np.sin(declination_rad)
        + np.cos(latitude_rad) * np.cos(declination_rad) * np.cos(hour_angle_rad)
    )
    cos_zenith = np.clip(cos_zenith, -1.0, 1.0)

    solar_zenith_deg = np.degrees(np.arccos(cos_zenith))

    # Solar azimuth, 0=noord, 90=oost, 180=zuid, 270=west
    # Robuuste benadering met atan2
    azimuth_rad = np.arctan2(
        np.sin(hour_angle_rad),
        np.cos(hour_angle_rad) * np.sin(latitude_rad)
        - np.tan(declination_rad) * np.cos(latitude_rad),
    )
    solar_azimuth_deg = (np.degrees(azimuth_rad) + 180.0) % 360.0

    # Extraterrestrische instraling loodrecht op de zonnestraal
    extraterrestrial_normal_wm2 = 1367.0 * (
        1.0 + 0.033 * np.cos(2.0 * np.pi * day_of_year / 365.0)
    )

    # Horizontale component boven de atmosfeer
    extraterrestrial_horizontal_wm2 = np.maximum(
        extraterrestrial_normal_wm2 * np.maximum(cos_zenith, 0.0),
        0.0,
    )

    result["day_of_year"] = day_of_year
    result["solar_zenith_deg"] = solar_zenith_deg
    result["solar_azimuth_deg"] = solar_azimuth_deg
    result["cos_zenith"] = np.maximum(cos_zenith, 0.0)
    result["extraterrestrial_normal_wm2"] = extraterrestrial_normal_wm2
    result["extraterrestrial_horizontal_wm2"] = extraterrestrial_horizontal_wm2

    return result