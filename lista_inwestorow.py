import streamlit as st
import requests
import pandas as pd
import re

# 🧠 Konfiguracja API
API_KEY = "TWOJ_KLUCZ_API_TUTAJ"
API_URL = "https://api.rocketreach.co/v1/api/search/profiles"

# 🔍 Funkcja do pobierania danych
def search_people(domain, include_keywords, exclude_keywords, max_pages=5):
    people = []
    reasons_skipped = []
    titles_seen = []

    for kw in include_keywords:
        query = {
            "company_domain": [domain],
            "current_title": [kw]
        }

        start = 1
        for page in range(max_pages):
            st.text(f"📡 Zapytanie API (strona {page + 1}): {query}")
            response = requests.post(
                API_URL,
                headers={"Authorization": f"Bearer {API_KEY}"},
                json=query | {"start": start}
            )
            if response.status_code != 200:
                st.error(f"Błąd API ({response.status_code}): {response.text}")
                break

            data = response.json()
            profiles = data.get("profiles", [])
            start = data.get("pagination", {}).get("next")

            for profile in profiles:
                title = (profile.get("current_title") or "").strip().lower()
                status = profile.get("status", "")
                profile_id = profile.get("id")
                titles_seen.append(title)

                included = not include_keywords or any(inc in title for inc in include_keywords)
                excluded = any(ex in title for ex in exclude_keywords)

                if included and not excluded and status in {"complete", "progress"} and profile_id not in people:
                    people.append(profile)
                else:
                    reasons = []
                    if not included:
                        reasons.append("brak dopasowania")
                    if excluded:
                        reasons.append("exclude match")
                    if status not in {"complete", "progress"}:
                        reasons.append(f"status={status}")
                    reasons_skipped.append(f"(ID {profile_id}) '{title}' ➤ {', '.join(reasons)}")

            if not start:
                break

    return people, titles_seen, reasons_skipped

# 🖥️ UI Streamlit
st.title("🔎 Wyszukiwarka kontaktów – RocketReach")

st.markdown("📌 Wpisz słowa kluczowe (oddziel przecinkami):")
include_input = st.text_input("Słowa do filtrowania stanowisk", "sales, developer")

st.markdown("🚫 Wpisz słowa do wykluczenia (oddziel przecinkami):")
exclude_input = st.text_input("Słowa do wykluczenia", "")

domain = st.text_input("🔍 Firma (np. nvidia.com)", "nvidia.com")

max_pages = st.number_input("🔁 Ile stron API chcesz przeszukać (każda zawiera 10 wyników)?", min_value=1, max_value=50, value=5)

if st.button("🔎 Szukaj"):
    with st.spinner("Szukanie kontaktów..."):
        include_keywords = [kw.strip().lower() for kw in include_input.split(",") if kw.strip()]
        exclude_keywords = [kw.strip().lower() for kw in exclude_input.split(",") if kw.strip()]

        results, titles, skipped = search_people(domain, include_keywords, exclude_keywords, max_pages)

        if results:
            df = pd.DataFrame([{
                "Imię i nazwisko": r.get("name"),
                "Stanowisko": r.get("current_title"),
                "LinkedIn": r.get("linkedin_url"),
                "Lokalizacja": r.get("location"),
                "Email firmowy": next((e for e in r.get("teaser", {}).get("professional_emails", [])), ""),
                "Email prywatny": next((e for e in r.get("teaser", {}).get("personal_emails", [])), ""),
                "Telefon": next((p.get("number") for p in r.get("teaser", {}).get("phones", [])), "")
            } for r in results])

            st.success(f"🎯 Znaleziono {len(df)} kontaktów!")
            st.dataframe(df)
            st.download_button("💾 Pobierz jako CSV", df.to_csv(index=False).encode("utf-8"), "kontakty.csv", "text/csv")

        else:
            st.warning("⚠️ Nie znaleziono kontaktów (pasujących do filtrów)")

        if skipped:
            with st.expander("🔎 Pomińnięte profile – szczegóły"):
                st.text("\n".join(skipped))
