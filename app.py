import dataclasses
from dataclasses import fields

import pandas as pd
import streamlit as st

from core.ev_tco import EvTcoInputs, run_ev_tco

st.set_page_config(page_title="Potentialanalyse", layout="centered")
st.title("Potentialanalyse")

def format_eur_de(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".") + " €"

def assert_inputs_match(evform_values: dict):
    expected = {f.name for f in fields(EvTcoInputs)}
    provided = set(form_values.keys())
    missing = sorted(expected - provided)
    extra = sorted(provided - expected)
    if missing or extra:
        raise ValueError(f"Input mismatch. Missing={missing} Extra={extra}")

use_case = st.sidebar.selectbox(
    "Use Case wählen",
    ["Lastgang – Maximalwert", "E-Fahrzeuge Wirtschaftlichkeit"]
)
# Freundliche Begrüßung mit Bild und Text
st.markdown("""### 🌍 **Herzlichen Glückwunsch!**
Du leistest einen wichtigen Beitrag für die **Umwelt** und deinen **Geldbeutel**!
""")

if use_case == "E-Fahrzeuge Wirtschaftlichkeit":
    st.title("E-Fahrzeuge Wirtschaftlichkeitsanalyse")

    with st.form("ev_tco_inputs"):
        # Projekt-Metadaten
        project_name = st.text_input("Projektname", value="Projekt 1")

        # Zeitliche Parameter
        col1, col2 = st.columns(2)
        with col1:
            base_year = st.number_input("Basisjahr", value=2026, min_value=2000, max_value=2100)
        with col2:
            horizon_years = st.number_input("Betrachtungshorizont (Jahre)", value=7, min_value=1, max_value=50)

        hours_per_year = st.number_input("Betriebsstunden/Jahr", value=880, min_value=0)

        # Diesel-Parameter
        st.subheader("Diesel-Parameter")
        col1, col2 = st.columns(2)
        with col1:
            diesel_l_per_h = st.number_input("Dieselverbrauch (Liter/Stunde)", value=7.5, min_value=0.0)
        with col2:
            diesel_price_eur_per_l = st.number_input("Dieselpreis (€/Liter)", value=1.8, min_value=0.0)

        # Strom-Parameter
        electricity_price_eur_per_kwh = st.number_input("Strompreis (€/kWh)", value=0.08, min_value=0.0)

        # Investition & Finanzierung
        st.subheader("Investition & Finanzierung")
        col1, col2 = st.columns(2)
        with col1:
            invest_eur = st.number_input("Investitionskosten (€)", value=60000, min_value=0)
        with col2:
            subsidy_rate = st.number_input("Förderquote (0.0–1.0)", value=0.35, min_value=0.0, max_value=1.0)

        col1, col2 = st.columns(2)
        with col1:
            resale_old_device_eur = st.number_input("Verkaufserlös Altgerät (€)", value=0, min_value=0)
        with col2:
            loan_interest = st.number_input("Kreditzins (0.0–1.0)", value=0.05, min_value=0.0, max_value=1.0)

        col1, col2 = st.columns(2)
        with col1:
            loan_years_total = st.number_input("Kreditlaufzeit (Jahre)", value=10, min_value=0, max_value=30)
        with col2:
            loan_grace_years = st.number_input("Tilgungsfreie Jahre", value=2, min_value=0, max_value=10)

        # Wirtschaftlichkeit
        discount_rate = st.number_input("Diskontierungsrate (0.0–1.0)", value=0.08, min_value=0.0, max_value=1.0)

        # Submit-Button
        submitted = st.form_submit_button("Berechnen")

    # Erstelle form_values nur, wenn das Formular abgeschickt wurde
    if submitted:
        form_values = {
            "project_name": project_name,
            "base_year": int(base_year),
            "horizon_years": int(horizon_years),
            "hours_per_year": float(hours_per_year),
            "diesel_l_per_h": float(diesel_l_per_h),
            "diesel_total_l_per_year": float(diesel_l_per_h * hours_per_year),
            "diesel_price_eur_per_l": float(diesel_price_eur_per_l),
            "electricity_kwh_per_year": float(diesel_l_per_h * hours_per_year * 3.8),  # NEU: Berechnet aus Dieselverbrauch
            "electricity_price_eur_per_kwh": float(electricity_price_eur_per_kwh),
            "invest_eur": float(invest_eur),
            "subsidy_rate": float(subsidy_rate),
            "resale_old_device_eur": float(resale_old_device_eur),
            "loan_interest": float(loan_interest),
            "loan_years_total": int(loan_years_total),
            "loan_grace_years": int(loan_grace_years),
            "discount_rate": float(discount_rate),
        }

        # Validierung und Berechnung nur ausführen, wenn form_values existiert
        try:
            assert_inputs_match(form_values)
            inputs = EvTcoInputs(**form_values)
            summary, cashflows_yearly, ledger = run_ev_tco(inputs)

            st.subheader("Ergebnisse")
            st.metric("NPV", format_eur_de(summary.npv))
            st.metric("Summe Cashflows", format_eur_de(summary.total_net_cashflow))
            st.metric("Ø jährliche Ersparnis", format_eur_de(summary.avg_yearly_savings))

            st.subheader("Cashflows (jährlich)")
            st.dataframe(cashflows_yearly, use_container_width=True)  # Korrektur: Kein __dict__

            st.subheader("Ledger")
            st.dataframe(ledger, use_container_width=True)           # Korrektur: Kein __dict__

        except Exception as e:
            st.error(str(e))


if use_case == "Lastgang – Maximalwert":
    st.title("15-Minuten-Lastgang: Maximale Last")

    st.write("CSV erwartet Spalten: **ts** (Zeitstempel) und **kwh** (kWh pro 15 Minuten).")

    uploaded = st.file_uploader("CSV hochladen", type=["csv"])

    def compute_max(df: pd.DataFrame):
        if "ts" not in df.columns or "kwh" not in df.columns:
            raise ValueError("CSV muss die Spalten 'ts' und 'kwh' enthalten.")

        ts = pd.to_datetime(df["ts"], utc=True, errors="coerce")
        kwh = pd.to_numeric(df["kwh"], errors="coerce")

        ok = ts.notna() & kwh.notna()
        if ok.sum() == 0:
            raise ValueError("Keine gültigen Zeilen gefunden. Prüfe ts/kwh Format.")

        df2 = pd.DataFrame({"ts": ts[ok], "kwh": kwh[ok]})
        idx = df2["kwh"].idxmax()

        max_kwh_15m = float(df2.loc[idx, "kwh"])
        ts_of_max = df2.loc[idx, "ts"]
        max_kw = max_kwh_15m * 4.0  # kWh/15min -> kW

        return max_kw, max_kwh_15m, ts_of_max, int(ok.sum())

    if uploaded:
        try:
            df = pd.read_csv(uploaded, sep=None, engine="python")
            df.columns = [c.strip().lower() for c in df.columns]

            st.subheader("Vorschau")
            st.dataframe(df.head(20), use_container_width=True)

            if st.button("Analysiere"):
                max_kw, max_kwh_15m, ts_of_max, n_ok = compute_max(df)

                st.success("Analyse abgeschlossen")
                st.metric("Maximale Last (kW)", f"{max_kw:.3f}")
                st.write(f"**Zeitpunkt** (UTC): {ts_of_max}")
                st.write(f"**Max kWh/15min**: {max_kwh_15m:.6f}")
                st.caption(f"Gültige Zeilen: {n_ok}")

        except Exception as e:
            st.error(str(e))
