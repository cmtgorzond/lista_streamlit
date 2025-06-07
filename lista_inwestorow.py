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

    def search_people(self, domain: str, include_titles: List[str], exclude_titles: List[str] = None) -> Optional[Dict]:
        """Wyszukuje osoby z obsługą błędów i limitów API"""
        cleaned_domain = self._clean_domain(domain)
        if not cleaned_domain:
            st.error("Nieprawidłowy format domeny")
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

        try:
            response = requests.post(
                f"{self.base_url}/person/search",
                headers=self.headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 400:
                error_details = response.json().get('detail', 'Nieznany błąd API')
                st.error(f"Błąd zapytania: {error_details}")
                return None
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            st.error(f"Błąd połączenia: {str(e)}")
            return None

    @staticmethod
    def _clean_domain(url: str) -> str:
        """Czyści domenę do formatu wymaganego przez API"""
        return re.sub(r"https?://(www\.)?", "", url).split('/')[0].strip().lower()

def main():
    st.set_page_config(page_title="🏢 Zaawansowana Wyszukiwarka Kontaktów", layout="wide")
    st.title("🔍 Wyszukiwarka Kontaktów B2B")
    
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        api_key = st.text_input("🔑 Klucz API RocketReach", type="password")
        
        st.subheader("🎯 Filtry Stanowisk")
        include_titles = st.text_input(
            "➕ Włączane stanowiska (oddziel przecinkami)",
            value="M&A,Corporate Development,Strategy",
            help="Przykład: 'M&A, M&A Analyst, Strategic Development'"
        )
        exclude_titles = st.text_input(
            "➖ Wykluczane stanowisk (oddziel przecinkami)",
            help="Przykład: 'HR, Marketing, Sales'"
        )
        
        include_list = [t.strip() for t in include_titles.split(",") if t.strip()]
        exclude_list = [t.strip() for t in exclude_titles.split(",") if t.strip()]
        
        st.markdown("---")
        st.subheader("📤 Dane Wejściowe")
        input_method = st.radio("Metoda wprowadzania:", ["Plik CSV", "Ręczne wprowadzanie"])

    if not api_key:
        st.warning("⚠️ Wprowadź klucz API w panelu bocznym")
        return

    client = RocketReachClient(api_key)
    results = []

    if input_method == "Plik CSV":
        uploaded_file = st.file_uploader("📤 Prześlij plik CSV", type=["csv"])
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file)
                if 'website' not in df.columns:
                    st.error("❌ Brak wymaganej kolumny 'website' w pliku CSV")
                    return
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for idx, row in df.iterrows():
                    domain = row['website']
                    status_text.text(f"🔍 Przetwarzanie: {domain}")
                    
                    response = client.search_people(domain, include_list, exclude_list)
                    
                    if response and 'profiles' in response:
                        processed = process_profiles(response['profiles'])
                        results.append(format_results(domain, processed))
                    else:
                        results.append({"Domena": domain, "Status": "Nie znaleziono kontaktów"})
                    
                    progress_bar.progress((idx + 1) / len(df))
                    time.sleep(1.5)
                
                progress_bar.empty()
                status_text.empty()
                
            except Exception as e:
                st.error(f"Błąd przetwarzania pliku CSV: {str(e)}")
    else:
        domains = st.text_area(
            "🌐 Wprowadź domeny firm (jedna na linijkę)",
            height=150,
            placeholder="przykład.com\nfirma.pl\ninna-firma.net"
        )
        if st.button("🔍 Wyszukaj kontakty", type="primary"):
            domains_list = [d.strip() for d in domains.split('\n') if d.strip()]
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, domain in enumerate(domains_list):
                status_text.text(f"🔍 Przetwarzanie: {domain}")
                response = client.search_people(domain, include_list, exclude_list)
                
                if response and 'profiles' in response:
                    processed = process_profiles(response['profiles'])
                    results.append(format_results(domain, processed))
                else:
                    results.append({"Domena": domain, "Status": "Nie znaleziono kontaktów"})
                
                progress_bar.progress((idx + 1) / len(domains_list))
                time.sleep(1.5)
            
            progress_bar.empty()
            status_text.empty()

    if results:
        df = pd.DataFrame(results)
        st.subheader("📊 Wyniki wyszukiwania")
        
        def highlight_row(row):
            return ['background-color: #ffebee' if "Nie znaleziono" in str(v) else '' for v in row]
        
        column_config = {
            col: st.column_config.LinkColumn("LinkedIn") if "LinkedIn" in col else None
            for col in df.columns
        }
        
        st.dataframe(
            df.style.apply(highlight_row, axis=1),
            use_container_width=True,
            column_config=column_config
        )
        
        csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button(
            label="💾 Pobierz wyniki jako CSV",
            data=csv,
            file_name=f"kontakty_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

def process_profiles(profiles: List[Dict]) -> List[Dict]:
    """Przetwarza profile na strukturalne dane"""
    processed = []
    for profile in profiles:
        person = {
            'name': f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
            'title': profile.get('current_title', ''),
            'email': next((e['email'] for e in profile.get('emails', []) if e.get('type') == 'work'), ''),
            'linkedin': next((l['url'] for l in profile.get('links', []) if 'linkedin' in l.get('type', '').lower()), '')
        }
        processed.append(person)
    return processed

def format_results(domain: str, profiles: List[Dict]) -> Dict:
    """Formatuje wyniki do struktury tabelarycznej"""
    result = {"Domena": domain}
    for i in range(5):
        if i < len(profiles):
            result.update({
                f"Osoba {i+1} - Imię i nazwisko": profiles[i]['name'],
                f"Osoba {i+1} - Stanowisko": profiles[i]['title'],
                f"Osoba {i+1} - Email": profiles[i]['email'],
                f"Osoba {i+1} - LinkedIn": profiles[i]['linkedin']
            })
        else:
            result.update({
                f"Osoba {i+1} - Imię i nazwisko": "",
                f"Osoba {i+1} - Stanowisko": "",
                f"Osoba {i+1} - Email": "",
                f"Osoba {i+1} - LinkedIn": ""
            })
    return result

if __name__ == "__main__":
    main()
