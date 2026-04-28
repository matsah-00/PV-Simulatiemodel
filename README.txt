# PV Simulatiemodel - Een Python-gebaseerd simulatiemodel voor het berekenen van zonne-energieopwekking op basis van locatie, jaar en systeemparameters.

Het model gebruikt KNMI-weergegevens, fysische zonne-energie modellen en systeeminstellingen om de verwachte PV-productie te simuleren op 10-minuten en uurbasis.

---

## Functionaliteiten

- Adres of locatie invoeren
- Automatische geocoding via PDOK API
- Gebruik van dichtstbijzijnde KNMI meetstations
- Interpolatie van instralingsdata
- Berekening zonnepositie
- Conversie naar paneelvlak instraling (POA / GTI)
- Simulatie PV-opwek (PAC)
- Jaarlijkse energieproductie in kWh
- Interactieve grafieken in Streamlit
- Export naar Excel

---

## Projectstructuur

```bash
pv_sim/
│── app.py                    # Streamlit interface
│── requirements.txt
│── output/                   # Resultaten (.xlsx)
│── src/
│   └── pv_sim_v2/
│       ├── simulation.py
│       ├── knmi_client.py
│       ├── solar.py
│       ├── irradiance.py
│       └── pv_model.py

app.py                  Streamlit frontend
simulation.py           Hoofdlogica
knmi_client.py          KNMI API koppeling
solar.py                Zonnepositie
irradiance.py           GTI berekeningen
pv_model.py             Vermogensmodel
output/                 Export bestanden