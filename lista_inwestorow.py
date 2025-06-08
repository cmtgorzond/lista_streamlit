import streamlit as st
import requests
import pandas as pd
import re
import time
from typing import List, Dict, Optional

class RocketReachClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co/api/v2"
        self.headers = {
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.rate_limit_delay = 1.5

    def search_people(self, domain: str, titles: List[str]) -> Optional[Dict]:
        """Wyszukuje profile osób zgodnie z dokumentacją Search API"""
        cleaned_domain = self._clean_domain(domain)
        payload = {
            "query": {
                "company_domain": cleaned_domain,
                "current_title": titles
            },
            "start": 1,
            "page_size": 5
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/person/search",
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as errh:
            st.error(f"Błąd Search API: {errh}")
            return None

    def lookup_person(self, profile_id: int) -> Optional[Dict]:
        """Pobiera szczegóły kontaktu zgodnie z dokumentacją Lookup API"""
        try:
            response = requests.get(
                f"{self.base_url}/person/lookup?id={profile_id}",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as errh:
            st.error(f"Błąd Lookup API: {errh}")
            return None

    @staticmethod
    def _clean_domain(url: str) -> str:
        """Czyści format domeny do wymagań API"""
        return re.sub(r"https?://(www\.)?", "", url).split('/')[0].strip().lower()

def main():
    st.set_page_config(page_title="🏢 Zaawansowana Wyszukiwarka Kontaktów", layout="wide")
    st.title("🔍 Wyszukiwarka Kontaktów B2B")
    
    with st.sidebar:
        api_key = st.text_input("🔑 Klucz API RocketReach", type="password")
        st.markdown("---")
        titles = st.text_input("Stanowiska (oddziel przecinkami)", value="M&A,Corporate Development,Strategy")
    
    if not api_key:
        st.warning("⚠️ Wprowadź klucz API w panelu bocznym")
        return
        
    client = RocketReachClient(api_key)
    
    domain = st.text_input("🌐 Wprowadź domenę firmy", value="nvidia.com")
    
    if st.button("🔍 Wyszukaj kontakty"):
        title_list = [t.strip() for t in titles.split(",") if t.strip()]
        
        if not title_list:
            st.error("Musisz podać przynajmniej jedno stanowisko")
            return
            
        start_time = time.time()
        
        # Etap 1: Wyszukiwanie profili
        search_results = client.search_people(domain, title_list)
        
        if not search_results or 'profiles' not in search_results:
            st.error("Nie znaleziono profilów")
            return
            
        profiles = search_results['profiles']
        st.success(f"Znaleziono {len(profiles)} profili, rozpoczynam pobieranie kontaktów...")
        
        # Etap 2: Pobieranie szczegółów kontaktowych
        results = []
        progress_bar = st.progress(0)
        
        for idx, profile in enumerate(profiles):
            profile_id = profile.get('id')
            if not profile_id:
                continue
                
            # Pobieranie danych kontaktowych
            lookup_data = client.lookup_person(profile_id)
            if lookup_data and 'person' in lookup_data:
                person = lookup_data['person']
                emails = [e['email'] for e in person.get('emails', []) if e.get('type') == 'work']
                results.append({
                    "Imię i nazwisko": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                    "Stanowisko": person.get('current_title', ''),
                    "Email": emails[0] if emails else ''
                })
            
            progress_bar.progress((idx + 1) / len(profiles))
            time.sleep(client.rate_limit_delay)
        
        progress_bar.empty()
        
        # Formatowanie wyników
        if results:
            df = pd.DataFrame(results)
            st.dataframe(
                df,
                use_container_width=True,
                column_config={
                    "Email": st.column_config.TextColumn("Email", help="Zweryfikowany email służbowy")
                }
            )
            
            csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
            st.download_button(
                label="💾 Pobierz wyniki jako CSV",
                data=csv,
                file_name=f"kontakty_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
        else:
            st.error("Nie znaleziono kontaktów z adresami email")

if __name__ == "__main__":
    main()
