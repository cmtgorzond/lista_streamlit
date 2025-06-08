import streamlit as st
import pandas as pd
import requests
import time
import os
from typing import List, Dict

# Sprawdź czy python-dotenv jest zainstalowane
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    st.warning("Biblioteka python-dotenv nie jest zainstalowana. Instaluję...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])
    from dotenv import load_dotenv
    load_dotenv()

# Sprawdź czy openpyxl jest zainstalowane
try:
    import openpyxl
except ImportError:
    st.error("Biblioteka openpyxl nie jest zainstalowana. Instaluję...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    import openpyxl

import io

def get_api_key():
    """Pobiera klucz API z różnych źródeł w kolejności priorytetów"""
    
    # 1. Streamlit secrets (najwyższy priorytet dla wdrożeń w chmurze)
    try:
        if hasattr(st, 'secrets') and 'api_keys' in st.secrets and 'rocketreach' in st.secrets.api_keys:
            return st.secrets.api_keys.rocketreach
    except:
        pass
    
    # 2. Zmienna środowiskowa
    api_key = os.getenv('ROCKETREACH_API_KEY')
    if api_key:
        return api_key
    
    # 3. Jeśli nic nie znaleziono, zwróć None
    return None

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
            
            if not company_url.startswith(('http://', 'https://')):
                company_url = f'https://{company_url}'
            
            for title in titles:
                if not title.strip():
                    continue
                    
                payload = {
                    "query": {
                        "company_domain": [company_url],
                        "current_title": [title.strip()]
                    },
                    "start": 1,
                    "page_size": 20
                }
                
                response = requests.post(
                    f"{self.base_url}/api/v2/person/search",
                    headers=self.headers,
                    json=payload
                )
                
                if response.status_code == 201:
                    data = response.json()
                    for person in data.get('profiles', []):
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
                
                time.sleep(0.5)
            
            return all_results
            
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
            
            if response.status_code == 200:
                data = response.json()
                
                professional_email = ""
                email_type = ""
                email_grade = ""
                smtp_valid = ""
                
                if data.get('recommended_professional_email'):
                    professional_email = data.get('recommended_professional_email')
                    for email_obj in data.get('emails', []):
                        if email_obj.get('email') == professional_email:
                            email_type = email_obj.get('type', '')
                            email_grade = email_obj.get('grade', '')
                            smtp_valid = email_obj.get('smtp_valid', '')
                            break
                
                elif data.get('current_work_email'):
                    professional_email = data.get('current_work_email')
                    for email_obj in data.get('emails', []):
                        if email_obj.get('email') == professional_email:
                            email_type = email_obj.get('type', '')
                            email_grade = email_obj.get('grade', '')
                            smtp_valid = email_obj.get('smtp_valid', '')
                            break
                
                elif 'emails' in data:
                    valid_professional_emails = [
                        email_obj for email_obj in data['emails']
                        if (email_obj.get('type') == 'professional' and 
                            email_obj.get('smtp_valid') != 'invalid')
                    ]
                    
                    if valid_professional_emails:
                        grade_order = {'A': 1, 'A-': 2, 'B': 3, 'B-': 4, 'C': 5, 'D': 6, 'F': 7}
                        valid_professional_emails.sort(
                            key=lambda x: grade_order.get(x.get('grade', 'F'), 8)
                        )
                        
                        best_email = valid_professional_emails[0]
                        professional_email = best_email.get('email', '')
                        email_type = best_email.get('type', '')
                        email_grade = best_email.get('grade', '')
                        smtp_valid = best_email.get('smtp_valid', '')
                
                if smtp_valid == 'invalid':
                    return {}
                
                return {
                    "name": data.get('name', ''),
                    "title": data.get('current_title', ''),
                    "email": professional_email,
                    "email_type": email_type,
                    "email_grade": email_grade,
                    "smtp_valid": smtp_valid,
                    "linkedin": data.get('linkedin_url', ''),
                    "company": data.get('current_employer', '')
                }
            else:
                st.error(f"Błąd lookup API: {response.status_code} - {response.text}")
                return {}
                
        except Exception as e:
            st.error(f"Błąd pobierania szczegółów: {str(e)}")
            return {}

def create_excel_file(results_df: pd.DataFrame) -> bytes:
    """Tworzy plik Excel i zwraca jako bytes"""
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            results_df.to_excel(writer, index=False, sheet_name='Kontakty')
        return output.getvalue()
    except Exception as e:
        st.error(f"Błąd tworzenia pliku Excel: {str(e)}")
        return results_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')

def main():
    st.set_page_config(page_title="🎯 Wyszukiwanie kontaktów do inwestorów", layout="wide")
    st.title("🎯 Wyszukiwanie kontaktów do inwestorów")
    st.markdown("Aplikacja do wyszukiwania kontaktów w firmach z zaawansowanymi filtrami")
    
    # Pobierz klucz API
    api_key = get_api_key()
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        
        # Wyświetl status klucza API
        if api_key:
            st.success("✅ Klucz API został automatycznie załadowany")
            # Opcjonalnie pozwól na nadpisanie
            manual_api_key = st.text_input(
                "Nadpisz klucz API (opcjonalnie)", 
                type="password",
                help="Pozostaw puste aby użyć automatycznie załadowanego klucza"
            )
            if manual_api_key.strip():
                api_key = manual_api_key.strip()
                st.info("🔄 Używam ręcznie wprowadzonego klucza")
        else:
            st.warning("⚠️ Nie znaleziono automatycznego klucza API")
            api_key = st.text_input(
                "Wprowadź klucz API RocketReach", 
                type="password",
                help="Klucz API nie został znaleziony w zmiennych środowiskowych ani secrets"
            )
        
        st.subheader("Stanowiska do wyszukiwania")
        job_titles_input = st.text_area(
            "Nazwy stanowisk (po jednej w linii)",
            "M&A\nM and A\ncorporate development\nstrategy\nstrategic\ngrowth\nmerger\nacquisition",
            height=150
        )
        job_titles = [title.strip() for title in job_titles_input.split('\n') if title.strip()]
        
        st.subheader("Stanowiska do wykluczenia")
        exclude_titles_input = st.text_area(
            "Nazwy stanowisk do wykluczenia (po jednej w linii)",
            "hr\nhuman resources\nmarketing\nsales\ntalent",
            height=100
        )
        exclude_titles = [title.strip() for title in exclude_titles_input.split('\n') if title.strip()]

    # Opcja wyboru źródła danych
    st.header("📊 Źródło danych")
    data_source = st.radio(
        "Wybierz sposób wprowadzenia domen:",
        ["Upload pliku CSV", "Wpisz domenę ręcznie"]
    )
    
    websites = []
    
    if data_source == "Upload pliku CSV":
        uploaded_file = st.file_uploader(
            "Wybierz plik CSV ze stronami internetowymi firm (kolumna A)",
            type=['csv']
        )
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                websites = df.iloc[:, 0].dropna().tolist()
                
                st.subheader("📊 Podgląd danych")
                st.dataframe(df.head())
                
            except Exception as e:
                st.error(f"Błąd wczytywania pliku: {str(e)}")
    
    else:
        st.subheader("🌐 Wprowadź domenę ręcznie")
        manual_domain = st.text_input(
            "Wpisz domenę firmy (np. https://www.nvidia.com/)",
            placeholder="https://www.example.com"
        )
        
        if manual_domain.strip():
            websites = [manual_domain.strip()]
            st.success(f"Dodano domenę: {manual_domain}")
    
    # Przycisk wyszukiwania
    if websites and api_key:
        if st.button("🚀 Rozpocznij wyszukiwanie", type="primary"):
            rr_api = RocketReachAPI(api_key)
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, website in enumerate(websites):
                status_text.text(f"Analizowanie: {website} ({i+1}/{len(websites)})")
                
                people = rr_api.search_people(website, job_titles, exclude_titles)
                
                result_row = {"Website": website}
                
                if not people:
                    result_row["Status"] = "Nie znaleziono kontaktów"
                    for j in range(1, 6):
                        result_row.update({
                            f"Imię i nazwisko osoby {j}": "",
                            f"Stanowisko osoby {j}": "",
                            f"Email osoby {j}": "",
                            f"LinkedIn URL osoby {j}": "",
                            f"Type emaila osoby {j}": "",
                            f"Grade emaila osoby {j}": "",
                            f"SMTP Valid osoby {j}": ""
                        })
                else:
                    valid_contacts = []
                    
                    for person in people:
                        details = rr_api.lookup_person_details(person['id'])
                        time.sleep(1)
                        
                        if details.get('email') and details.get('smtp_valid') != 'invalid':
                            valid_contacts.append(details)
                        
                        if len(valid_contacts) >= 5:
                            break
                    
                    if not valid_contacts:
                        result_row["Status"] = "Nie znaleziono kontaktów z prawidłowymi emailami"
                        for j in range(1, 6):
                            result_row.update({
                                f"Imię i nazwisko osoby {j}": "",
                                f"Stanowisko osoby {j}": "",
                                f"Email osoby {j}": "",
                                f"LinkedIn URL osoby {j}": "",
                                f"Type emaila osoby {j}": "",
                                f"Grade emaila osoby {j}": "",
                                f"SMTP Valid osoby {j}": ""
                            })
                    else:
                        result_row["Status"] = f"Znaleziono {len(valid_contacts)} kontakt(ów) z prawidłowymi emailami"
                        
                        for j, contact in enumerate(valid_contacts[:5], 1):
                            result_row.update({
                                f"Imię i nazwisko osoby {j}": contact.get('name', ''),
                                f"Stanowisko osoby {j}": contact.get('title', ''),
                                f"Email osoby {j}": contact.get('email', ''),
                                f"LinkedIn URL osoby {j}": contact.get('linkedin', ''),
                                f"Type emaila osoby {j}": contact.get('email_type', ''),
                                f"Grade emaila osoby {j}": contact.get('email_grade', ''),
                                f"SMTP Valid osoby {j}": contact.get('smtp_valid', '')
                            })
                        
                        for j in range(len(valid_contacts) + 1, 6):
                            result_row.update({
                                f"Imię i nazwisko osoby {j}": "",
                                f"Stanowisko osoby {j}": "",
                                f"Email osoby {j}": "",
                                f"LinkedIn URL osoby {j}": "",
                                f"Type emaila osoby {j}": "",
                                f"Grade emaila osoby {j}": "",
                                f"SMTP Valid osoby {j}": ""
                            })
                
                results.append(result_row)
                progress_bar.progress((i + 1) / len(websites))
            
            status_text.text("✅ Analiza zakończona!")
            
            # Wyświetl wyniki
            st.subheader("📋 Wyniki wyszukiwania")
            results_df = pd.DataFrame(results)
            st.dataframe(results_df, use_container_width=True)
            
            # Statystyki
            st.subheader("📊 Statystyki")
            total_contacts = sum(1 for result in results 
                               for j in range(1, 6) 
                               if result.get(f"Email osoby {j}"))
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Przeanalizowane firmy", len(websites))
            with col2:
                st.metric("Znalezione kontakty", total_contacts)
            with col3:
                firms_with_contacts = sum(1 for result in results 
                                        if "kontakt" in result["Status"] and "Nie znaleziono" not in result["Status"])
                st.metric("Firmy z kontaktami", firms_with_contacts)
            
            # Download button
            excel_data = create_excel_file(results_df)
            st.download_button(
                "📥 Pobierz wyniki jako Excel",
                data=excel_data,
                file_name="kontakty_inwestorzy.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
    elif not api_key:
        st.error("❌ Brak klucza API - skonfiguruj go w pliku .env lub wprowadź ręcznie")
    elif not websites:
        st.info("📝 Wprowadź dane firm do analizy")

    # Informacje o aplikacji
    with st.expander("ℹ️ Konfiguracja klucza API"):
        st.markdown("""
        ### Sposoby konfiguracji klucza API:
        
        **Metoda 1: Plik .env (zalecana dla rozwoju)**
        1. Stwórz plik `.env` w głównym folderze projektu
        2. Dodaj linię: `ROCKETREACH_API_KEY=twój_klucz_api`
        3. Dodaj `.env` do pliku `.gitignore`
        
        **Metoda 2: Streamlit Secrets (zalecana dla wdrożenia)**
        1. Stwórz folder `.streamlit`
        2. Stwórz plik `.streamlit/secrets.toml`
        3. Dodaj: `[api_keys]` i `rocketreach = "twój_klucz_api"`
        
        **Metoda 3: Ręczne wprowadzenie**
        - Wprowadź klucz w polu powyżej (nie jest bezpieczne dla produkcji)
        """)

if __name__ == "__main__":
    main()
