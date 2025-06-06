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

    def search_people(self, domain: str, titles: List[str], excluded_titles: List[str]) -> Dict:
        """Wykonuje zapytanie wyszukiwania osób"""
        url = f"{self.base_url}/person/search"
        payload = {
            "query": {
                "company_domain": [domain],
                "current_title": titles,
                "exclude_current_title": excluded_titles
            },
            "page_size": 5,
            "start": 1
        }
        
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            st.error(f"Błąd połączenia: {str(e)}")
            return {}

def process_domain(client: RocketReachClient, domain: str, include: List[str], exclude: List[str]) -> Dict:
    """Przetwarza pojedynczą domenę i zwraca wyniki"""
    cleaned_domain = re.sub(r"https?://(www\.)?", "", domain).split('/')[0].strip()
    
    results = client.search_people(cleaned_domain, include, exclude)
    
    output = {"Domena": cleaned_domain}
    
    if results.get('profiles'):
        for i, profile in enumerate(results['profiles'][:5]):  # Ogranicz do 5 wyników
            output.update({
                f"Osoba {i+1} - Imię i nazwisko": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
                f"Osoba {i+1} - Stanowisko": profile.get('current_title', ''),
                f"Osoba {i+1} - Email": next((e['email'] for e in profile.get('emails', []) if e.get('type') == 'work'), ''),
                f"Osoba {i+1} - LinkedIn": next((l['url'] for l in profile.get('links', []) if 'linkedin' in l.get('type', '').lower()), '')
            })
    else:
        output["Status"] = "nie znaleziono kontaktów"
    
    return output

def main():
    st.set_page_config(page_title="🏢 Wyszukiwarka kontaktów", layout="wide")
    st.title("🔍 Zaawansowane wyszukiwanie kontaktów B2B")
    
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        api_key = st.text_input("🔑 Klucz API RocketReach", type="password")
        
        st.subheader("🎯 Filtry stanowisk")
        include_titles = st.text_input(
            "➕ Włączane stanowiska (oddziel przecinkami)",
            value="M&A, M and A, corporate development, strategy, strategic, growth, merger",
            help="Np.: 'M&A, corporate development'"
        )
        exclude_titles = st.text_input(
            "➖ Wykluczane stanowiska (oddziel przecinkami)",
            help="Np.: 'HR, marketing'"
        )
        
    if not api_key:
        st.warning("⚠️ Wprowadź klucz API w panelu bocznym")
        return
    
    client = RocketReachClient(api_key)
    include_list = [x.strip() for x in include_titles.split(",") if x.strip()]
    exclude_list = [x.strip() for x in exclude_titles.split(",") if x.strip()]
    
    st.subheader("📤 Wprowadź dane")
    input_method = st.radio("Wybierz metodę wprowadzania:", ["Plik CSV", "Ręczne wprowadzanie"])
    
    results = []
    
    if input_method == "Plik CSV":
        uploaded_file = st.file_uploader("Prześlij plik CSV", type=["csv"])
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            if 'website' not in df.columns:
                st.error("❌ Brak wymaganej kolumny 'website' w pliku CSV")
                return
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, row in df.iterrows():
                status_text.text(f"Przetwarzanie: {row['website']}")
                result = process_domain(client, row['website'], include_list, exclude_list)
                results.append(result)
                progress_bar.progress((idx + 1) / len(df))
                time.sleep(1)  # Rate limiting
            
            progress_bar.empty()
            status_text.empty()
    else:
        domains = st.text_area("Wprowadź domeny (jedna na linijkę)", height=150)
        if st.button("Szukaj"):
            domains_list = [d.strip() for d in domains.split('\n') if d.strip()]
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for idx, domain in enumerate(domains_list):
                status_text.text(f"Przetwarzanie: {domain}")
                result = process_domain(client, domain, include_list, exclude_list)
                results.append(result)
                progress_bar.progress((idx + 1) / len(domains_list))
                time.sleep(1)  # Rate limiting
            
            progress_bar.empty()
            status_text.empty()
    
    if results:
        df = pd.DataFrame(results)
        st.subheader("📊 Wyniki wyszukiwania")
        
        # Podświetlanie wierszy bez wyników
        def highlight_row(row):
            return ['background-color: #ffebee' if 'nie znaleziono' in str(v) else '' for v in row]
        
        st.dataframe(
            df.style.apply(highlight_row, axis=1),
            height=600,
            use_container_width=True,
            column_config={
                "LinkedIn": st.column_config.LinkColumn("LinkedIn")
            }
        )
        
        # Eksport wyników
        csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button(
            label="💾 Pobierz wyniki jako CSV",
            data=csv,
            file_name=f"kontakty_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
