from __future__ import annotations

import os
import sys

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# Zorg dat de src-map importeerbaar is
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(CURRENT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from pv_sim_v2.simulation import run_pv_simulation


def build_year_local_range(year: int) -> tuple[str, str]:
    """
    Zet een kalenderjaar om naar een volledige lokale periode.
    Voorbeeld:
    2025 -> ("2025-01-01 00:00:00", "2025-12-31 23:59:59")
    """
    start_local = f"{year}-01-01 00:00:00"
    end_local = f"{year}-12-31 23:59:59"
    return start_local, end_local


@st.cache_data(show_spinner=False)
def geocode_address_pdok(address: str) -> tuple[float, float, str]:
    """
    Zet adres om naar lat/lon + geeft het gevonden adres terug.
    """
    url = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"
    params = {
        "q": address,
        "rows": 1,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    docs = response.json()["response"]["docs"]

    if not docs:
        raise ValueError(f"Locatie niet gevonden: {address}")

    doc = docs[0]

    # Coördinaten
    point = doc["centroide_ll"]
    lon, lat = map(
        float,
        point.replace("POINT(", "").replace(")", "").split(),
    )

    # Mooie naam van adres
    # Dit veld werkt meestal goed:
    display_name = doc.get("weergavenaam") or doc.get("adres") or "Onbekend adres"

    return lat, lon, display_name


@st.cache_data(show_spinner=False)
def run_simulation_cached(
    latitude: float,
    longitude: float,
    start_local: str,
    end_local: str,
    tilt_deg: float,
    surface_azimuth_deg: float,
    pr: float,
    pstc_kwp: float,
    albedo: float,
):
    """
    Cache de simulatie zodat dezelfde run niet steeds opnieuw hoeft.
    """
    return run_pv_simulation(
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


def format_station_line(station: dict) -> str:
    """
    Maak een nette tekstregel voor een gebruikt station.
    """
    station_name = station.get("station_name", "Onbekend station")
    distance_km = station.get("distance_km", "?")
    return f"**{station_name}** — {distance_km} km"


def build_pac_chart(df: pd.DataFrame, title: str):
    """
    Bouw een interactieve PAC-grafiek.
    """
    chart_df = df.copy()

    if "time" not in chart_df.columns:
        raise ValueError("Kolom 'time' ontbreekt in de resultaten.")
    if "pac_kw" not in chart_df.columns:
        raise ValueError("Kolom 'pac_kw' ontbreekt in de resultaten.")

    chart_df["time"] = pd.to_datetime(chart_df["time"])
    chart_df = chart_df.sort_values("time")

    fig = px.line(
        chart_df,
        x="time",
        y="pac_kw",
        title=title,
        labels={
            "time": "Tijd",
            "pac_kw": "PAC [kW]",
        },
    )

    fig.update_layout(
        xaxis_title="Datum",
        yaxis_title="PAC [kW]",
        hovermode="x unified",
    )

    return fig


def main() -> None:
    st.set_page_config(page_title="PV Simulatiemodel", layout="wide")

    st.title("PV Simulatiemodel")
    st.write("Voer de parameters in en plot de PAC-opwek over een volledig jaar.")

    st.sidebar.header("Invoer")

    location = st.sidebar.text_input(
        "Adres of locatie",
        value="Amsterdam",
        placeholder="Bijv. Johan van Hasseltweg, Amsterdam",
    )

    year = st.sidebar.number_input(
        "Jaar",
        min_value=1900,
        max_value=2100,
        value=2025,
        step=1,
    )

    st.sidebar.markdown("Azimuth conventie: 0 = noord, 90 = oost, 180 = zuid, 270 = west")

    tilt_deg = st.sidebar.number_input(
        "Tilt / hellingshoek (graden)",
        value=35.0,
    )
    surface_azimuth_deg = st.sidebar.number_input(
        "Paneel-azimuth (graden)",
        value=180.0,
    )
    pr = st.sidebar.number_input(
        "Performance Ratio (PR)",
        value=0.82,
        format="%.2f",
    )
    pstc_kwp = st.sidebar.number_input(
        "PSTC (kWp)",
        value=425.0,
    )
    albedo = st.sidebar.number_input(
        "Albedo",
        value=0.20,
        format="%.2f",
    )

    data_choice = st.sidebar.radio(
        "Resolutie grafiek",
        options=["10 minuten", "uurdata"],
        index=0,
    )

    run_button = st.sidebar.button("Start simulatie", type="primary")

    start_local, end_local = build_year_local_range(int(year))

    st.markdown("### Simulatieperiode")
    st.write(f"**Start lokaal:** {start_local}")
    st.write(f"**Eind lokaal:** {end_local}")

    if not run_button:
        st.info("Vul links je locatie en parameters in en klik op **Start simulatie**.")
        return

    if not location.strip():
        st.error("Vul een adres of locatie in.")
        return

    try:
        with st.spinner("Locatie wordt omgezet naar coördinaten..."):
            latitude, longitude, found_address = geocode_address_pdok(location.strip())
    except Exception as exc:
        st.error(f"Kon locatie niet omzetten naar coördinaten: {exc}")
        return

    st.markdown("### Gevonden locatie")

    st.write(f"**Invoer:** {location}")
    st.write(f"**Gevonden adres:** {found_address}")

    if location.lower().strip() not in found_address.lower():
        st.warning("Let op: het ingevoerde adres wijkt af van wat is gevonden.")

    st.write(f"**Latitude:** {latitude:.6f}")
    st.write(f"**Longitude:** {longitude:.6f}")

    try:
        with st.spinner("Simulatie wordt uitgevoerd..."):
            summary, df_10min, df_hourly = run_simulation_cached(
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
    except Exception as exc:
        st.error(f"Er ging iets mis tijdens de simulatie: {exc}")
        return

    st.success("Simulatie klaar.")

    st.markdown("## Samenvatting")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Totale energie 10-min", f"{summary['total_energy_kwh_10min']} kWh")
    col2.metric("Totale energie uurdata", f"{summary['total_energy_kwh_hourly']} kWh")
    col3.metric("Peak PAC", f"{summary['peak_pac_kw']} kW")
    col4.metric("Gemiddelde POA / GTI", f"{summary['mean_poa_wm2']} W/m²")

    st.markdown("## Gebruikte stations")
    for station in summary["stations_used"]:
        st.markdown(f"- {format_station_line(station)}")

    st.markdown("## PAC-opwek over het jaar")

    if data_choice == "10 minuten":
        plot_df = df_10min
        plot_title = "PAC-opwek (10-minuten data)"
    else:
        plot_df = df_hourly
        plot_title = "PAC-opwek (uurdata)"

    try:
        fig = build_pac_chart(plot_df, plot_title)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as exc:
        st.error(f"Kon de grafiek niet opbouwen: {exc}")

    st.markdown("## Download resultaten")

    csv_10min = df_10min.to_csv(index=False).encode("utf-8")
    csv_hourly = df_hourly.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download 10-minuten data als CSV",
        data=csv_10min,
        file_name=f"pv_simulatie_10min_{year}.csv",
        mime="text/csv",
    )

    st.download_button(
        label="Download uurdata als CSV",
        data=csv_hourly,
        file_name=f"pv_simulatie_hourly_{year}.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
