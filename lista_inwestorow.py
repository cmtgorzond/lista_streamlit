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

    def search_people(self, query_params: Dict) -> Dict:
        """Wykonuje zapytanie wyszukiwania osób z obsługą błędów"""
        url = f"{self.base_url}/person/search"
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=query_params,
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
    domain = re.sub(r"https?://(www\.)?", "", url).split('/')[0].strip()
    return domain.split('?')[0]  # Usuwa parametry zapytania

def process_profiles(profiles: List[Dict]) -> List[Dict]:
    """Przetwarza profile na strukturalne dane"""
    processed = []
    for profile in profiles:
        person = {
            'name': f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
            'title': profile.get('current_title', ''),
            'email': '',
            'linkedin': ''
        }
        
        # Ekstrakcja emaili
        emails = profile.get('emails', [])
        if emails:
            work_emails = [e for e in emails if e.get('type') == 'work']
            person['email'] = work_emails[0]['email'] if work_emails else emails[0]['email']
        
        # Ekstrakcja LinkedIn
        links = profile.get('links', [])
        for link in links:
            if 'linkedin' in link.get('type', '').lower():
                person['linkedin'] = link.get('url', '')
                break
        
        processed.append(person)
    return processed

def search_contacts(client: RocketReachClient, domains: List[str], include: List[str], exclude: List[str]):
    """Przetwarza listę domen i wyświetla wyniki"""
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, domain in enumerate(domains):
        status_text.text(f"🔍 Przeszukuję: {domain}")
        
        # Budowanie zapytania zgodnie z dokumentacją API
        query = {
            "query": {
                "current_employer": domain,  # Poprawione - bez listy
                "current_title": include,
                "exclude_current_title": exclude
            },
            "start": 1,
            "page_size": 5,
            "dedup_emails": True
        }
        
        response = client.search_people(query)
        
        if response.get('profiles'):
            processed = process_profiles(response['profiles'])
            results.extend(format_results(domain, processed))
        else:
            results.append({
                "Domena": domain,
                "Status": "Nie znaleziono kontaktów",
                "Szczegóły": response.get('message', 'Brak szczegółów')
            })
        
        progress_bar.progress((idx + 1) / len(domains))
        time.sleep(1.5)  # Zwiększony limit czasu między zapytaniami

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
    
    # Filtracja pustych wierszy
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
    st.set_page_config(page_title="🏢 Advanced Contact Finder", layout="wide")
    st.title("🔍 Zaawansowane wyszukiwanie kontaktów B2B")
    
    with st.sidebar:
        st.header("⚙️ Konfiguracja wyszukiwania")
        api_key = st.text_input("🔑 Klucz API RocketReach", type="password")
        
        st.subheader("🎯 Filtry stanowisk")
        include_titles = st.text_input(
            "➕ Włączane stanowiska (oddziel przecinkami)",
            value="M&A,Corporate Development,Strategy",
            help="Np.: 'M&A, M and A, Strategic Development'"
        )
        exclude_titles = st.text_input(
            "➖ Wykluczane stanowiska (oddziel przecinkami)",
            help="Np.: 'HR, Marketing, Sales'"
        )
        
        include_list = [x.strip() for x in include_titles.split(",") if x.strip()]
        exclude_list = [x.strip() for x in exclude_titles.split(",") if x.strip()]
        
        st.markdown("---")
        st.subheader("📤 Dane wejściowe")
        input_method = st.radio("Metoda wprowadzania danych:", ["Plik CSV", "Ręczne wprowadzanie"])

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
                process_csv(client, df, include_list, exclude_list)
            except Exception as e:
                st.error(f"Błąd przetwarzania pliku CSV: {str(e)}")
    else:
        domains = st.text_area(
            "🌐 Wprowadź domeny firm (jedna na linijkę)",
            height=150,
            placeholder="przykład.com\nfirma.pl\ninna-firma.net"
        )
        if st.button("🔍 Wyszukaj kontakty", type="primary"):
            process_manual_input(client, domains, include_list, exclude_list)

def process_csv(client: RocketReachClient, df: pd.DataFrame, include: List[str], exclude: List[str]):
    """Przetwarza plik CSV i wyświetla wyniki"""
    domains = [clean_domain(row['website']) for _, row in df.iterrows()]
    search_contacts(client, domains, include, exclude)

def process_manual_input(client: RocketReachClient, domains: str, include: List[str], exclude: List[str]):
    """Przetwarza ręcznie wprowadzone domeny"""
    if domains.strip():
        domains_list = [clean_domain(d) for d in domains.split('\n') if d.strip()]
        search_contacts(client, domains_list, include, exclude)
    else:
        st.error("Wprowadź przynajmniej jedną domenę")

if __name__ == "__main__":
    main()
