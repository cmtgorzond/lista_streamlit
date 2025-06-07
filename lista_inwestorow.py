import streamlit as st
import requests
import pandas as pd
import re
import time

class RocketReachClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co/api/v2"
        self.headers = {
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"  # WYMAGANE przez API
        }

    def search_people(self, domain: str, titles: List[str]) -> Dict:
        """Poprawiona struktura zapytań zgodnie z dokumentacją"""
        cleaned_domain = self._clean_domain(domain)
        
        payload = {
            "query": {
                "company_domain": cleaned_domain,  # KLUCZOWA ZMIANA
                "current_title": {
                    "include": titles  # NOWA STRUKTURA
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
        except Exception as e:
            st.error(f"Błąd API: {response.text if response else str(e)}")
            return {}

    @staticmethod
    def _clean_domain(url: str) -> str:
        """Czyści domenę do formatu wymaganego przez API"""
        return re.sub(r"https?://(www\.)?", "", url).split('/')[0].strip().lower()

def main():
    st.set_page_config(page_title="Wyszukiwarka Kontaktów", layout="wide")
    st.title("🔍 Wyszukiwarka Kontaktów B2B")
    
    # Panel boczny
    with st.sidebar:
        api_key = st.text_input("Klucz API RocketReach", type="password")
        st.markdown("---")
        titles = st.text_input("Stanowiska (oddziel przecinkami)", value="M&A,Corporate Development,Strategy")
    
    if not api_key:
        st.warning("Wprowadź klucz API w panelu bocznym")
        return
        
    client = RocketReachClient(api_key)
    
    # Główny formularz
    domain = st.text_input("Wprowadź domenę firmy", value="nvidia.com")
    
    if st.button("Szukaj"):
        title_list = [t.strip() for t in titles.split(",") if t.strip()]
        
        if not title_list:
            st.error("Musisz podać przynajmniej jedno stanowisko")
            return
            
        start_time = time.time()
        results = client.search_people(domain, title_list)
        
        if 'profiles' in results and results['profiles']:
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
            st.success(f"Znaleziono {len(data)} wyników w {time.time()-start_time:.2f}s")
        else:
            st.error("Nie znaleziono kontaktów")

if __name__ == "__main__":
    main()
