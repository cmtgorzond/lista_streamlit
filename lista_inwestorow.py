import streamlit as st
import pandas as pd
import requests
import re
import time
from typing import List, Dict

class RocketReachAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co"
        self.headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json"
        }

    def search_people(self, company_url: str, titles: List[str], exclude_titles: List[str]) -> List[Dict]:
        """Wyszukuje osoby według pełnego URL firmy i stanowisk, bez cudzysłowów"""
        results = []
        for title in titles:
            try:
                payload = {
                    "query": {
                        "company_domain": [company_url],  # pełny URL, jak w przykładzie
                        "current_title": [title]        # bez cudzysłowów
                    },
                    "start": 1,
                    "page_size": 10
                }
                response = requests.post(
                    "https://api.rocketreach.co/api/v2/person/search",
                    headers=self.headers,
                    json=payload
                )
                if response.status_code == 201:
                    data = response.json()
                    profiles = data.get('profiles', [])
                    for profile in profiles:
                        title_lower = profile.get('current_title', '').lower()
                        if any(excl.lower() in title_lower for excl in exclude_titles):
                            continue
                        results.append({
                            "id": profile.get('id'),
                            "name": profile.get('name'),
                            "title": profile.get('current_title'),
                            "linkedin": profile.get('linkedin_url')
                        })
                time.sleep(0.5)
            except Exception as e:
                st.error(f"Błąd podczas wyszukiwania dla stanowiska '{title}': {str(e)}")
        return results

    def lookup_email(self, person_id: int) -> Dict:
        """Pobiera dane osoby, w tym zweryfikowany email"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v2/person/lookup",
                headers=self.headers,
                params={"id": person_id, "lookup_type": "standard"}
            )
            if response.status_code == 200:
                data = response.json()
                # wybierz zweryfikowany email zawodowy
                email = ''
                for e in data.get('emails', []):
                    if e.get('type') == 'professional' and e.get('smtp_valid') == 'valid':
                        email = e.get('email')
                        break
                return {
                    "email": email,
                    "linkedin": data.get('linkedin_url', '')
                }
            return {}
        except Exception as e:
            st.error(f"Błąd lookup email dla ID {person_id}: {str(e)}")
            return {}

def extract_full_url(url: str) -> str:
    """Zwraca pełny URL z protokołem"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

def main():
    st.set_page_config(page_title="🚀 RocketReach Poprawione", layout="wide")
    st.title("🚀 RocketReach Poprawione - Wyszukiwanie kontaktów")
    
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        api_key = st.text_input("API Key RocketReach", type="password")
        # Stanowiska do wyszukiwania
        titles_input = st.text_area(
            "Stanowiska do wyszukiwania (po jednej linijce)",
            "M&A\nM and A\ncorporate development\nstrategy\ngrowth",
            height=150
        )
        titles = [t.strip() for t in titles_input.split('\n') if t.strip()]
        # Stanowiska do wykluczenia
        exclude_input = st.text_area(
            "Stanowiska do wykluczenia (po jednej linijce)",
            height=100
        )
        exclude_titles = [t.strip() for t in exclude_input.split('\n') if t.strip()]

    st.header("📁 Prześlij plik CSV z URLami firm")
    uploaded_file = st.file_uploader("Wybierz plik CSV", type=['csv'])
    if uploaded_file and api_key:
        df = pd.read_csv(uploaded_file)
        urls = df.iloc[:, 0].dropna().tolist()

        if st.button("🚀 Rozpocznij wyszukiwanie"):
            api = RocketReachAPI(api_key)
            results = []
            for idx, url in enumerate(urls):
                full_url = extract_full_url(url)
                profiles = api.search_people(full_url, titles, exclude_titles)
                if not profiles:
                    results.append({
                        "URL": url,
                        "Status": "Nie znaleziono kontaktów"
                    })
                else:
                    for profile in profiles[:5]:
                        details = api.lookup_email(profile['id'])
                        results.append({
                            "URL": url,
                            "Name": profile['name'],
                            "Title": profile['title'],
                            "Email": details.get('email', ''),
                            "LinkedIn": details.get('linkedin', ''),
                            "Status": "Znaleziono"
                        })
                # Progress
                st.write(f"Przetwarzanie: {url} ({idx+1}/{len(urls)})")
            df_results = pd.DataFrame(results)
            st.dataframe(df_results)
            csv = df_results.to_csv(index=False, sep=';', encoding='utf-8-sig')
            st.download_button("📥 Pobierz wyniki", data=csv, file_name="wyniki_rocketreach.csv", mime="text/csv")
