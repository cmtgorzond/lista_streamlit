import streamlit as st
import pandas as pd
import requests
import time
import random
import io
from typing import List, Dict
from urllib.parse import urlparse

# --- Konfiguracja webhook ---
WEBHOOK_URL = "https://8721272bed36.ngrok-free.app/webhook"

class RocketReachAPI:
    def __init__(self, api_key: str, webhook_id: str):
        self.api_key = api_key
        self.webhook_id = webhook_id
        self.base_url = "https://api.rocketreach.co"
        self.headers = {"Api-Key": api_key}

    def search_people(self, company_domain: str, titles: List[str], exclude: List[str]) -> List[Dict]:
        """Wysyła jednokrotne zapytanie Person Search z batchowaniem."""
        payload = {
            "query": {
                "company_domain": [company_domain],
                "current_title": titles,
                "exclude_current_title": exclude,
                "exact_match": True
            },
            "page_size": 25,
            "fields": [
                "id","name","current_title",
                "current_employer","linkedin_url"
            ]
        }
        resp = requests.post(
            f"{self.base_url}/api/v2/person/search",
            headers=self.headers,
            json=payload
        )
        if resp.status_code in (200, 201):
            return resp.json().get("profiles", [])[:10]
        st.error(f"Search API error {resp.status_code}: {resp.text}")
        return []

    def bulk_lookup(self, ids: List[int]):
        """Wywołuje Bulk Lookup z webhook_id."""
        payload = {
            "profiles": [{"id": i} for i in ids],
            "lookup_type": "standard",
            "webhook_id": self.webhook_id
        }
        resp = requests.post(
            f"{self.base_url}/api/v2/person/bulk-lookup",
            headers=self.headers,
            json=payload
        )
        if resp.status_code == 200:
            st.info("🔔 Bulk lookup wysłany, wyniki przyjdą przez webhook")
        else:
            st.error(f"Bulk lookup error {resp.status_code}: {resp.text}")

def extract_domain(url: str) -> str:
    """Wyciąga czystą domenę z URL."""
    if not url.startswith(("http://","https://")):
        url = "https://" + url
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc

def main():
    st.set_page_config(page_title="🚀 RocketReach Webhook", layout="wide")
    st.title("🚀 Wyszukiwarka z Webhook RocketReach")

    # --- Sidebar konfiguracyjny ---
    st.sidebar.header("⚙️ Konfiguracja")
    api_key = st.sidebar.text_input("RocketReach API Key", type="password")
    webhook_id = st.sidebar.text_input("Webhook ID", help="ID wygenerowane w panelu RocketReach")
    st.sidebar.markdown(f"Webhook URL: `{WEBHOOK_URL}`")

    st.sidebar.subheader("Stanowiska do wyszukiwania")
    default_titles = [
        "M&A","M and A","corporate development","strategy",
        "strategic","growth","merger","acquisition","deal","origination"
    ]
    job_titles_input = st.sidebar.text_area(
        "", "\n".join(default_titles), height=150
    )
    job_titles = [t.strip() for t in job_titles_input.split("\n") if t.strip()]

    st.sidebar.subheader("Stanowiska do wykluczenia")
    default_exclude = ["hr","human resources","marketing","sales","talent"]
    exclude_input = st.sidebar.text_area(
        "", "\n".join(default_exclude), height=100
    )
    exclude_titles = [t.strip() for t in exclude_input.split("\n") if t.strip()]

    # --- Wczytanie listy firm ---
    st.header("📁 Wczytaj firmy")
    uploaded = st.file_uploader("Plik CSV z domenami firm (kolumna A)", type="csv")
    if not api_key or not webhook_id:
        st.warning("Podaj API Key oraz Webhook ID w panelu bocznym")
        return

    if uploaded:
        df = pd.read_csv(uploaded)
        sites = df.iloc[:,0].dropna().tolist()
        st.dataframe(df.head())

        if st.button("🚀 Rozpocznij wyszukiwanie"):
            rr = RocketReachAPI(api_key, webhook_id)
            for site in sites:
                domain = extract_domain(site)
                st.write(f"🔍 Szukam w {domain}")
                profiles = rr.search_people(domain, job_titles, exclude_titles)
                ids = [p["id"] for p in profiles[:3]]  # tylko 3 osoby
                if ids:
                    rr.bulk_lookup(ids)
                else:
                    st.write("❌ Brak profili do lookup")
                time.sleep(random.uniform(1,2))
            st.success("📬 Wszystkie zapytania wysłane. Sprawdź swój webhook.")

if __name__ == "__main__":
    main()
