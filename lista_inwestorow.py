import streamlit as st
import pandas as pd
import requests
import time
import os
import re
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
    
    # 1. GitHub Actions/Environment Variables (najwyższy priorytet)
    api_key = os.getenv('ROCKETREACH_API_KEY')
    if api_key:
        return api_key
    
    # 2. Streamlit secrets (dla Streamlit Cloud)
    try:
        if hasattr(st, 'secrets') and 'ROCKETREACH_API_KEY' in st.secrets:
            return st.secrets.ROCKETREACH_API_KEY
    except:
        pass
    
    # 3. Streamlit secrets z api_keys (alternatywna struktura)
    try:
        if hasattr(st, 'secrets') and 'api_keys' in st.secrets and 'rocketreach' in st.secrets.api_keys:
            return st.secrets.api_keys.rocketreach
    except:
        pass
    
    # 4. Jeśli nic nie znaleziono, zwróć None
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

    def search_people(self, company_url: str, titles: List[str], exclude_titles: List[str], 
                     skills: List[str], exclude_skills: List[str]) -> List[Dict]:
        """Wyszukaj osoby według stanowisk i umiejętności"""
        try:
            all_results = []
            
            # Wyszukiwanie po stanowiskach
            st.info("🔍 Wyszukiwanie po stanowiskach...")
            title_results = self._search_by_criteria(company_url, "current_title", titles, exclude_titles)
            all_results.extend(title_results)
            
            # Jeśli mniej niż 5 wyników, szukaj po skills
            if len(all_results) < 5:
                st.info("🎯 Rozszerzam wyszukiwanie o umiejętności...")
                skill_results = self._search_by_criteria(company_url, "skills", skills, exclude_skills)
                
                # Dodaj tylko unikalne wyniki
                for result in skill_results:
                    if not any(existing['id'] == result['id'] for existing in all_results):
                        all_results.append(result)
                        if len(all_results) >= 5:
                            break
            
            return all_results[:5]  # Ogranicz do 5 wyników
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania: {str(e)}")
            return []

    def _search_by_criteria(self, company_url: str, field: str, values: List[str], 
                          exclude_values: List[str]) -> List[Dict]:
        """Uniwersalna metoda do wyszukiwania po dowolnym kryterium"""
        try:
            results = []
            
            if not company_url.startswith(('http://', 'https://')):
                company_url = f'https://{company_url}'
            
            for value in values:
                if not value.strip():
                    continue
                    
                payload = {
                    "query": {
                        "company_domain": [company_url],
                        field: [value.strip()]
                    },
                    "start": 1,
                    "page_size": 10
                }
                
                # Obsługa błędu 429 z retry logic
                max_retries = 3
                retry_count = 0
                
                while retry_count < max_retries:
                    response = requests.post(
                        f"{self.base_url}/api/v2/person/search",
                        headers=self.headers,
                        json=payload
                    )
                    
                    if response.status_code == 429:
                        try:
                            error_data = response.json()
                            wait_time = float(error_data.get('wait', 60))
                        except:
                            wait_time = 60
                        
                        st.warning(f"⏳ Przekroczono limit zapytań. Czekam {wait_time:.0f} sekund...")
                        time.sleep(wait_time + 5)
                        retry_count += 1
                        continue
                    
                    elif response.status_code == 201:
                        data = response.json()
                        for person in data.get('profiles', []):
                            # Sprawdź wykluczenia
                            if field == "current_title":
                                check_value = person.get('current_title', '').lower()
                            elif field == "skills":
                                check_value = ' '.join(person.get('skills', [])).lower()
                            else:
                                check_value = str(person.get(field, '')).lower()
                            
                            if exclude_values and any(excl.lower() in check_value for excl in exclude_values if excl.strip()):
                                continue
                                
                            results.append({
                                "id": person.get('id'),
                                "name": person.get('name'),
                                "title": person.get('current_title'),
                                "company": person.get('current_employer'),
                                "linkedin": person.get('linkedin_url'),
                                "skills": person.get('skills', [])
                            })
                        break
                    
                    else:
                        st.error(f"Błąd search API: {response.status_code} - {response.text}")
                        break
                
                time.sleep(2)  # Dodatkowe opóźnienie między zapytaniami
            
            return results
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania po {field}: {str(e)}")
            return []

    def lookup_person_details(self, person_id: int) -> Dict:
        """Pobierz szczegółowe dane osoby przez ID"""
        try:
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                response = requests.get(
                    f"{self.base_url}/api/v2/person/lookup",
                    headers=self.headers,
                    params={
                        "id": person_id,
                        "lookup_type": "standard"
                    }
                )
                
                if response.status_code == 429:
                    try:
                        error_data = response.json()
                        wait_time = float(error_data.get('wait', 60))
                    except:
                        wait_time = 60
                    
                    st.warning(f"⏳ Limit lookup API. Czekam {wait_time:.0f} sekund...")
                    time.sleep(wait_time + 5)
                    retry_count += 1
                    continue
                
                elif response.status_code == 200:
                    data = response.json()
                    
                    professional_email = ""
                    email_type = ""
                    email_grade = ""
                    smtp_valid = ""
                    
                    # Hierarchia wyboru emaila
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
                    
                    # Sprawdź czy email ma smtp_valid = 'invalid'
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
                        "company": data.get('current_employer', ''),
                        "skills": data.get('skills', [])
                    }
                else:
                    st.error(f"Błąd lookup API: {response.status_code} - {response.text}")
                    break
            
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
        else:
            st.error("❌ Nie znaleziono klucza API - skonfiguruj GitHub Secrets lub zmienne środowiskowe")
        
        st.subheader("Stanowiska do wyszukiwania")
        job_titles_input = st.text_area(
            "Nazwy stanowisk (po jednej w linii)",
            "M&A\nM and A\ncorporate development\nstrategy\nstrategic\ngrowth\nmerger\nacquisition",
            height=150
        )
        job_titles = [title.strip() for title in job_titles_input.split('\n') if title.strip()]
        
        st.subheader("Umiejętności do wyszukiwania")
        skills_input = st.text_area(
            "Umiejętności (po jednej w linii)",
            "M&A\nM and A\ncorporate development\nstrategy\nstrategic\ngrowth\nmerger\nacquisition",
            height=150
        )
        skills = [skill.strip() for skill in skills_input.split('\n') if skill.strip()]
        
        st.subheader("Stanowiska do wykluczenia")
        exclude_titles_input = st.text_area(
            "Nazwy stanowisk do wykluczenia (po jednej w linii)",
            "hr\nhuman resources\nmarketing\nsales\ntalent",
            height=100
        )
        exclude_titles = [title.strip() for title in exclude_titles_input.split('\n') if title.strip()]
        
        st.subheader("Umiejętności do wykluczenia")
        exclude_skills_input = st.text_area(
            "Umiejętności do wykluczenia (po jednej w linii)",
            "hr\nhuman resources\nmarketing\nsales\ntalent",
            height=100
        )
        exclude_skills = [skill.strip() for skill in exclude_skills_input.split('\n') if skill.strip()]

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
                
                # Wyszukaj osoby (po stanowiskach i umiejętnościach)
                people = rr_api.search_people(website, job_titles, exclude_titles, skills, exclude_skills)
                
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
                        time.sleep(2)  # Rate limiting
                        
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
        st.error("❌ Brak klucza API - skonfiguruj GitHub Secrets lub zmienne środowiskowe")
    elif not websites:
        st.info("📝 Wprowadź dane firm do analizy")

if __name__ == "__main__":
    main()
