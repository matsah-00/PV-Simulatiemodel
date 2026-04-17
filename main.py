"""
main.py

Dit is het startpunt van je project.

Wat dit script doet:
1. Vraagt input aan de gebruiker
2. Vraagt alleen een kalenderjaar op
3. Zet dat jaar om naar een volledige UTC tijdsreeks
4. Roept de simulatie aan
5. Print de samenvatting
6. Slaat alle tijdstappen op naar Excel met 2 tabs:
   - 10min_data
   - hourly_data
"""

from __future__ import annotations

import os
import sys
import pandas as pd

# Zorg dat de src-map importeerbaar is
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(CURRENT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from pv_sim_v2.simulation import run_pv_simulation


def ask_float(prompt_text: str) -> float:
    """
    Hulpfunctie om netjes een float op te vragen.
    """
    while True:
        try:
            return float(input(prompt_text).strip())
        except ValueError:
            print("Ongeldige invoer. Vul een numerieke waarde in.")


def ask_text(prompt_text: str) -> str:
    """
    Hulpfunctie om tekst op te vragen.
    """
    while True:
        value = input(prompt_text).strip()
        if value:
            return value
        print("Invoer mag niet leeg zijn.")


def ask_year(prompt_text: str) -> int:
    """
    Vraag een kalenderjaar op, bijvoorbeeld 2024 of 2025.
    """
    while True:
        value = input(prompt_text).strip()

        if not value.isdigit():
            print("Ongeldige invoer. Vul een jaar in zoals 2024.")
            continue

        year = int(value)

        if year < 1900 or year > 2100:
            print("Vul een geldig jaar in tussen 1900 en 2100.")
            continue

        return year


def build_year_local_range(year: int) -> tuple[str, str]:
    """
    Zet een kalenderjaar om naar een volledige lokale periode.

    Voorbeeld:
    2025 -> ("2025-01-01 00:00:00", "2025-12-31 23:59:59")
    """
    start_local = f"{year}-01-01 00:00:00"
    end_local = f"{year}-12-31 23:59:59"

    return start_local, end_local


def main() -> None:
    """
    Vraag alle inputs op en voer de simulatie uit.
    """
    print("\n--- PV SIM V2 ---\n")
    print("Voer de gevraagde waarden in.\n")
    print("Azimuth conventie:")
    print("0 = noord, 90 = oost, 180 = zuid, 270 = west\n")

    latitude = ask_float("Latitude (bijv. 52.0907): ")
    longitude = ask_float("Longitude (bijv. 5.1214): ")

    print("\nVul alleen een kalenderjaar in, bijvoorbeeld 2024 of 2025.\n")

    year = ask_year("Jaar: ")
    start_local, end_local = build_year_local_range(year)

    print(f"\nSimulatieperiode automatisch ingesteld op:")
    print(f"Start lokaal: {start_local}")
    print(f"End lokaal  : {end_local}\n")

    tilt_deg = ask_float("Tilt / hellingshoek in graden (bijv. 35): ")
    surface_azimuth_deg = ask_float("Paneel-azimuth in graden (bijv. 180 voor zuid): ")
    pr = ask_float("Performance Ratio PR (bijv. 0.82): ")
    pstc_kwp = ask_float("PSTC in kWp (bijv. 425): ")
    albedo = ask_float("Albedo (bijv. 0.20): ")

    summary, df_10min, df_hourly = run_pv_simulation(
        latitude=latitude,
        longitude=longitude,
        start_local=start_local,
        end_local=end_local,
        tilt_deg=tilt_deg,
        surface_azimuth_deg=surface_azimuth_deg,
        pr=pr,
        pstc_kwp=pstc_kwp,
        albedo=albedo,
    )

    print("\n--- RESULTAAT ---")
    print("Gebruikte stations voor interpolatie:")

    for station in summary["stations_used"]:
        print(
            f"- #{station['station_rank']} {station['station_name']} "
            f"({station['station_id']}) | afstand: {station['distance_km']} km "
            f"| gewicht: {station['weight']}"
        )

    print(f"\nTotale energie 10-min   : {summary['total_energy_kwh_10min']} kWh")
    print(f"Totale energie uurdata  : {summary['total_energy_kwh_hourly']} kWh")
    print(f"Peak PAC                : {summary['peak_pac_kw']} kW")
    print(f"Gemiddelde POA / GTI    : {summary['mean_poa_wm2']} W/m²")

    os.makedirs("output", exist_ok=True)

    output_path = os.path.join("output", f"pv_simulation_results_{year}.xlsx")

    # Excel ondersteunt geen timezone-aware datetime kolommen.
    # Daarom maken we kopieën van de dataframes en verwijderen we alleen
    # voor export de timezone-informatie uit de kolom 'time'.
    df_10min_export = df_10min.copy()
    df_hourly_export = df_hourly.copy()

    if "time" in df_10min_export.columns:
        df_10min_export["time"] = pd.to_datetime(
            df_10min_export["time"]
        ).dt.tz_localize(None)

    if "time" in df_hourly_export.columns:
        df_hourly_export["time"] = pd.to_datetime(
            df_hourly_export["time"]
        ).dt.tz_localize(None)

    # Schrijf naar Excel met meerdere tabs
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_10min_export.to_excel(writer, sheet_name="10min_data", index=False)
        df_hourly_export.to_excel(writer, sheet_name="hourly_data", index=False)

    print(f"\nExcel opgeslagen naar: {output_path}")
    print("Tabs:")
    print("- 10min_data")
    print("- hourly_data")
    print("Klaar.\n")


if __name__ == "__main__":
    main()