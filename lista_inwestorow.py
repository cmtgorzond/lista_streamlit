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

    def search_people(self, domain: str, include_titles: List[str]) -> Dict:
        """Poprawiona struktura zapytania zgodnie z dokumentacją API"""
        # Sanityzacja domeny
        cleaned_domain = re.sub(r"https?://(www\.)?", "", domain).split('/')[0].strip().lower()
        
        payload = {
            "query": {
                "company_domain": cleaned_domain,  # Użyj poprawnego parametru
                "current_title": {
                    "include": include_titles  # Nowa struktura filtrów
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
            
            # Dodatkowe logowanie błędów
            if response.status_code != 200:
                error_details = response.json().get('detail', 'Nieznany błąd')
                st.error(f"Błąd {response.status_code}: {error_details}")
                return {}

            return response.json()
            
        except Exception as e:
            st.error(f"Błąd połączenia: {str(e)}")
            return {}

def main():
    st.set_page_config(page_title="Wyszukiwarka Kontaktów", layout="wide")
    st.title("🔍 Wyszukiwarka Kontaktów B2B")
    
    # Panel boczny
    with st.sidebar:
        api_key = st.text_input("Klucz API RocketReach", type="password")
        st.markdown("---")
        include_titles = st.text_input("Stanowiska do włączenia (oddziel przecinkami)", value="sales")
    
    if not api_key:
        st.warning("Wprowadź klucz API w panelu bocznym")
        return
        
    client = RocketReachClient(api_key)
    
    # Główny formularz
    domain = st.text_input("Wprowadź domenę firmy", value="https://www.nvidia.com/")
    
    if st.button("Szukaj"):
        # Przetwarzanie wyników
        results = client.search_people(domain, [t.strip() for t in include_titles.split(",")])
        
        if not results.get('profiles'):
            st.error("Nie znaleziono kontaktów")
            return
            
        # Przygotowanie danych
        data = []
        for profile in results['profiles']:
            row = {
                "Imię i nazwisko": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
                "Stanowisko": profile.get('current_title', ''),
                "Email": next((e['email'] for e in profile.get('emails', []) if e.get('type') == 'work'), ''),
                "LinkedIn": next((l['url'] for l in profile.get('links', []) if 'linkedin' in l.get('type', '').lower()), '')
            }
            data.append(row)
        
        # Wyświetlanie wyników
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
