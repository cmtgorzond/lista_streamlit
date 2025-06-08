import streamlit as st
import pandas as pd
import requests
import time
import os
from typing import List, Dict

# Autoryzacja API
def get_api_key():
    return os.getenv('ROCKETREACH_API_KEY')

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
        try:
            all_results = []
            if not company_url.startswith(('http://', 'https://')):
                company_url = f'https://{company_url}'
            
            for title in titles:
                if not title.strip():
                    continue
                    
                payload = {
                    "query": {
                        "company_domain": [company_url],
                        "current_title": [title.strip()]
                    },
                    "start": 1,
                    "page_size": 20
                }
                
                while True:
                    response = requests.post(
                        f"{self.base_url}/api/v2/person/search",
                        headers=self.headers,
                        json=payload
                    )
                    
                    if response.status_code == 429:
                        retry_after = float(response.json().get('wait', 60))
                        st.warning(f"Przekroczono limit zapytań. Czekam {retry_after} sekund...")
                        time.sleep(retry_after)
                        continue
                        
                    if response.status_code != 200:
                        st.error(f"Błąd API: {response.status_code} - {response.text}")
                        break
                        
                    data = response.json()
                    for person in data.get('profiles', []):
                        current_title = person.get('current_title', '').lower()
                        if exclude_titles and any(excl.lower() in current_title for excl in exclude_titles if excl.strip()):
                            continue
                        all_results.append({
                            "id": person.get('id'),
                            "name": person.get('name'),
                            "title": person.get('current_title'),
                            "company": person.get('current_employer'),
                            "linkedin": person.get('linkedin_url')
                        })
                    break
                
                time.sleep(1)  # Dodatkowe opóźnienie między zapytaniami
            return all_results
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania: {str(e)}")
            return []

    # Reszta metod pozostaje bez zmian...

def main():
    st.set_page_config(page_title="🎯 Wyszukiwanie kontaktów do inwestorów", layout="wide")
    st.title("🎯 Wyszukiwanie kontaktów do inwestorów")
    
    api_key = get_api_key()
    
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        
        st.subheader("Stanowiska do wyszukiwania")
        job_titles_input = st.text_area(
            "Nazwy stanowisk (po jednej w linii)",
            "M&A\nM and A\ncorporate development\nstrategy\nstrategic\ngrowth\nmerger\nacquisition",
            height=150
        )
        job_titles = [title.strip() for title in job_titles_input.split('\n') if title.strip()]
        
        st.subheader("Stanowiska do wykluczenia")
        exclude_titles_input = st.text_area(
            "Nazwy stanowisk do wykluczenia (po jednej w linii)",
            "hr\nhuman resources\nmarketing\nsales\ntalent",
            height=100
        )
        exclude_titles = [title.strip() for title in exclude_titles_input.split('\n') if title.strip()]

    # Reszta kodu pozostaje bez zmian...

if __name__ == "__main__":
    main()
