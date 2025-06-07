import os
import pandas as pd
import requests
import streamlit as st

# Pobierz klucz API z ustawionej zmiennej środowiskowej
API_KEY = os.getenv("ROCKETREACH_API_KEY")

# Zatrzymaj aplikację, jeśli klucz nie jest dostępny
if not API_KEY:
    st.error("❌ Klucz API nie został znaleziony. Ustaw zmienną środowiskową ROCKETREACH_API_KEY w Streamlit Cloud (Advanced Settings).")
    st.stop()

# Konfiguracja aplikacji Streamlit
st.set_page_config(page_title="RocketReach Contact Finder", layout="wide")
st.title("🔍 RocketReach – Szukaj kontaktów w firmach")

# Uploader pliku CSV
uploaded_file = st.file_uploader("📄 Wgraj plik CSV (kolumna A: strony internetowe firm)", type=["csv"])

# Pola do wpisania słów kluczowych
include_keywords = st.text_area(
    "🔎 Szukaj stanowisk zawierających słowa (oddzielone przecinkami):",
    "M&A, corporate development, strategy, strategic, growth, merger"
)

exclude_keywords = st.text_area(
    "🚫 Wyklucz stanowiska zawierające słowa (oddzielone przecinkami):",
    ""
)

# Funkcja zapytania do RocketReach
def fetch_contacts(domain, include, exclude):
    url = "https://api.rocketreach.co/v1/api/search/person"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {
        "company_domain": domain,
        "current_employer": True,
        "page_size": 20
    }

    try:
        response = requests.get(url, headers=headers, params=params)
    except Exception as e:
        return "błąd połączenia", []

    if response.status_code != 200:
        return f"błąd API ({response.status_code})", []

    data = response.json().get("results", [])
    filtered = []

    for person in data:
        title = (person.get("current_title") or "").lower()
        if any(key in title for key in include) and not any(ex in title for ex in exclude):
            filtered.append({
                "name": person.get("name", "brak"),
                "title": person.get("current_title", "brak"),
                "email": person.get("email", "brak"),
                "linkedin": person.get("linkedin_url", "brak")
            })
        if len(filtered) == 5:
            break

    return None, filtered

# Jeśli plik został wgrany
if uploaded_file:
    df_input = pd.read_csv(uploaded_file)
    domains = df_input.iloc[:, 0].dropna().tolist()

    # Przetwarzanie słów kluczowych
    include = [k.strip().lower() for k in include_keywords.split(",") if k.strip()]
    exclude = [k.strip().lower() for k in exclude_keywords.split(",") if k.strip()]

    output_rows = []

    with st.spinner("🔄 Szukanie kontaktów..."):
        for domain in domains:
            error, contacts = fetch_contacts(domain, include, exclude)
            row = {"strona_firmy": domain}

            if error:
                row["status"] = error
            elif not contacts:
                row["status"] = "nie znaleziono kontaktów"
            else:
                row["status"] = "OK"
                for i, c in enumerate(contacts, start=1):
                    row[f"imię i nazwisko {i}"] = c["name"]
                    row[f"stanowisko {i}"] = c["title"]
                    row[f"email {i}"] = c["email"]
                    row[f"linkedin {i}"] = c["linkedin"]
            output_rows.append(row)

    # Wyświetlanie wyników
    df_result = pd.DataFrame(output_rows)
    st.success("✅ Wyszukiwanie zakończone!")
    st.dataframe(df_result)

    # Przycisk do pobrania
    csv = df_result.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Pobierz wyniki jako CSV", data=csv, file_name="wyniki_kontaktów.csv", mime="text/csv")
