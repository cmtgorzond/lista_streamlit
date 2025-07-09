import streamlit as st
import pandas as pd
import requests
import time
import random
import io
from typing import List, Dict
from urllib.parse import urlparse

# --- Konfiguracja Webhook ---
WEBHOOK_URL = "https://8721272bed36.ngrok-free.app/webhook"
WEBHOOK_ID  = "TWÓJ_WEBHOOK_ID"  # wklej swój Webhook ID z RocketReach

class RocketReachAPI:
    def __init__(self, api_key: str, webhook_id: str):
        self.api_key = api_key
        self.webhook_id = webhook_id
        self.base_url = "https://api.rocketreach.co"
        self.headers = {"Api-Key": api_key}

    def search_people(self, domain: str, titles: List[str], exclude: List[str]) -> List[Dict]:
        payload = {
            "query": {
                "company_domain": [domain],
                "current_title": titles,
                "exclude_current_title": exclude,
                "exact_match": True
            },
            "page_size": 25,
            "fields": ["id","name","current_title","current_employer","linkedin_url"]
        }
        resp = requests.post(f"{self.base_url}/api/v2/person/search",
                             headers=self.headers, json=payload)
        if resp.status_code in (200,201):
            return resp.json().get("profiles", [])[:10]
        st.error(f"Search API error {resp.status_code}: {resp.text}")
        return []

    def bulk_lookup(self, ids: List[int]):
        payload = {
            "profiles": [{"id": i} for i in ids],
            "lookup_type": "standard",
            "webhook_id": self.webhook_id
        }
        resp = requests.post(f"{self.base_url}/api/v2/person/bulk-lookup",
                             headers=self.headers, json=payload)
        if resp.status_code == 200:
            st.info("🔔 Bulk lookup wysłany, wyniki przyjdą przez webhook")
        else:
            st.error(f"Bulk lookup error {resp.status_code}: {resp.text}")

def extract_domain(url: str) -> str:
    if not url.startswith(("http://","https://")):
        url = "https://" + url
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h

def main():
    st.set_page_config(page_title="🚀 RocketReach Webhook", layout="wide")
    st.title("🚀 Wyszukiwarka z Webhook RocketReach")

    st.sidebar.header("⚙️ Konfiguracja")
    api_key    = st.sidebar.text_input("RocketReach API Key", type="password")
    webhook_id = st.sidebar.text_input("Webhook ID", value=WEBHOOK_ID)
    st.sidebar.markdown(f"Webhook URL: `{WEBHOOK_URL}`")

    st.sidebar.subheader("Stanowiska do wyszukiwania")
    default_titles = [
        "M&A","M and A","corporate development","strategy",
        "strategic","growth","merger","acquisition","deal","origination"
    ]
    titles_input = st.sidebar.text_area(
        "", "\n".join(default_titles), height=150
    )
    job_titles = [t.strip() for t in titles_input.split("\n") if t.strip()]

    st.sidebar.subheader("Stanowiska do wykluczenia")
    default_exclude = ["hr","human resources","marketing","sales","talent"]
    exclude_input = st.sidebar.text_area(
        "", "\n".join(default_exclude), height=100
    )
    exclude_titles = [t.strip() for t in exclude_input.split("\n") if t.strip()]

    st.header("📊 Wprowadzanie domen")
    data_source = st.radio("Wybierz sposób wprowadzania domen:", ["Upload pliku CSV", "Wpisz domenę ręcznie"])
    websites = []

    if data_source == "Upload pliku CSV":
        uploaded = st.file_uploader("Plik CSV z domenami firm (kolumna A)", type="csv")
        if uploaded:
            df = pd.read_csv(uploaded)
            websites = df.iloc[:,0].dropna().tolist()
            st.dataframe(df.head())
    else:
        manual = st.text_input("Wpisz domenę firmy", placeholder="example.com")
        if manual.strip():
            websites = [manual.strip()]

    if not api_key or not webhook_id:
        st.warning("Podaj API Key oraz Webhook ID w panelu bocznym")
        return

    if websites and st.button("🚀 Rozpocznij wyszukiwanie"):
        rr = RocketReachAPI(api_key, webhook_id)
        for site in websites:
            domain = extract_domain(site)
            st.write(f"🔍 Szukam w {domain}")
            profiles = rr.search_people(domain, job_titles, exclude_titles)
            # wybierz pierwsze 5
            ids = [p["id"] for p in profiles[:5]]
            if ids:
                rr.bulk_lookup(ids)
            else:
                st.write("❌ Brak profili do lookup")
            time.sleep(random.uniform(1,2))
        st.success("📬 Wszystkie zapytania wysłane. Sprawdź webhook.")

if __name__=="__main__":
    main()
