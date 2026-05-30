"""
Inflationsrechner – Streamlit-Version
Lädt den Verbraucherpreisindex (VPI) für Deutschland direkt aus der
GENESIS-Datenbank des Statistischen Bundesamts (Destatis).

Datenquelle: Tabelle 61111-0002 (VPI Monatswerte, Basis 2020=100)
"""

import requests
import pandas as pd
import streamlit as st
from io import StringIO, BytesIO
import zipfile


# =====================================================================
# Daten laden (mit Cache, damit die API nicht bei jedem Klick gefragt wird)
# =====================================================================
@st.cache_data(ttl=60 * 60 * 24)  # Cache 24 Stunden
def load_cpi_data() -> pd.DataFrame:
    """Lädt CPI-Daten aus der GENESIS-API und bereitet sie auf."""

    token = st.secrets["GENESIS_TOKEN"]
    BASE_URL = "https://www-genesis.destatis.de/genesisWS/rest/2020/"

    response = requests.post(
        BASE_URL + "data/tablefile",
        headers={"username": token},
        data={
            "name": "61111-0002",
            "area": "all",
            "compress": "false",
            "transpose": "false",
            "format": "ffcsv",
            "language": "de",
            "startyear": "1991",
            "endyear": "2100",
        },
    )
    response.raise_for_status()

    # Antwort ist ein ZIP-Archiv – darin liegt eine CSV-Datei
    with zipfile.ZipFile(BytesIO(response.content)) as z:
        csv_name = z.namelist()[0]
        with z.open(csv_name) as f:
            csv_text = f.read().decode("utf-8")

    raw = pd.read_csv(StringIO(csv_text), sep=";", decimal=",")

    # Nur die Zeilen mit dem CPI-Indexwert (nicht die Veränderungsraten)
    cpi_rows = raw[raw["value_unit"] == "2020=100"].copy()

    monate_de = {
        "Januar": 1, "Februar": 2, "März": 3, "April": 4,
        "Mai": 5, "Juni": 6, "Juli": 7, "August": 8,
        "September": 9, "Oktober": 10, "November": 11, "Dezember": 12,
    }

    df = pd.DataFrame({
        "Jahr":  cpi_rows["time"].astype(int).values,
        "Monat": cpi_rows["1_variable_attribute_label"].map(monate_de).values,
    })

    # Komma → Punkt, dann in Zahl umwandeln
    values_str = cpi_rows["value"].astype(str).str.replace(",", ".", regex=False)
    df["CPI_Monat"] = pd.to_numeric(values_str, errors="coerce").values

    df = df.sort_values(["Jahr", "Monat"]).reset_index(drop=True)
    df["Monatliche Inflation"] = (df["CPI_Monat"] / df["CPI_Monat"].shift(1) - 1).round(3)

    return df


def get_cpi(df: pd.DataFrame, jahr: int, monat: int) -> float | None:
    """Hilfsfunktion: gibt den CPI für ein bestimmtes Jahr/Monat zurück, oder None."""
    match = df[(df["Jahr"] == jahr) & (df["Monat"] == monat)]
    if match.empty or pd.isna(match["CPI_Monat"].iloc[0]):
        return None
    return float(match["CPI_Monat"].iloc[0])


# =====================================================================
# UI
# =====================================================================
st.title("📈 Inflationsrechner")
st.caption("Datenquelle: Statistisches Bundesamt (Destatis), GENESIS-Online")

with st.spinner("Lade CPI-Daten von der GENESIS-Datenbank ..."):
    df = load_cpi_data()

# Nur Zeilen mit echtem CPI-Wert für die Bereichsgrenzen
valid = df.dropna(subset=["CPI_Monat"])
min_year = int(valid["Jahr"].min())
max_year = int(valid["Jahr"].max())
min_month_in_max = int(valid[valid["Jahr"] == max_year]["Monat"].max())

st.info(f"Daten verfügbar von 01/{min_year} bis "
        f"{min_month_in_max:02d}/{max_year}.")


# ---------------------------------------------------------------------
# Block 1: Inflationsbereinigte Berechnung (vorwärts UND rückwärts)
# ---------------------------------------------------------------------

# How-To: ausklappbare Erklärung der App
with st.expander("How-To"):
    st.write(
        "Dieser Rechner nutzt den Verbraucherpreisindex (VPI) des Statistischen "
        "Bundesamts, um die Kaufkraft von Geldbeträgen über die Zeit zu vergleichen.\n\n"
        "**Wert von Geldbeträgen über die Zeit:**\n"
        "Gib unter *Von ...* das Ausgangs-Jahr und den Monat ein und unter *... nach* "
        "das Ziel-Jahr und den Monat. Trage dann den Betrag ein. Die App berechnet, "
        "welchen Wert dieser Betrag zum Zielzeitpunkt hat.\n\n"
        "Du kannst sowohl **vorwärts** rechnen (z.B. was 100 € von 1995 heute wert sind) "
        "als auch **rückwärts** (z.B. welche Kaufkraft 100 € von heute im Jahr 1995 hatten).\n\n"
        "**Gehaltsentwicklung vs. Inflation:**\n"
        "Hier kannst du vergleichen, ob ein Betrag (z.B. dein Gehalt) stärker oder "
        "schwächer gestiegen ist als die Inflation – also ob die reale Kaufkraft "
        "gewachsen ist oder gesunken."
    )

st.header("Wert von Geldbeträgen über die Zeit")
st.write("Berechne was ein Geldbetrag in einem gewissen Jahr und Monat in einem anderen "
         "Jahr und Monat wert ist. Entweder rückblickend in die Vergangenheit, oder "
         "nach vorausschauend in die Zukunft. (Siehe How-To)")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Von ...")
    start_year  = st.number_input("Jahr",  min_value=min_year, max_value=max_year,
                                  value=min_year, key="start_year")
    start_month = st.number_input("Monat (1–12)", min_value=1, max_value=12,
                                  value=1, key="start_month")

with col2:
    st.subheader("... nach")
    end_year  = st.number_input("Jahr",  min_value=min_year, max_value=max_year,
                                value=max_year, key="end_year")
    end_month = st.number_input("Monat (1–12)", min_value=1, max_value=12,
                                value=min_month_in_max, key="end_month")

value = st.number_input("Betrag (€)", min_value=0.0, value=100.0, step=10.0)

# Validierungen
if (start_year, start_month) == (end_year, end_month):
    st.error("Start- und Enddatum dürfen nicht identisch sein.")
else:
    cpi_start_user = get_cpi(df, start_year, start_month)
    cpi_end_user   = get_cpi(df, end_year,   end_month)

    if cpi_start_user is None or cpi_end_user is None:
        st.warning("Für das gewählte Start- oder Enddatum liegen keine CPI-Daten vor.")
    else:
        cumulative_factor = cpi_end_user / cpi_start_user
        final_value = value * cumulative_factor

        # Erkennen ob vorwärts oder rückwärts gerechnet wurde
        richtung = "entspricht" if (end_year, end_month) > (start_year, start_month) \
                  else "hatte den Kaufkraft-Wert von"

        st.success(
            f"💶 Der Wert von **{value:.2f} €** aus {start_month:02d}/{start_year} "
            f"{richtung} **{final_value:.2f} €** in {end_month:02d}/{end_year}.  \n"
            f"Inflationsfaktor: **{cumulative_factor:.4f}**"
        )

        # CPI-Verlauf für den gewählten Zeitraum als Chart
        st.subheader("Entwicklung des Verbraucherpreisindex, also der Inflation")
        st.write("Das folgende Bild zeigt, wie sich der Verbraucherpreisindex "
                 "(2020 = 100 €) über die Zeit entwickelt hat. Eine starke Steigung "
                 "zeigt Phasen, in denen die Inflation hoch war.")

        cs, ce = sorted([(start_year, start_month), (end_year, end_month)])
        chart_df = df[
            df.apply(lambda r: cs <= (r["Jahr"], r["Monat"]) <= ce, axis=1)
        ].copy()
        chart_df["Datum"] = pd.to_datetime(
            chart_df["Jahr"].astype(str) + "-" + chart_df["Monat"].astype(str).str.zfill(2)
        )
        st.line_chart(chart_df.set_index("Datum")["CPI_Monat"])


# ---------------------------------------------------------------------
# Block 2: Gehaltsentwicklung vs. Inflation
# ---------------------------------------------------------------------
st.divider()
st.header("Gehaltsentwicklung vs. Inflation")
st.write("Vergleiche wie sich gewisse Geldbeträge, wie z.B. das Monatsgehalt oder "
         "auch Nebenkosten, im Vergleich zur Inflation entwickelt haben.")

col3, col4 = st.columns(2)

with col3:
    st.subheader("Damals")
    sy_c = st.number_input("Jahr",  min_value=min_year, max_value=max_year,
                           value=min_year, key="sy_c")
    sm_c = st.number_input("Monat (1–12)", min_value=1, max_value=12,
                           value=1, key="sm_c")
    value_compare = st.number_input("Damaliges Gehalt (€)",
                                    min_value=0.0, value=2500.0, step=100.0)

with col4:
    st.subheader("Heute")
    ey_c = st.number_input("Jahr",  min_value=min_year, max_value=max_year,
                           value=max_year, key="ey_c")
    em_c = st.number_input("Monat (1–12)", min_value=1, max_value=12,
                           value=min_month_in_max, key="em_c")
    value_today   = st.number_input("Heutiges Gehalt (€)",
                                    min_value=0.0, value=3500.0, step=100.0)

if (ey_c, em_c) <= (sy_c, sm_c):
    st.error("Das Enddatum muss nach dem Startdatum liegen.")
elif value_compare == 0:
    st.error("Das damalige Gehalt darf nicht 0 sein.")
else:
    cpi_start_c = get_cpi(df, sy_c, sm_c)
    cpi_end_c   = get_cpi(df, ey_c, em_c)

    if cpi_start_c is None or cpi_end_c is None:
        st.warning("Für das gewählte Start- oder Enddatum liegen keine CPI-Daten vor.")
    else:
        expected_value     = value_compare * (cpi_end_c / cpi_start_c)
        nominal_growth_pct = (value_today / value_compare - 1) * 100
        inflation_pct      = (cpi_end_c / cpi_start_c - 1) * 100
        real_growth_pct    = (value_today / expected_value - 1) * 100

        # Drei Metriken nebeneinander
        m1, m2, m3 = st.columns(3)
        m1.metric("Nominale Gehaltssteigerung", f"{nominal_growth_pct:+.2f} %")
        m2.metric("Inflation im Zeitraum",      f"{inflation_pct:+.2f} %")
        m3.metric("Reale Veränderung",          f"{real_growth_pct:+.2f} %")

        if real_growth_pct >= 0:
            st.success(
                f"✅ Dein Gehalt ist real um **{real_growth_pct:+.2f} %** gewachsen.  \n"
                f"Inflationsbereinigt müsste dein damaliges Gehalt heute "
                f"**{expected_value:.2f} €** sein – tatsächlich verdienst du **{value_today:.2f} €**."
            )
        else:
            st.warning(
                f"⚠️ Dein Gehalt hat real um **{real_growth_pct:+.2f} %** an Kaufkraft verloren.  \n"
                f"Um die Kaufkraft zu halten, müsste dein heutiges Gehalt "
                f"**{expected_value:.2f} €** sein."
            )