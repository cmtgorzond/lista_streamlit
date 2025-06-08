import streamlit as st
import pandas as pd
import requests
import time
import re
from typing import List, Dict, Optional, Tuple

class RocketReachAPI:
    """Klasa do obsługi RocketReach API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co"
        self.headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json"
        }
    
    def search_people_by_company(self, company_domain: str, job_titles: List[str], 
                                exclude_titles: List[str] = None) -> List[Dict]:
        """Wyszukuje osoby w firmie według stanowisk"""
        try:
            # Wyciągnij nazwę firmy z domeny
            company_name = company_domain.replace('www.', '').replace('.com', '').replace('.pl', '').replace('.org', '')
            
            all_results = []
            
            for title in job_titles:
                # Wyszukaj osoby dla każdego stanowiska
                search_params = {
                    "current_employer": [company_name],
                    "current_title": [title],
                    "size": 10  # Maksymalnie 10 wyników na stanowisko
                }
                
                response = requests.post(
                    f"{self.base_url}/api/v2/person/search",
                    headers=self.headers,
                    json=search_params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'people' in data:
                        for person in data['people']:
                            # Sprawdź czy stanowisko nie jest wykluczonym
                            if exclude_titles and any(excl.lower() in person.get('current_title', '').lower() 
                                                    for excl in exclude_titles):
                                continue
                            all_results.append(person)
                
                # Dodaj opóźnienie między zapytaniami
                time.sleep(0.5)
            
            return all_results[:5]  # Maksymalnie 5 osób
            
        except Exception as e:
            st.error(f"Błąd podczas wyszukiwania osób: {str(e)}")
            return []
    
    def lookup_person_details(self, person_data: Dict) -> Dict:
        """Pobiera szczegółowe informacje o osobie"""
        try:
            lookup_params = {}
            
            # Użyj LinkedIn URL jeśli dostępny
            if 'linkedin_url' in person_data and person_data['linkedin_url']:
                lookup_params['linkedin_url'] = person_data['linkedin_url']
            # W przeciwnym razie użyj imienia i firmy
            elif 'name' in person_data and 'current_employer' in person_data:
                lookup_params['name'] = person_data['name']
                lookup_params['current_employer'] = person_data['current_employer']
            else:
                return person_data  # Zwróć oryginalne dane jeśli brak wystarczających informacji
            
            response = requests.get(
                f"{self.base_url}/api/v2/person/lookup",
                headers=self.headers,
                params=lookup_params
            )
            
            if response.status_code == 200:
                detailed_data = response.json()
                return detailed_data
            else:
                return person_data
                
        except Exception as e:
            st.error(f"Błąd podczas pobierania szczegółów osoby: {str(e)}")
            return person_data

def extract_domain(url: str) -> str:
    """Wyciąga domenę z URL"""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    import re
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return match.group(1) if match else url

def main():
    st.set_page_config(
        page_title="RocketReach Contact Finder",
        page_icon="🚀",
        layout="wide"
    )
    
    st.title("🚀 RocketReach Contact Finder")
    st.markdown("Aplikacja do wyszukiwania kontaktów w firmach na podstawie stron internetowych")
    
    # Sidebar dla konfiguracji
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        
        # API Key
        api_key = st.text_input(
            "RocketReach API Key",
            type="password",
            help="Wprowadź swój klucz API z RocketReach"
        )
        
        # Stanowiska do wyszukiwania
        st.subheader("Stanowiska do wyszukiwania")
        default_titles = ["M&A", "M and A", "corporate development", "strategy", "strategic", "growth", "merger"]
        
        job_titles_input = st.text_area(
            "Nazwy stanowisk (po jednej w linii)",
            value="\n".join(default_titles),
            height=150,
            help="Wprowadź nazwy stanowisk, każdą w nowej linii"
        )
        
        job_titles = [title.strip() for title in job_titles_input.split('\n') if title.strip()]
        
        # Stanowiska do wykluczenia
        st.subheader("Stanowiska do wykluczenia")
        exclude_titles_input = st.text_area(
            "Nazwy stanowisk do wykluczenia (po jednej w linii)",
            height=100,
            help="Wprowadź nazwy stanowisk do wykluczenia, każdą w nowej linii"
        )
        
        exclude_titles = [title.strip() for title in exclude_titles_input.split('\n') if title.strip()]
        
        # Informacje o limitach API
        st.info("ℹ️ Pamiętaj o limitach API RocketReach. Wyszukiwanie jest darmowe, ale lookup szczegółów pobiera kredyty.")
    
    # Główna część aplikacji
    st.header("📁 Upload pliku CSV")
    
    uploaded_file = st.file_uploader(
        "Wybierz plik CSV ze stronami internetowymi firm (kolumna A)",
        type=['csv'],
        help="Plik powinien zawierać strony internetowe firm w kolumnie A"
    )
    
    if uploaded_file is not None and api_key:
        try:
            # Wczytaj plik CSV
            df = pd.read_csv(uploaded_file)
            
            if df.empty:
                st.error("Plik CSV jest pusty")
                return
            
            # Pokaż podgląd danych
            st.subheader("📊 Podgląd danych wejściowych")
            st.dataframe(df.head())
            
            # Pobierz listę stron internetowych z pierwszej kolumny
            websites = df.iloc[:, 0].dropna().tolist()
            
            st.subheader(f"🔍 Analiza {len(websites)} firm")
            
            if st.button("🚀 Rozpocznij wyszukiwanie", type="primary"):
                # Inicjalizuj API
                rr_api = RocketReachAPI(api_key)
                
                # Przygotuj listę wyników
                results = []
                
                # Progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, website in enumerate(websites):
                    status_text.text(f"Analizowanie: {website} ({i+1}/{len(websites)})")
                    
                    domain = extract_domain(website)
                    
                    # Wyszukaj osoby w firmie
                    people = rr_api.search_people_by_company(domain, job_titles, exclude_titles)
                    
                    if not people:
                        # Jeśli nie znaleziono nikogo
                        result_row = {
                            'Website': website,
                            'Status': 'Nie znaleziono kontaktów'
                        }
                        for j in range(1, 6):
                            result_row.update({
                                f'Imię i nazwisko osoby {j}': '',
                                f'Stanowisko osoby {j}': '',
                                f'Email osoby {j}': '',
                                f'LinkedIn URL osoby {j}': ''
                            })
                        results.append(result_row)
                    else:
                        # Przygotuj wiersz wyników
                        result_row = {
                            'Website': website,
                            'Status': f'Znaleziono {len(people)} kontakt(ów)'
                        }
                        
                        # Pobierz szczegółowe dane dla każdej osoby
                        for j, person in enumerate(people[:5], 1):
                            # Pobierz szczegółowe informacje
                            detailed_person = rr_api.lookup_person_details(person)
                            
                            # Wyciągnij informacje
                            name = detailed_person.get('name', person.get('name', ''))
                            title = detailed_person.get('current_title', person.get('current_title', ''))
                            
                            # Email - sprawdź różne możliwe pola
                            email = ''
                            if 'emails' in detailed_person and detailed_person['emails']:
                                email = detailed_person['emails'][0].get('email', '')
                            elif 'email' in detailed_person:
                                email = detailed_person['email']
                            
                            linkedin = detailed_person.get('linkedin_url', person.get('linkedin_url', ''))
                            
                            result_row.update({
                                f'Imię i nazwisko osoby {j}': name,
                                f'Stanowisko osoby {j}': title,
                                f'Email osoby {j}': email,
                                f'LinkedIn URL osoby {j}': linkedin
                            })
                            
                            # Dodaj opóźnienie między lookup'ami
                            time.sleep(1)
                        
                        # Wypełnij pozostałe kolumny pustymi wartościami
                        for j in range(len(people) + 1, 6):
                            result_row.update({
                                f'Imię i nazwisko osoby {j}': '',
                                f'Stanowisko osoby {j}': '',
                                f'Email osoby {j}': '',
                                f'LinkedIn URL osoby {j}': ''
                            })
                        
                        results.append(result_row)
                    
                    # Aktualizuj progress bar
                    progress_bar.progress((i + 1) / len(websites))
                
                status_text.text("✅ Analiza zakończona!")
                
                # Wyświetl wyniki
                st.subheader("📋 Wyniki wyszukiwania")
                results_df = pd.DataFrame(results)
                st.dataframe(results_df, use_container_width=True)
                
                # Opcja pobrania wyników
                csv = results_df.to_csv(index=False, encoding='utf-8')
                st.download_button(
                    label="📥 Pobierz wyniki jako CSV",
                    data=csv,
                    file_name="rocketreach_results.csv",
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"Błąd podczas przetwarzania pliku: {str(e)}")
    
    elif not api_key:
        st.warning("⚠️ Wprowadź klucz API RocketReach w panelu bocznym")
    
    # Informacje o aplikacji
    with st.expander("ℹ️ Informacje o aplikacji"):
        st.markdown("""
        ### Jak używać aplikacji:
        
        1. **Wprowadź klucz API RocketReach** w panelu bocznym
        2. **Skonfiguruj stanowiska** do wyszukiwania i wykluczenia
        3. **Wgraj plik CSV** z listą stron internetowych firm (kolumna A)
        4. **Kliknij "Rozpocznij wyszukiwanie"** i poczekaj na wyniki
        
        ### Ważne informacje:
        
        - Aplikacja wykorzystuje RocketReach API do wyszukiwania kontaktów
        - Wyszukiwanie podstawowe jest darmowe, ale pobieranie szczegółów kontaktowych pobiera kredyty
        - Wyniki obejmują maksymalnie 5 osób na firmę
        - Aplikacja automatycznie dodaje opóźnienia między zapytaniami API
        
        ### Wymagania:
        
        - Aktywne konto RocketReach z dostępem do API
        - Plik CSV z listą stron internetowych firm w kolumnie A
        """)

if __name__ == "__main__":
    main()
