"""
irradiance.py

Doel:
- GHI splitsen in diffuse en directe component
- GHI omzetten naar GTI/POA

Model maakt gebruik van: 
- Erbs-decompositie voor DHI / DNI
- Ground reflected component met albedo

Terminologie:
- GHI = Global Horizontal Irradiance
- DHI = Diffuse Horizontal Irradiance
- DNI = Direct Normal Irradiance
- POA / GTI = instraling op paneelvlak
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_dhi_dni_erbs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Gebruik de Erbs-correlatie om GHI op te splitsen in DHI en DNI.

    Verwachte inputkolommen:
    - ghi : globale horizontale instraling [W/m²]
    - cos_zenith : cosinus van de zonnezenithoek [-]
    - extraterrestrial_horizontal_wm2 : extraterrestrische horizontale instraling [W/m²]

    Outputkolommen:
    - kt : clearness index [-]
    - dhi : diffuse horizontale instraling [W/m²]
    - dni : directe normale instraling [W/m²]

    Opmerkingen:
    - Bij zeer lage zonnestand wordt DNI op 0 gezet om onrealistische pieken te vermijden.
    - Als ghi ontbreekt, blijven kt/dhi/dni ook leeg (NaN).
    """

    result = df.copy()

    ghi = result["ghi"].to_numpy(dtype=float)
    cos_zenith = result["cos_zenith"].to_numpy(dtype=float)
    i0h = result["extraterrestrial_horizontal_wm2"].to_numpy(dtype=float)

    # Negatieve meetwaarden afvangen, maar NaN behouden
    ghi = np.where(np.isnan(ghi), np.nan, np.clip(ghi, 0.0, None))
    cos_zenith = np.where(np.isnan(cos_zenith), np.nan, np.clip(cos_zenith, -1.0, 1.0))
    i0h = np.where(np.isnan(i0h), np.nan, np.clip(i0h, 0.0, None))

    # Start met NaN-arrays zodat ontbrekende waarden leeg blijven
    kt = np.full_like(ghi, np.nan, dtype=float)
    kd = np.full_like(ghi, np.nan, dtype=float)
    dhi = np.full_like(ghi, np.nan, dtype=float)
    dni = np.full_like(ghi, np.nan, dtype=float)

    # Alleen rekenen als alle benodigde input aanwezig is
    valid_input = (~np.isnan(ghi)) & (~np.isnan(cos_zenith)) & (~np.isnan(i0h))

    # Dagconditie: alleen rekenen wanneer de zon fysisch boven de horizon zit
    day = valid_input & (i0h > 0.0) & (cos_zenith > 0.0)

    # Voor geldige input buiten daglicht mag kt/dhi/dni naar 0
    night_or_dark = valid_input & (~day)
    kt[night_or_dark] = 0.0
    kd[night_or_dark] = 0.0
    dhi[night_or_dark] = 0.0
    dni[night_or_dark] = 0.0

    # Clearness index
    kt[day] = ghi[day] / i0h[day]

    # Voor Erbs is clippen tot 1.0 meestal robuuster dan tot 2.0
    kt[day] = np.clip(kt[day], 0.0, 1.0)

    # Erbs diffuse fraction (kd)
    mask_1 = day & (kt <= 0.22)
    kd[mask_1] = 1.0 - 0.09 * kt[mask_1]

    mask_2 = day & (kt > 0.22) & (kt <= 0.80)
    kd[mask_2] = (
        0.9511
        - 0.1604 * kt[mask_2]
        + 4.3880 * kt[mask_2] ** 2
        - 16.6380 * kt[mask_2] ** 3
        + 12.3360 * kt[mask_2] ** 4
    )

    mask_3 = day & (kt > 0.80)
    kd[mask_3] = 0.165

    kd[day] = np.clip(kd[day], 0.0, 1.0)

    # Diffuse horizontale instraling
    valid_kd = day & (~np.isnan(kd))
    dhi[valid_kd] = kd[valid_kd] * ghi[valid_kd]
    dhi[valid_kd] = np.clip(dhi[valid_kd], 0.0, ghi[valid_kd])  # fysisch: DHI <= GHI

    # Directe normale instraling
    # Extra drempel op cos_zenith om onrealistische DNI-pieken bij lage zonnestand te vermijden
    good_sun = valid_kd & (cos_zenith > 0.065)

    dni[good_sun] = (ghi[good_sun] - dhi[good_sun]) / cos_zenith[good_sun]
    dni[good_sun] = np.clip(dni[good_sun], 0.0, None)

    # Overige dagpunten met te lage zonnestand krijgen DNI = 0
    low_sun = valid_kd & (cos_zenith <= 0.065)
    dni[low_sun] = 0.0

    result["kt"] = kt
    result["dhi"] = dhi
    result["dni"] = dni

    return result

def add_poa_irradiance(
    df: pd.DataFrame,
    tilt_deg: float,
    surface_azimuth_deg: float,
    albedo: float = 0.20,
) -> pd.DataFrame:
    """
    Bereken de instraling op het paneelvlak (POA / GTI).

    Verwachte inputkolommen:
    - ghi
    - dhi
    - dni
    - solar_zenith_deg
    - solar_azimuth_deg
    - cos_zenith

    Azimuth conventie:
    - 0 = noord
    - 90 = oost
    - 180 = zuid
    - 270 = west
    """
    result = df.copy()

    tilt_rad = np.radians(tilt_deg)
    solar_zenith_rad = np.radians(result["solar_zenith_deg"].to_numpy(dtype=float))
    solar_azimuth_rad = np.radians(result["solar_azimuth_deg"].to_numpy(dtype=float))
    surface_azimuth_rad = np.radians(surface_azimuth_deg)

    ghi = result["ghi"].to_numpy(dtype=float)
    dhi = result["dhi"].to_numpy(dtype=float)
    dni = result["dni"].to_numpy(dtype=float)
    cos_zenith = result["cos_zenith"].to_numpy(dtype=float)

    # Cosinus van de invalshoek op het paneelvlak
    cos_aoi = (
        np.cos(solar_zenith_rad) * np.cos(tilt_rad)
        + np.sin(solar_zenith_rad) * np.sin(tilt_rad)
        * np.cos(solar_azimuth_rad - surface_azimuth_rad)
    )
    cos_aoi = np.clip(cos_aoi, 0.0, None)

    # Directe component op paneelvlak
    poa_direct = dni * cos_aoi

    # Diffuse component via isotrope hemel
    poa_diffuse = dhi * (1.0 + np.cos(tilt_rad)) / 2.0

    # Gereflecteerde grondcomponent
    poa_ground = albedo * ghi * (1.0 - np.cos(tilt_rad)) / 2.0

    # Totale paneelvlak-instraling
    poa_global = poa_direct + poa_diffuse + poa_ground

    # 'GTI' en 'POA global' gebruiken we hier als hetzelfde concept
    result["poa_direct"] = poa_direct
    result["poa_diffuse"] = poa_diffuse
    result["poa_ground"] = poa_ground
    result["gti"] = poa_global
    result["poa_global"] = poa_global
    result["cos_aoi"] = cos_aoi

    # Veiligheidsclip
    result["poa_global"] = result["poa_global"].clip(lower=0.0)
    result["gti"] = result["gti"].clip(lower=0.0)

    return result