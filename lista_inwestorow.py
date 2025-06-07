import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="RocketReach Contact Finder", layout="wide")
st.title("🔍 RocketReach - People Search by Company Website")

# API Key (tu wpisz swój klucz)
API_KEY = "YOUR_API_KEY"

# Formularz konfiguracji
uploaded_file = st.file_uploader("📄 Wgraj plik CSV z kolumną A (strony internetowe firm)", type=["csv"])
include_keywords = st.text_area("🔎 Wpisz słowa kluczowe dla stanowisk (oddziel przecinkami)", "M&A,corporate development,strategy,strategic,growth,merger")
exclude_keywords = st.text_area("🚫 Wyklucz stanowiska zawierające (oddziel przecinkami)", "")

def fetch_contacts(domain, include, exclude):
    url = "https://api.rocketreach.co/v1/api/search/person"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {
        "company_domain": domain,
        "current_employer": True,
        "page_size": 20
    }
    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        return "błąd API", []

    data = response.json().get("results", [])
    filtered = []
    for person in data:
        job_title = (person.get("current_title") or "").lower()
        if any(keyword.lower() in job_title for keyword in include) and not any(bad.lower() in job_title for bad in exclude):
            filtered.append({
                "name": person.get("name"),
                "title": person.get("current_title"),
                "email": person.get("email", "brak"),
                "linkedin": person.get("linkedin_url", "brak")
            })
        if len(filtered) == 5:
            break

    return None, filtered

if uploaded_file:
    df_input = pd.read_csv(uploaded_file)
    domains = df_input.iloc[:, 0].dropna().tolist()

    include = [k.strip().lower() for k in include_keywords.split(",")]
    exclude = [k.strip().lower() for k in exclude_keywords.split(",")]

    output_rows = []
    with st.spinner("🔄 Przetwarzanie danych..."):
        for domain in domains:
            error, contacts = fetch_contacts(domain, include, exclude)
            row = {"domain": domain}
            if error:
                row["status"] = error
            elif not contacts:
                row["status"] = "nie znaleziono kontaktów"
            else:
                row["status"] = "OK"
                for i, c in enumerate(contacts, start=1):
                    row[f"name_{i}"] = c["name"]
                    row[f"title_{i}"] = c["title"]
                    row[f"email_{i}"] = c["email"]
                    row[f"linkedin_{i}"] = c["linkedin"]
            output_rows.append(row)

    df_result = pd.DataFrame(output_rows)
    st.success("✅ Gotowe!")
    st.dataframe(df_result)

    csv = df_result.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Pobierz wyniki jako CSV", data=csv, file_name="wyniki.csv", mime="text/csv")
