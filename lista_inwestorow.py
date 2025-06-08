import streamlit as st
import pandas as pd
import requests
import time
from typing import List, Dict, Optional
import re
from urllib.parse import urlparse

class RocketReachClient:
    """Klient do komunikacji z RocketReach API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co/api/v2"
        self.headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json"
        }
        
    def search_people(self, company_domain: str, job_titles: List[str], 
                     exclude_titles: List[str] = None, max_results: int = 5) -> List[Dict]:
        """Wyszukuje osoby w firmie na podstawie domeny i stanowisk"""
        
        # Wyciągnij nazwę firmy z domeny
        company_name = self._extract_company_name(company_domain)
        
        all_results = []
        
        # Wyszukuj dla każdego stanowiska osobno, aby zwiększyć szanse znalezienia
        for title in job_titles:
            if len(all_results) >= max_results:
                break
                
            search_params = {
                "current_employer": company_name,
                "current_title": title,
                "size": min(10, max_results - len(all_results))
            }
            
            # Dodaj wykluczenia jeśli są podane
            if exclude_titles:
                search_params["exclude_current_title"] = exclude_titles
            
            try:
                response = requests.post(
                    f"{self.base_url}/person/search",
                    headers=self.headers,
                    json=search_params,
                    timeout=30
                )
                
                if response.status_code == 201:
                    data = response.json()
                    if "people" in data:
                        for person in data["people"]:
                            if len(all_results) >= max_results:
                                break
                            # Sprawdź czy osoba nie jest już w wynikach
                            if not any(p.get("id") == person.get("id") for p in all_results):
                                all_results.append(person)
                
                elif response.status_code == 429:
                    st.warning("Osiągnięto limit zapytań API. Czekam 2 sekundy...")
                    time.sleep(2)
                    continue
                else:
                    st.error(f"Błąd API dla {company_domain}: {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                st.error(f"Błąd połączenia dla {company_domain}: {str(e)}")
                
            # Pauza między zapytaniami aby uniknąć rate limitów
            time.sleep(0.5)
        
        return all_results[:max_results]
    
    def _extract_company_name(self, domain: str) -> str:
        """Wyciąga nazwę firmy z domeny"""
        # Usuń protokół jeśli jest
        if "://" in domain:
            domain = urlparse(domain).netloc
        
        # Usuń www. jeśli jest
        if domain.startswith("www."):
            domain = domain[4:]
            
        # Wyciąg nazwę bez rozszerzenia
        company_name = domain.split(".")[0]
        
        return company_name.capitalize()
    
    def test_connection(self) -> bool:
        """Testuje połączenie z API"""
        try:
            response = requests.get(
                f"{self.base_url}/account",
                headers=self.headers,
                timeout=10
            )
            return response.status_code == 201
        except:
            return False

def main():
    st.set_page_config(
        page_title="RocketReach - Wyszukiwanie Osób w Firmach",
        page_icon="🚀",
        layout="wide"
    )
    
    st.title("🚀 RocketReach - Wyszukiwanie Osób w Firmach")
    st.markdown("Aplikacja do wyszukiwania osób w firmach na podstawie domen internetowych")
    
    # Sidebar z konfiguracją
    st.sidebar.header("⚙️ Konfiguracja")
    
    # Pole na klucz API
    api_key = st.sidebar.text_input(
        "Klucz API RocketReach:",
        type="password",
        help="Wprowadź swój klucz API z RocketReach"
    )
    
    if not api_key:
        st.warning("⚠️ Wprowadź klucz API RocketReach w panelu bocznym")
        st.info("""
        **Jak uzyskać klucz API:**
        1. Zaloguj się do swojego konta RocketReach
        2. Przejdź do Account Settings
        3. Wybierz API Usage & Settings
        4. Wygeneruj lub skopiuj swój klucz API
        """)
        return
    
    # Inicjalizacja klienta
    client = RocketReachClient(api_key)
    
    # Test połączenia
    if st.sidebar.button("🔗 Testuj połączenie API"):
        if client.test_connection():
            st.sidebar.success("✅ Połączenie z API działa!")
        else:
            st.sidebar.error("❌ Błąd połączenia z API")
            return
    
    # Główny interfejs
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📋 Stanowiska do wyszukania")
        default_titles = ["M&A", "M and A", "corporate development", "strategy", "strategic", "growth", "merger"]
        
        job_titles_input = st.text_area(
            "Wprowadź stanowiska (każde w nowej linii):",
            value="\n".join(default_titles),
            height=200,
            help="Każde stanowisko w osobnej linii"
        )
        
        job_titles = [title.strip() for title in job_titles_input.split("\n") if title.strip()]
    
    with col2:
        st.subheader("🚫 Stanowiska do wykluczenia")
        exclude_titles_input = st.text_area(
            "Wprowadź stanowiska do wykluczenia (każde w nowej linii):",
            height=200,
            help="Opcjonalne: stanowiska które mają być wykluczone z wyników"
        )
        
        exclude_titles = [title.strip() for title in exclude_titles_input.split("\n") if title.strip()]
    
    # Upload pliku CSV
    st.subheader("📁 Plik CSV z domenami firm")
    uploaded_file = st.file_uploader(
        "Wybierz plik CSV",
        type="csv",
        help="Plik CSV gdzie kolumna A zawiera domeny internetowe firm"
    )
    
    if uploaded_file is not None:
        try:
            # Wczytaj CSV
            df = pd.read_csv(uploaded_file)
            st.write("**Podgląd pliku:**")
            st.dataframe(df.head())
            
            # Pobierz domeny z pierwszej kolumny
            domains = df.iloc[:, 0].dropna().tolist()
            
            st.write(f"**Znaleziono {len(domains)} domen do przeszukania**")
            
            if st.button("🔍 Rozpocznij wyszukiwanie", type="primary"):
                if not job_titles:
                    st.error("❌ Wprowadź przynajmniej jedno stanowisko do wyszukania")
                    return
                
                # Progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Wyniki
                results = []
                
                for i, domain in enumerate(domains):
                    status_text.text(f"Przeszukuję: {domain} ({i+1}/{len(domains)})")
                    
                    # Wyszukaj osoby
                    people = client.search_people(
                        company_domain=domain,
                        job_titles=job_titles,
                        exclude_titles=exclude_titles if exclude_titles else None,
                        max_results=5
                    )
                    
                    # Przygotuj wiersz wyników
                    row = {"Domena": domain}
                    
                    if people:
                        for j, person in enumerate(people, 1):
                            row[f"ID {j}"] = person.get("id", "")
                            row[f"Imię i nazwisko {j}"] = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
                            row[f"Stanowisko {j}"] = person.get("current_title", "")
                    else:
                        row["Status"] = "Nie znaleziono kontaktów"
                    
                    results.append(row)
                    
                    # Aktualizuj progress bar
                    progress_bar.progress((i + 1) / len(domains))
                
                status_text.text("✅ Wyszukiwanie zakończone!")
                
                # Wyświetl wyniki
                st.subheader("📊 Wyniki wyszukiwania")
                
                if results:
                    results_df = pd.DataFrame(results)
                    
                    # Wyświetl tabelę
                    st.dataframe(results_df, use_container_width=True)
                    
                    # Przycisk do pobrania
                    csv = results_df.to_csv(index=False)
                    st.download_button(
                        label="💾 Pobierz wyniki jako CSV",
                        data=csv,
                        file_name="rocketreach_wyniki.csv",
                        mime="text/csv"
                    )
                    
                    # Statystyki
                    st.subheader("📈 Statystyki")
                    total_companies = len(results)
                    companies_with_contacts = len([r for r in results if "Status" not in r or r["Status"] != "Nie znaleziono kontaktów"])
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Przeszukane firmy", total_companies)
                    with col2:
                        st.metric("Firmy z kontaktami", companies_with_contacts)
                    with col3:
                        success_rate = (companies_with_contacts / total_companies * 100) if total_companies > 0 else 0
                        st.metric("Skuteczność", f"{success_rate:.1f}%")
                
        except Exception as e:
            st.error(f"❌ Błąd podczas przetwarzania pliku: {str(e)}")
    
    # Informacje o aplikacji
    st.sidebar.markdown("---")
    st.sidebar.markdown("**ℹ️ Informacje o aplikacji**")
    st.sidebar.markdown("""
    - Wykorzystuje RocketReach API
    - Wyszukuje maksymalnie 5 osób na firmę
    - Automatycznie zarządza limitami API
    - Eksportuje wyniki do CSV
    """)

if __name__ == "__main__":
    main()
