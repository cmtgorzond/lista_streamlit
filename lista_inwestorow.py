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

    def search_people(self, domain: str, include_titles: List[str], exclude_titles: List[str] = None) -> Optional[Dict]:
        cleaned_domain = self._clean_domain(domain)
        if not cleaned_domain:
            st.error("Nieprawidłowy format domeny")
            return None

        if not self._validate_titles(include_titles):
            return None

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

        for attempt in range(3):
            try:
                response = requests.post(
                    f"{self.base_url}/person/search",
                    headers=self.headers,
                    json=payload,
                    timeout=10
                )
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 30))
                    time.sleep(retry_after)
                    continue
                    
                if response.status_code >= 400:
                    error_details = response.json().get('detail', 'Nieznany błąd API')
                    st.error(f"Błąd {response.status_code}: {error_details}")
                    return None
                    
                return response.json()
                
            except Exception as e:
                st.error(f"Błąd połączenia: {str(e)}")
                time.sleep(self.rate_limit_delay * (attempt + 1))
        
        return None

    @staticmethod
    def _clean_domain(url: str) -> str:
        domain = re.sub(r"https?://(www\.)?", "", url, flags=re.IGNORECASE)
        domain = re.split(r"/|\?|#", domain)[0].strip().lower()
        return re.sub(r"[^a-z0-9.-]", "", domain)

    @staticmethod
    def _validate_titles(titles: List[str]) -> bool:
        if not any(titles):
            st.error("Musisz podać przynajmniej jedno stanowisko")
            return False
        if len(titles) > 10:
            st.error("Maksymalnie 10 stanowisk w jednym zapytaniu")
            return False
        return True

def main():
    st.set_page_config(page_title="Wyszukiwarka Kontaktów", layout="wide")
    st.title("🔍 Wyszukiwarka Kontaktów B2B")
    
    with st.sidebar:
        api_key = st.text_input("Klucz API RocketReach", type="password")
        st.markdown("---")
        include_titles = st.text_input("Stanowiska do włączenia (oddziel przecinkami)", value="M&A,Strategy")
        exclude_titles = st.text_input("Stanowiska do wykluczenia (oddziel przecinkami)")
    
    if not api_key:
        st.warning("Wprowadź klucz API w panelu bocznym")
        return
        
    client = RocketReachClient(api_key)
    
    domain = st.text_input("Wprowadź domenę firmy", value="nvidia.com")
    
    if st.button("Szukaj"):
        include_list = [t.strip() for t in include_titles.split(",") if t.strip()]
        exclude_list = [t.strip() for t in exclude_titles.split(",") if t.strip()]
        
        results = client.search_people(domain, include_list, exclude_list)
        
        if results and 'profiles' in results:
            # Przetwarzanie i wyświetlanie wyników...
        else:
            st.error("Nie znaleziono kontaktów")

if __name__ == "__main__":
    main()
