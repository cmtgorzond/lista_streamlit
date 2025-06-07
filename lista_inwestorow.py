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
            "accept": "application/json",
            "content-type": "application/json",
            "Api-Key": self.api_key
        }

    def search_people(self, domain: str, titles: List[str]) -> Dict:
        """Wysyła zapytanie zgodne z dokumentacją RocketReach"""
        cleaned_domain = self.clean_domain(domain)
        
        payload = {
            "query": {
                "company_domain": cleaned_domain,
                "current_title": {
                    "include": titles
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
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as errh:
            st.error(f"Błąd HTTP {response.status_code}: {response.text}")
            return {}
        except Exception as e:
            st.error(f"Błąd połączenia: {str(e)}")
            return {}

    @staticmethod
    def clean_domain(url: str) -> str:
        """Czyści domenę do formatu wymaganego przez API"""
        return re.sub(r"https?://(www\.)?", "", url).split('/')[0].strip().lower()

def main():
    st.set_page_config(page_title="Wyszukiwarka Kontaktów", layout="wide")
    st.title("🔍 Wyszukiwarka Kontaktów B2B")
    
    # Panel konfiguracyjny
    with st.sidebar:
        api_key = st.text_input("Klucz API RocketReach", type="password")
        st.markdown("---")
        titles = st.text_input("Stanowiska (oddziel przecinkami)", value="sales,M&A")
    
    if not api_key:
        st.warning("Wprowadź klucz API w panelu bocznym")
        return
    
    client = RocketReachClient(api_key)
    
    # Główny formularz
    col1, col2 = st.columns([3, 1])
    with col1:
        domain = st.text_input("Domena firmy", value="https://www.nvidia.com/")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Szukaj", type="primary"):
            with st.spinner("Przeszukuję..."):
                start_time = time.time()
                
                # Przetwarzanie zapytania
                title_list = [t.strip() for t in titles.split(",")]
                results = client.search_people(domain, title_list)
                
                # Wyświetlanie wyników
                if results.get('profiles'):
                    data = []
                    for profile in results['profiles']:
                        row = {
                            "Imię i nazwisko": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
                            "Stanowisko": profile.get('current_title', ''),
                            "Email": next((e['email'] for e in profile.get('emails', []) if e.get('type') == 'work'), ''),
                            "LinkedIn": profile.get('linkedin_url', '')
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
                    
                    # Statystyki
                    st.success(f"Znaleziono {len(data)} wyników w {time.time()-start_time:.2f}s")
                else:
                    st.error("Nie znaleziono kontaktów")

if __name__ == "__main__":
    main()
