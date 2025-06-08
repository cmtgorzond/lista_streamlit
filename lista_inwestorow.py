import streamlit as st
import pandas as pd
import requests
import time
from typing import List, Dict

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
        """Wyszukaj osoby według pełnego URL firmy i stanowisk"""
        try:
            all_results = []
            
            # Upewnij się, że URL ma protokół
            if not company_url.startswith(('http://', 'https://')):
                company_url = f'https://{company_url}'
            
            for title in titles:
                if not title.strip():
                    continue
                    
                payload = {
                    "query": {
                        "company_domain": [company_url],  # Użyj company_domain z pełnym URL
                        "current_title": [title.strip()]  # Bez cudzysłowów
                    },
                    "start": 1,
                    "page_size": 10
                }
                
                response = requests.post(
                    f"{self.base_url}/api/v2/person/search",
                    headers=self.headers,
                    json=payload
                )
                
                if response.status_code == 201:  # Status 201 dla search
                    data = response.json()
                    for person in data.get('profiles', []):
                        # Sprawdź wykluczenia
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
                else:
                    st.error(f"Błąd search API: {response.status_code} - {response.text}")
                
                time.sleep(0.5)  # Rate limiting
            
            return all_results[:5]  # Maksymalnie 5 osób
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania: {str(e)}")
            return []

    def lookup_person_details(self, person_id: int) -> Dict:
        """Pobierz szczegółowe dane osoby przez ID"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v2/person/lookup",
                headers=self.headers,
                params={
                    "id": person_id,
                    "lookup_type": "standard"
                }
            )
            
            if response.status_code == 200:  # Status 200 dla lookup
                data = response.json()
                
                # Wyciągnij najlepszy email zawodowy
                professional_email = ""
                if 'emails' in data:
                    # Priorytet: zweryfikowane emaile zawodowe
                    for email_obj in data['emails']:
                        if (email_obj.get('type') == 'professional' and 
                            email_obj.get('smtp_valid') == 'valid'):
                            professional_email = email_obj.get('email', '')
                            break
                    
                    # Jeśli nie ma zweryfikowanych, weź pierwszy zawodowy
                    if not professional_email:
                        for email_obj in data['emails']:
                            if email_obj.get('type') == 'professional':
                                professional_email = email_obj.get('email', '')
                                break
                
                # Alternatywnie użyj recommended email
                if not professional_email:
                    professional_email = data.get('recommended_professional_email', '')
                
                return {
                    "name": data.get('name', ''),
                    "title": data.get('current_title', ''),
                    "email": professional_email,
                    "linkedin": data.get('linkedin_url', ''),
                    "company": data.get('current_employer', '')
                }
            else:
                st.error(f"Błąd lookup API: {response.status_code} - {response.text}")
                return {}
                
        except Exception as e:
            st.error(f"Błąd pobierania szczegółów: {str(e)}")
            return {}

def main():
    st.set_page_config(page_title="🚀 RocketReach Contact Finder", layout="wide")
    st.title("🚀 RocketReach Contact Finder")
    st.markdown("Aplikacja do wyszukiwania kontaktów w firmach")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        api_key = st.text_input("RocketReach API Key", type="password")
        
        st.subheader("Stanowiska do wyszukiwania")
        job_titles_input = st.text_area(
            "Nazwy stanowisk (po jednej w linii)",
            "sales\nM&A\nM and A\ncorporate development\nstrategy\nstrategic\ngrowth\nmerger",
            height=150
        )
        job_titles = [title.strip() for title in job_titles_input.split('\n') if title.strip()]
        
        st.subheader("Stanowiska do wykluczenia")
        exclude_titles_input = st.text_area(
            "Nazwy stanowisk do wykluczenia (po jednej w linii)",
            height=100
        )
        exclude_titles = [title.strip() for title in exclude_titles_input.split('\n') if title.strip()]

    # Main content
    st.header("📁 Upload pliku CSV")
    uploaded_file = st.file_uploader(
        "Wybierz plik CSV ze stronami internetowymi firm (kolumna A)",
        type=['csv']
    )
    
    if uploaded_file is not None and api_key:
        try:
            df = pd.read_csv(uploaded_file)
            websites = df.iloc[:, 0].dropna().tolist()
            
            st.subheader("📊 Podgląd danych")
            st.dataframe(df.head())
            
            if st.button("🚀 Rozpocznij wyszukiwanie", type="primary"):
                rr_api = RocketReachAPI(api_key)
                results = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, website in enumerate(websites):
                    status_text.text(f"Analizowanie: {website} ({i+1}/{len(websites)})")
                    
                    # Wyszukaj osoby
                    people = rr_api.search_people(website, job_titles, exclude_titles)
                    
                    result_row = {"Website": website}
                    
                    if not people:
                        result_row["Status"] = "Nie znaleziono kontaktów"
                        # Wypełnij puste kolumny
                        for j in range(1, 6):
                            result_row.update({
                                f"Imię i nazwisko osoby {j}": "",
                                f"Stanowisko osoby {j}": "",
                                f"Email osoby {j}": "",
                                f"LinkedIn URL osoby {j}": ""
                            })
                    else:
                        result_row["Status"] = f"Znaleziono {len(people)} kontakt(ów)"
                        
                        # Pobierz szczegółowe dane dla każdej osoby
                        for j, person in enumerate(people[:5], 1):
                            details = rr_api.lookup_person_details(person['id'])
                            time.sleep(1)  # Rate limiting dla lookupów
                            
                            result_row.update({
                                f"Imię i nazwisko osoby {j}": details.get('name', ''),
                                f"Stanowisko osoby {j}": details.get('title', ''),
                                f"Email osoby {j}": details.get('email', ''),
                                f"LinkedIn URL osoby {j}": details.get('linkedin', '')
                            })
                        
                        # Wypełnij pozostałe puste kolumny
                        for j in range(len(people) + 1, 6):
                            result_row.update({
                                f"Imię i nazwisko osoby {j}": "",
                                f"Stanowisko osoby {j}": "",
                                f"Email osoby {j}": "",
                                f"LinkedIn URL osoby {j}": ""
                            })
                    
                    results.append(result_row)
                    progress_bar.progress((i + 1) / len(websites))
                
                status_text.text("✅ Analiza zakończona!")
                
                # Wyświetl wyniki
                st.subheader("📋 Wyniki wyszukiwania")
                results_df = pd.DataFrame(results)
                st.dataframe(results_df, use_container_width=True)
                
                # Download button
                csv = results_df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    "📥 Pobierz wyniki jako CSV",
                    data=csv,
                    file_name="rocketreach_results.csv",
                    mime="text/csv"
                )
        
        except Exception as e:
            st.error(f"Błąd: {str(e)}")
    
    elif not api_key:
        st.warning("⚠️ Wprowadź klucz API RocketReach")

if __name__ == "__main__":
    main()
