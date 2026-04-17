"""
knmi_client.py

Doel:
- KNMI stations ophalen via de EDR API
- dichtstbijzijnde stations bepalen op basis van coördinaten
- qg ophalen voor een periode
- GHI interpoleren op basis van de 3 dichtstbijzijnde stations

Belangrijk:
- We vragen de API in UTC aan
- Voor de rest van het model werken we met lokale tijd (Europe/Amsterdam)
- Daarna filteren we exact op de gewenste lokale periode
"""

from __future__ import annotations

import os
from math import radians, sin, cos, asin, sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

# Zoek het .env bestand expliciet in de project-root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH)

EDR_BASE_URL = "https://api.dataplatform.knmi.nl/edr/v1"
COLLECTION_ID = "10-minute-in-situ-meteorological-observations"


def _get_headers() -> Dict[str, str]:
    """
    Bouw de Authorization headers op voor KNMI.
    """
    api_key = os.getenv("KNMI_API_KEY")

    if not api_key:
        raise RuntimeError("KNMI_API_KEY ontbreekt. Zet deze in je .env bestand.")

    return {"Authorization": api_key}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Bereken de afstand tussen twee coördinaten in kilometers.
    """
    earth_radius_km = 6371.0

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    c = 2 * asin(sqrt(a))

    return earth_radius_km * c


def list_locations() -> List[Dict[str, Any]]:
    """
    Haal alle beschikbare locaties/stations op uit de KNMI EDR API.
    """
    url = f"{EDR_BASE_URL}/collections/{COLLECTION_ID}/locations"

    response = requests.get(url, headers=_get_headers(), timeout=60)
    response.raise_for_status()

    raw = response.json()

    locations: List[Dict[str, Any]] = []

    for feature in raw.get("features", []):
        station_id = feature.get("id")
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            continue

        longitude = coords[0]
        latitude = coords[1]
        name = properties.get("name", station_id)

        if station_id is None:
            continue

        locations.append(
            {
                "id": station_id,
                "name": name,
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    if not locations:
        raise RuntimeError("Geen stations gevonden via KNMI locations endpoint.")

    return locations


def find_nearest_stations(
    target_lat: float,
    target_lon: float,
    max_stations: int = 10,
) -> List[Dict[str, Any]]:
    """
    Zoek de dichtstbijzijnde stations op basis van haversine-afstand.
    """
    locations = list_locations()

    for location in locations:
        location["distance_km"] = haversine_km(
            target_lat,
            target_lon,
            location["latitude"],
            location["longitude"],
        )

    locations.sort(key=lambda item: item["distance_km"])

    return locations[:max_stations]


def coverage_collection_to_dataframe(raw: Dict[str, Any]) -> pd.DataFrame:
    """
    Parse een KNMI EDR CoverageCollection naar een pandas DataFrame.
    """
    if "coverages" not in raw or not raw["coverages"]:
        raise ValueError("EDR response bevat geen coverages.")

    coverage = raw["coverages"][0]

    time_values = coverage["domain"]["axes"]["t"]["values"]
    df = pd.DataFrame({"time": pd.to_datetime(time_values, utc=True)})

    for parameter_name, parameter_range in coverage.get("ranges", {}).items():
        df[parameter_name] = parameter_range.get("values", [])

    return df


def local_period_to_utc_strings(
    start_local: str,
    end_local: str,
    timezone_name: str = "Europe/Amsterdam",
) -> Tuple[str, str]:
    """
    Zet lokale tijdstrings om naar UTC ISO strings voor de KNMI API.
    """
    start_ts = pd.Timestamp(start_local).tz_localize(timezone_name)
    end_ts = pd.Timestamp(end_local).tz_localize(timezone_name)

    start_utc = start_ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = end_ts.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")

    return start_utc, end_utc

def build_full_time_index(
    start_local: str,
    end_local: str,
    timezone_name: str = "Europe/Amsterdam",
    freq: str = "10min",
) -> pd.DataFrame:
    """
    Bouw een volledige lokale tijdreeks op tussen start en eind.

    Voorbeelden:
    - 10min: 2025-01-01 00:00 t/m 2025-12-31 23:50
    - 1h   : 2025-01-01 00:00 t/m 2025-12-31 23:00

    Output:
    DataFrame met 1 kolom:
    - time
    """
    start_ts = pd.Timestamp(start_local).tz_localize(timezone_name)
    end_ts = pd.Timestamp(end_local).tz_localize(timezone_name)

    full_index = pd.date_range(
        start=start_ts,
        end=end_ts,
        freq=freq,
    )

    return pd.DataFrame({"time": full_index})


def ensure_full_10min_series(
    df: pd.DataFrame,
    start_local: str,
    end_local: str,
    timezone_name: str = "Europe/Amsterdam",
) -> pd.DataFrame:
    """
    Zorg dat de DataFrame een volledige 10-minuten tijdreeks bevat.

    Werkwijze:
    - Maak een volledige 10-minuten index voor de gevraagde periode
    - Merge de bestaande data daarop
    - Ontbrekende tijdstappen blijven aanwezig met NaN-waarden

    Verwacht:
    - kolom 'time' aanwezig

    Retourneert:
    - DataFrame met complete tijdas
    """
    full_time_df = build_full_time_index(
        start_local=start_local,
        end_local=end_local,
        timezone_name=timezone_name,
        freq="10min",
    )

    result = full_time_df.merge(df, on="time", how="left")
    result = result.sort_values("time").reset_index(drop=True)

    return result




def fetch_qg_for_station(
    station_id: str,
    start_local: str,
    end_local: str,
    timezone_name: str = "Europe/Amsterdam",
) -> pd.DataFrame:
    """
    Haal qg op voor één station en één lokale periode.

    Belangrijk:
    - We bouwen eerst een volledige 10-minuten tijdreeks
    - Daarna voegen we de KNMI data daarop in
    - Ontbrekende meetpunten blijven dus bestaan als lege waarden (NaN)

    Output:
    - time in lokale tijd
    - ghi
    """
    start_utc, end_utc = local_period_to_utc_strings(
        start_local=start_local,
        end_local=end_local,
        timezone_name=timezone_name,
    )

    url = f"{EDR_BASE_URL}/collections/{COLLECTION_ID}/locations/{station_id}"

    params = {
        "datetime": f"{start_utc}/{end_utc}",
        "parameter-name": "qg",
    }

    response = requests.get(
        url,
        headers=_get_headers(),
        params=params,
        timeout=60,
    )
    response.raise_for_status()

    raw = response.json()
    df = coverage_collection_to_dataframe(raw)

    if "qg" not in df.columns:
        raise ValueError(f"Station {station_id} bevat geen qg kolom.")

    df = df[["time", "qg"]].copy()
    df.rename(columns={"qg": "ghi"}, inplace=True)

    # Zet naar lokale tijd
    df["time"] = df["time"].dt.tz_convert(timezone_name)

    # Zet numeriek om, maar vul niet met 0.0
    # Ontbrekende waarden moeten leeg blijven
    df["ghi"] = pd.to_numeric(df["ghi"], errors="coerce")

    # Filter exact op de gewenste lokale kalenderperiode
    start_filter = pd.Timestamp(start_local).tz_localize(timezone_name)
    end_filter = pd.Timestamp(end_local).tz_localize(timezone_name)

    df = df[(df["time"] >= start_filter) & (df["time"] <= end_filter)].copy()
    df = df.sort_values("time").reset_index(drop=True)
    # Exact filteren op de gewenste lokale kalenderperiode
    start_filter = pd.Timestamp(start_local).tz_localize(timezone_name)
    end_filter = pd.Timestamp(end_local).tz_localize(timezone_name)

    df = df[(df["time"] >= start_filter) & (df["time"] <= end_filter)].copy()
    df = df.sort_values("time").reset_index(drop=True)

    # Zorg dat alle 10-minuten tijdstappen aanwezig zijn
    df = ensure_full_10min_series(
        df=df,
        start_local=start_local,
        end_local=end_local,
        timezone_name=timezone_name,
    )

    return df



def calculate_inverse_distance_weights(
    stations: List[Dict[str, Any]],
    power: float = 2.0,
) -> List[float]:
    """
    Bereken inverse-distance gewichten voor een lijst stations.
    """
    distances = [float(station["distance_km"]) for station in stations]

    if any(distance == 0.0 for distance in distances):
        return [1.0 if distance == 0.0 else 0.0 for distance in distances]

    raw_weights = [1.0 / (distance ** power) for distance in distances]
    weight_sum = sum(raw_weights)

    if weight_sum == 0.0:
        raise ValueError("Som van de interpolatiegewichten is 0.")

    normalized_weights = [weight / weight_sum for weight in raw_weights]

    return normalized_weights


def fetch_interpolated_ghi_from_nearest_stations(
    latitude: float,
    longitude: float,
    start_local: str,
    end_local: str,
    timezone_name: str = "Europe/Amsterdam",
    n_stations: int = 3,
    distance_power: float = 2.0,
    search_pool: int = 10,
) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """
    Interpoleer GHI op basis van de n dichtstbijzijnde stations met geldige data.
    """
    candidates = find_nearest_stations(latitude, longitude, max_stations=search_pool)

    usable_stations: List[Dict[str, Any]] = []
    station_dataframes: List[pd.DataFrame] = []
    last_error: Optional[Exception] = None

    for station in candidates:
        try:
            df_station = fetch_qg_for_station(
                station_id=station["id"],
                start_local=start_local,
                end_local=end_local,
                timezone_name=timezone_name,
            )

            if df_station.empty or not df_station["ghi"].notna().any():
                continue

            station_copy = station.copy()
            usable_stations.append(station_copy)

            station_number = len(usable_stations)
            renamed = df_station.rename(columns={"ghi": f"ghi_station_{station_number}"})

            station_dataframes.append(renamed)

            if len(usable_stations) >= n_stations:
                break

        except Exception as exc:
            last_error = exc
            continue

    if len(usable_stations) < n_stations:
        raise RuntimeError(
            f"Er zijn minder dan {n_stations} bruikbare stations gevonden. "
            f"Gevonden: {len(usable_stations)}. Laatste fout: {last_error}"
        )

    weights = calculate_inverse_distance_weights(
        usable_stations,
        power=distance_power,
    )

    for station, weight in zip(usable_stations, weights):
        station["weight"] = weight

    # Bouw eerst een volledige 10-minuten tijdreeks op
    merged_df = build_full_time_index(
        start_local=start_local,
        end_local=end_local,
        timezone_name=timezone_name,
        freq="10min",
    )

    # Voeg elk station toe met een left join
    for station_df in station_dataframes:
        merged_df = merged_df.merge(station_df, on="time", how="left")


    station_columns = [f"ghi_station_{i+1}" for i in range(len(usable_stations))]

    # Gewogen interpolatie per rij, waarbij ontbrekende stationwaarden worden overgeslagen.
    # Als op een tijdstip geen enkel station data heeft, blijft ghi leeg (NaN).
    weighted_sum = pd.Series(0.0, index=merged_df.index)
    weight_sum = pd.Series(0.0, index=merged_df.index)

    for column_name, weight in zip(station_columns, weights):
        valid_mask = merged_df[column_name].notna()

        weighted_sum.loc[valid_mask] += merged_df.loc[valid_mask, column_name] * weight
        weight_sum.loc[valid_mask] += weight

    merged_df["ghi"] = weighted_sum / weight_sum

    # Negatieve waarden afkappen, maar NaN behouden
    merged_df.loc[merged_df["ghi"] < 0, "ghi"] = 0.0
    merged_df = merged_df.sort_values("time").reset_index(drop=True)

    return usable_stations, merged_df