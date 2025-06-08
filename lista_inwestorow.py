import streamlit as st
import pandas as pd
import requests
import time

st.title("🎯 RocketReach – Wyszukiwarka kontaktów po stronie internetowej firmy")

# Wczytywanie pliku CSV
uploaded_file = st.file_uploader("📁 Wgraj plik CSV z kolumną A jako strony internetowe firm:", type=["csv"])

# Wprowadzenie API Key
api_key = st.text_input("🔑 Wprowadź swój API Key do RocketReach:", type="password")

# Wprowadzenie słów kluczowych
include_keywords = st.text_area("📌 Wpisz słowa kluczowe do filtrowania stanowisk (oddzielone przecinkami):", 
                                value="M&A, M and A, corporate development, strategy, strategic, growth, merger")
exclude_keywords = st.text_area("🚫 Wpisz słowa kluczowe do wykluczenia (oddzielone przecinkami):")

# Przetwarzanie danych wejściowych
include_keywords = [kw.strip().lower() for kw in include_keywords.split(",") if kw.strip()]
exclude_keywords = [kw.strip().lower() for kw in exclude_keywords.split(",") if kw.strip()]

def search_people(domain, api_key, include_keywords, exclude_keywords, max_results=5):
    search_url = "https://api.rocketreach.co/api/v2/person/search"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Api-Key": api_key
    }
    people = []
    start = 1

    while len(people) < max_results:
        payload = {
            "query": {
                "company_domain": [domain],
            },
            "start": start,
            "page_size": 10
        }
        response = requests.post(search_url, json=payload, headers=headers)
        if response.status_code != 200:
            break

        data = response.json()
        profiles = data.get("profiles", [])
        if not profiles:
            break

        for profile in profiles:
            title = profile.get("current_title", "").lower()
            if any(keyword in title for keyword in include_keywords) and not any(
                ex in title for ex in exclude_keywords
            ):
                people.append(profile["id"])
                if len(people) >= max_results:
                    break

        start = data.get("pagination", {}).get("next", None)
        if not start:
            break
        time.sleep(1)  # Drobna przerwa dla bezpieczeństwa

    return people

def lookup_person(person_id, api_key):
    url = f"https://api.rocketreach.co/api/v2/person/lookup?id={person_id}&lookup_type=standard"
    headers = {
        "accept": "application/json",
        "Api-Key": api_key
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None

    data = response.json()
    name = data.get("name", "")
    title = data.get("current_title", "")
    email = data.get("recommended_professional_email", "") or data.get("current_work_email", "")
    linkedin = data.get("linkedin_url", "")
    return [name, title, email, linkedin]

if uploaded_file and api_key and include_keywords:
    df = pd.read_csv(uploaded_file)
    output_data = []

    for index, row in df.iterrows():
        website = str(row[0])
        st.write(f"🔍 Szukam kontaktów dla: {website}")
        person_ids = search_people(website, api_key, include_keywords, exclude_keywords)

        if not person_ids:
            output_data.append(["nie znaleziono kontaktów"] + [""] * 19)
        else:
            row_data = []
            for pid in person_ids[:5]:
                details = lookup_person(pid, api_key)
                if details:
                    row_data.extend(details)
                else:
                    row_data.extend(["", "", "", ""])
            while len(row_data) < 20:  # jeśli mniej niż 5 osób
                row_data.extend(["", "", "", ""])
            output_data.append(row_data)

    # Tworzenie DataFrame z wynikami
    columns = []
    for i in range(1, 6):
        columns.extend([
            f"Imię i nazwisko {i}", f"Stanowisko {i}", f"Email {i}", f"LinkedIn {i}"
        ])
    results_df = pd.DataFrame(output_data, columns=columns)
    results_df.insert(0, "Strona internetowa", df.iloc[:, 0])

    st.success("✅ Gotowe! Oto wyniki:")
    st.dataframe(results_df)

    # Eksport
    csv = results_df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Pobierz wyniki jako CSV", data=csv, file_name="wyniki_kontakty.csv", mime="text/csv")
else:
    st.info("Wgraj plik CSV, wpisz API Key oraz przynajmniej jedno słowo kluczowe.")
