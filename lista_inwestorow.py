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
            "User-Agent": "StreamlitApp/1.0"
        }

    def search_people(self, domain: str, titles: List[str], excluded_titles: List[str]) -> Dict:
        """Wykonuje zapytanie wyszukiwania osób z obsługą błędów"""
        url = f"{self.base_url}/person/search"
        payload = {
            "query": {
                "company_domain": domain,
                "current_title": titles,
                "exclude_current_title": excluded_titles
            },
            "start": 1,
            "page_size": 5,
            "dedup_emails": True
        }
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as errh:
            st.error(f"Błąd HTTP: {errh}")
        except requests.exceptions.ConnectionError as errc:
            st.error(f"Błąd połączenia: {errc}")
        except requests.exceptions.Timeout as errt:
            st.error(f"Timeout: {errt}")
        except Exception as err:
            st.error(f"Inny błąd: {err}")
        return {}

def clean_domain(url: str) -> str:
    """Czyści i weryfikuje domenę"""
    domain = re.sub(r"https?://(www\.)?", "", url).split('/')[0].strip().lower()
    return re.sub(r"[^a-z0-9.-]", "", domain)

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

def search_contacts(client: RocketReachClient, domains: List[str], include: List[str], exclude: List[str]):
    """Przetwarza listę domen i wyświetla wyniki"""
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, domain in enumerate(domains):
        status_text.text(f"🔍 Przeszukuję: {domain}")
        
        cleaned_domain = clean_domain(domain)
        if not cleaned_domain:
            st.warning(f"Nieprawidłowa domena: {domain}")
            continue
            
        max_retries = 3
        for attempt in range(max_retries):
            response = client.search_people(cleaned_domain, include, exclude)
            
            if response.get('profiles'):
                processed = process_profiles(response['profiles'])
                if processed:
                    results.extend(format_results(cleaned_domain, processed))
                    break
            elif response.get('error') == 'rate_limit_exceeded':
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            else:
                results.append({
                    "Domena": cleaned_domain,
                    "Status": "Nie znaleziono kontaktów",
                    "Szczegóły": response.get('message', 'Brak danych')
                })
                break
        else:
            results.append({
                "Domena": cleaned_domain,
                "Status": "Błąd połączenia",
                "Szczegóły": "Przekroczono limit prób"
            })
        
        progress_bar.progress((idx + 1) / len(domains))
        time.sleep(1.5)

    progress_bar.empty()
    status_text.empty()
    display_results(pd.DataFrame(results))

def format_results(domain: str, profiles: List[Dict], max_contacts: int = 5) -> List[Dict]:
    """Formatuje wyniki do struktury tabelarycznej"""
    expanded = []
    for i in range(max_contacts):
        if i < len(profiles):
            expanded.append({
                "Domena": domain,
                f"Osoba {i+1} - Imię i nazwisko": profiles[i]['name'],
                f"Osoba {i+1} - Stanowisko": profiles[i]['title'],
                f"Osoba {i+1} - Email": profiles[i]['email'],
                f"Osoba {i+1} - LinkedIn": profiles[i]['linkedin']
            })
        else:
            expanded.append({
                "Domena": domain,
                f"Osoba {i+1} - Imię i nazwisko": "",
                f"Osoba {i+1} - Stanowisko": "",
                f"Osoba {i+1} - Email": "",
                f"Osoba {i+1} - LinkedIn": ""
            })
    return expanded

def display_results(df: pd.DataFrame):
    """Wyświetla wyniki w formie tabeli"""
    st.subheader("📊 Wyniki wyszukiwania")
    
    if df.empty:
        st.info("Brak wyników do wyświetlenia")
        return
    
    df = df[df.filter(like='Osoba').ne('').any(axis=1)]
    
    if not df.empty:
        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "LinkedIn": st.column_config.LinkColumn("LinkedIn")
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
        st.info("Nie znaleziono żadnych kontaktów spełniających kryteria")

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
            help="Np.: 'M&A, M&A Analyst, Strategic Development'"
        )
        exclude_titles = st.text_input(
            "➖ Wykluczane stanowiska (oddziel przecinkami)",
            help="Np.: 'HR, Marketing, Sales'"
        )
        
        include_list = [x.strip().title() for x in include_titles.split(",") if x.strip()]
        exclude_list = [x.strip().title() for x in exclude_titles.split(",") if x.strip()]
        
        st.markdown("---")
        st.subheader("📤 Dane Wejściowe")
        input_method = st.radio("Metoda wprowadzania:", ["Plik CSV", "Ręczne wprowadzanie"])

    if not api_key:
        st.warning("⚠️ Wprowadź klucz API w panelu bocznym")
        return

    client = RocketReachClient(api_key)
    
    if input_method == "Plik CSV":
        uploaded_file = st.file_uploader("📤 Prześlij plik CSV", type=["csv"])
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file)
                if 'website' not in df.columns:
                    st.error("❌ Brak wymaganej kolumny 'website' w pliku CSV")
                    return
                domains = [clean_domain(row['website']) for _, row in df.iterrows()]
                search_contacts(client, domains, include_list, exclude_list)
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
            search_contacts(client, domains_list, include_list, exclude_list)

if __name__ == "__main__":
    main()
