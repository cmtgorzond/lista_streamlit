import streamlit as st
import pandas as pd
import requests
import time
import random
import re
from typing import List, Dict
from urllib.parse import urlparse
import io

# Konfiguracja webhook
WEBHOOK_ID = "TWÓJ_WEBHOOK_ID"  # wklej swój Webhook ID z RocketReach
WEBHOOK_URL = "https://8721272bed36.ngrok-free.app/webhook"

class RocketReachAPI:
    def __init__(self, api_key: str, webhook_id: str = None):
        self.api_key = api_key
        self.webhook_id = webhook_id
        self.base_url = "https://api.rocketreach.co"
        self.headers = {"Api-Key": api_key}

    def search_people(self, company_url: str, titles: List[str], exclude_titles: List[str]) -> List[Dict]:
        """Wyszukaj profile (bez lookup)"""
        payload = {
            "query": {
                "company_domain": [company_url],
                "current_title": titles,
                "exclude_current_title": exclude_titles,
                "exact_match": True
            },
            "page_size": 25,
            "fields": ["id","name","current_title","current_employer","linkedin_url"]
        }
        resp = requests.post(f"{self.base_url}/api/v2/person/search", headers=self.headers, json=payload)
        if resp.status_code == 201:
            return resp.json().get("profiles", [])
        st.error(f"Search API error {resp.status_code}")
        return []

    def bulk_lookup(self, ids: List[int]):
        """Wywołaj bulk lookup z webhookiem"""
        payload = {
            "profiles": [{"id": _id} for _id in ids],
            "lookup_type": "standard",
            "webhook_id": self.webhook_id
        }
        resp = requests.post(f"{self.base_url}/api/v2/person/bulk-lookup", headers=self.headers, json=payload)
        if resp.status_code == 200:
            st.info("🔔 Bulk lookup wysłany, wyniki przyjdą na webhook")
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
    st.sidebar.header("Konfiguracja")
    api_key = st.sidebar.text_input("RocketReach API Key", type="password")
    webhook_id = st.sidebar.text_input("Webhook ID", value=WEBHOOK_ID)
    st.sidebar.markdown(f"Webhook URL: `{WEBHOOK_URL}`")
    st.sidebar.subheader("Stanowiska do wyszukiwania")
    job_titles = [t.strip() for t in st.sidebar.text_area(
        "", "M&A\nM and A\ncorporate development\nstrategy\nstrategic\ngrowth\nmerger\nacquisition\ndeal\norigination",
        height=150).split("\n") if t.strip()]
    st.sidebar.subheader("Stanowiska do wykluczenia")
    exclude = [t.strip() for t in st.sidebar.text_area(
        "", "hr\nhuman resources\nmarketing\nsales\ntalent", height=100).split("\n") if t.strip()]

    st.header("📁 Wczytaj firmy")
    uploaded = st.file_uploader("", type="csv")
    if not (api_key and webhook_id):
        st.warning("Podaj API Key i Webhook ID")
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
                profiles = rr.search_people(domain, job_titles, exclude)
                ids = [p["id"] for p in profiles[:3]]  # 3 profile
                if ids:
                    rr.bulk_lookup(ids)
                else:
                    st.write("❌ Brak profili do lookup")
                time.sleep(random.uniform(1,2))
            st.success("📬 Wszystkie zapytania wysłane. Sprawdź webhook.")

if __name__=="__main__":
    main()
