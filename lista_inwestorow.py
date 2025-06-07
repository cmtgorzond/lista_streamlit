import streamlit as st
import requests
import pandas as pd
import re
import time
from typing import List, Dict

class RocketReachClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co/api/v2"
        self.headers = {
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"  # Dodaj ten nagłówek
        }

    def search_people(self, domain: str, include_titles: List[str], exclude_titles: List[str] = None) -> Dict:
        """Poprawiona struktura zapytania zgodna z dokumentacją API"""
        cleaned_domain = self.clean_domain(domain)
        
        if not cleaned_domain:
            st.error("Nieprawidłowy format domeny")
            return {}

        payload = {
            "query": {
                "company_domain": cleaned_domain,
                "current_title": {
                    "include": include_titles,
                    "exclude": exclude_titles or []
                }
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
            
            if response.status_code == 400:
                error_details = response.json().get('detail', 'Nieznany błąd')
                st.error(f"Błąd API: {error_details}")
                return {}

            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            st.error(f"Błąd połączenia: {str(e)}")
            return {}

    @staticmethod
    def clean_domain(url: str) -> str:
        """Zaawansowane czyszczenie domeny"""
        if not url:
            return ""
            
        # Usuń protokół i ścieżki
        domain = re.sub(r"https?://", "", url, flags=re.IGNORECASE)
        domain = re.split(r"/|\?|#", domain)[0]
        
        # Usuń www i subdomeny
        domain = re.sub(r"^www\.", "", domain)
        
        # Usuń białe znaki i konwertuj na małe litery
        return domain.strip().lower()

def main():
    st.set_page_config(page_title="Wyszukiwarka Kontaktów", layout="wide")
    st.title("🔍 Wyszukiwarka Kontaktów B2B")
    
    with st.sidebar:
        api_key = st.text_input("Klucz API RocketReach", type="password")
        st.markdown("---")
        include_titles = st.text_input("Stanowiska do włączenia (oddziel przecinkami)", value="M&A,Strategy")
    
    if not api_key:
        st.warning("Wprowadź klucz API w panelu bocznym")
        return
        
    client = RocketReachClient(api_key)
    
    domain = st.text_input("Wprowadź domenę firmy", value="nvidia.com")
    
    if st.button("Szukaj"):
        title_list = [t.strip() for t in include_titles.split(",") if t.strip()]
        
        if not title_list:
            st.error("Musisz podać przynajmniej jedno stanowisko")
            return
            
        results = client.search_people(domain, title_list)
        
        if not results.get('profiles'):
            st.error("Nie znaleziono kontaktów")
            return
            
        data = []
        for profile in results['profiles']:
            row = {
                "Imię i nazwisko": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
                "Stanowisko": profile.get('current_title', ''),
                "Email": next((e['email'] for e in profile.get('emails', []) if e.get('type') == 'work'), ''),
                "LinkedIn": next((l['url'] for l in profile.get('links', []) if 'linkedin' in l.get('type', '').lower()), '')
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "LinkedIn": st.column_config.LinkColumn("LinkedIn")
            }
        )

if __name__ == "__main__":
    main()
