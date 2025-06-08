import streamlit as st
import pandas as pd
import requests
import time
import random
import re
from typing import List, Dict

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

class RocketReachAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co"
        self.headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json"
        }
        self.request_timestamps = []

    def _rate_limit_check(self):
        """Zachowaj maksymalnie 5 zapytań na sekundę zgodnie z dokumentacją API"""
        now = time.time()
        # Usuń stare timestampy (starsze niż 1 sekunda)
        self.request_timestamps = [t for t in self.request_timestamps if t > now - 1]
        
        if len(self.request_timestamps) >= 5:
            sleep_time = 1.0 - (now - self.request_timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time + random.uniform(0.1, 0.3))  # Dodaj losowy jitter
        
        self.request_timestamps.append(now)

    def _handle_rate_limit(self, response):
        """Automatyczna obsługa limitu z wykładniczym backoffem"""
        if response.status_code == 429:
            try:
                error_data = response.json()
                retry_after = float(error_data.get('wait', 60))
            except:
                retry_after = float(response.headers.get('Retry-After', 60))
            
            st.warning(f"⏳ Przekroczono limit. Czekam {retry_after:.0f} sekund...")
            time.sleep(retry_after + random.uniform(1, 3))  # Dodaj losowy jitter
            return True
        return False

    def search_people_with_emails(self, company_url: str, titles: List[str], exclude_titles: List[str]) -> List[Dict]:
        """Optymalizowane wyszukiwanie z batchowaniem i dwuetapowym procesem"""
        try:
            valid_contacts = []
            
            # ETAP 1: Wyszukiwanie po stanowiskach (wszystkie tytuły w jednym zapytaniu)
            st.info("🔍 Etap 1: Wyszukiwanie po stanowiskach...")
            title_results = self._search_optimized(company_url, "current_title", titles, exclude_titles)
            
            # Sprawdź emaile dla wyników z stanowisk
            for person in title_results[:15]:  # Ogranicz do 15 wyników dla optymalizacji
                if len(valid_contacts) >= 5:
                    break
                    
                details = self.lookup_person_details(person['id'])
                
                if details.get('email') and details.get('smtp_valid') != 'invalid':
                    # Połącz dane z search i lookup
                    combined_contact = {**person, **details}
                    valid_contacts.append(combined_contact)
                    st.success(f"✅ Znaleziono kontakt przez stanowisko: {details.get('name')} - {details.get('title')} | {details.get('email')} (Grade: {details.get('email_grade', 'N/A')}, SMTP: {details.get('smtp_valid', 'N/A')})")
            
            # ETAP 2: Jeśli mniej niż 5 kontaktów, szukaj po skills
            if len(valid_contacts) < 5:
                st.info(f"🎯 Etap 2: Znaleziono {len(valid_contacts)} kontaktów. Rozszerzam wyszukiwanie o umiejętności...")
                skill_results = self._search_optimized(company_url, "skills", titles, exclude_titles)
                
                # Sprawdź emaile dla wyników z skills (pomijając już znalezione)
                existing_ids = {contact.get('id') for contact in valid_contacts if 'id' in contact}
                
                for person in skill_results[:15]:  # Ogranicz do 15 wyników
                    if len(valid_contacts) >= 5:
                        break
                    
                    # Pomiń jeśli już mamy tę osobę
                    if person['id'] in existing_ids:
                        continue
                        
                    details = self.lookup_person_details(person['id'])
                    
                    if details.get('email') and details.get('smtp_valid') != 'invalid':
                        combined_contact = {**person, **details}
                        valid_contacts.append(combined_contact)
                        st.success(f"✅ Znaleziono kontakt przez umiejętności: {details.get('name')} - {details.get('title')} | {details.get('email')} (Grade: {details.get('email_grade', 'N/A')}, SMTP: {details.get('smtp_valid', 'N/A')})")
            
            st.info(f"📊 Łącznie znaleziono {len(valid_contacts)} kontaktów z prawidłowymi emailami")
            return valid_contacts[:5]
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania: {str(e)}")
            return []

    def _search_optimized(self, company_url: str, field: str, values: List[str], exclude_values: List[str]) -> List[Dict]:
        """Optymalizowane wyszukiwanie z batchowaniem wszystkich tytułów"""
        try:
            self._rate_limit_check()
            
            if not company_url.startswith(('http://', 'https://')):
                company_url = f'https://{company_url}'
            
            # Filtruj puste wartości
            clean_values = [v.strip() for v in values if v.strip()]
            clean_exclude = [v.strip() for v in exclude_values if v.strip()]
            
            if not clean_values:
                return []
            
            # Przygotuj payload z wszystkimi tytułami naraz
            payload = {
                "query": {
                    "company_domain": [company_url],
                    field: clean_values  # Wszystkie tytuły w jednym zapytaniu
                },
                "start": 1,
                "page_size": 50  # Maksymalny rozmiar strony zgodnie z dokumentacją
            }
            
            # Dodaj wykluczenia jeśli istnieją
            if clean_exclude:
                exclude_field = f"exclude_{field}" if field != "skills" else "exclude_current_title"
                payload["query"][exclude_field] = clean_exclude
            
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                response = requests.post(
                    f"{self.base_url}/api/v2/person/search",
                    headers=self.headers,
                    json=payload
                )
                
                if self._handle_rate_limit(response):
                    retry_count += 1
                    continue
                
                elif response.status_code == 201:
                    data = response.json()
                    results = []
                    
                    for person in data.get('profiles', []):
                        # Dodatkowe filtrowanie po stronie klienta dla pewności
                        if field == "current_title":
                            check_value = person.get('current_title', '').lower()
                        elif field == "skills":
                            check_value = ' '.join(person.get('skills', [])).lower()
                        else:
                            check_value = str(person.get(field, '')).lower()
                        
                        # Sprawdź wykluczenia
                        if clean_exclude and any(excl.lower() in check_value for excl in clean_exclude):
                            continue
                            
                        results.append({
                            "id": person.get('id'),
                            "name": person.get('name'),
                            "title": person.get('current_title'),
                            "company": person.get('current_employer'),
                            "linkedin": person.get('linkedin_url'),
                            "skills": person.get('skills', [])
                        })
                    
                    return results
                
                else:
                    st.error(f"Błąd search API: {response.status_code} - {response.text}")
                    break
            
            return []
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania po {field}: {str(e)}")
            return []

    def lookup_person_details(self, person_id: int) -> Dict:
        """Optymalizowane pobieranie danych z lepszą obsługą emaili"""
        try:
            self._rate_limit_check()
            
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
                
                if self._handle_rate_limit(response):
                    retry_count += 1
                    continue
                
                elif response.status_code == 200:
                    data = response.json()
                    return self._process_email_data(data, person_id)
                
                else:
                    st.error(f"Błąd lookup API: {response.status_code} - {response.text}")
                    break
            
            return {}
                
        except Exception as e:
            st.error(f"Błąd pobierania szczegółów: {str(e)}")
            return {}

    def _process_email_data(self, data: Dict, person_id: int) -> Dict:
        """Wspólna metoda przetwarzania emaili z hierarchią wyboru"""
        professional_email = ""
        email_grade = ""
        smtp_valid = ""
        
        # Hierarchia wyboru emaila zgodnie z wymaganiami
        if data.get('recommended_professional_email'):
            professional_email = data.get('recommended_professional_email')
            # Znajdź szczegóły dla tego emaila
            for email_obj in data.get('emails', []):
                if email_obj.get('email') == professional_email:
                    email_grade = email_obj.get('grade', '')
                    smtp_valid = email_obj.get('smtp_valid', '')
                    break
        
        elif data.get('current_work_email'):
            professional_email = data.get('current_work_email')
            # Znajdź szczegóły dla tego emaila
            for email_obj in data.get('emails', []):
                if email_obj.get('email') == professional_email:
                    email_grade = email_obj.get('grade', '')
                    smtp_valid = email_obj.get('smtp_valid', '')
                    break
        
        elif 'emails' in data:
            # Znajdź najlepszy email zawodowy
            valid_professional_emails = [
                email_obj for email_obj in data['emails']
                if (email_obj.get('type') == 'professional' and 
                    email_obj.get('smtp_valid') != 'invalid')
            ]
            
            if valid_professional_emails:
                # Sortuj według grade
                grade_order = {'A': 1, 'A-': 2, 'B': 3, 'B-': 4, 'C': 5, 'D': 6, 'F': 7}
                valid_professional_emails.sort(
                    key=lambda x: grade_order.get(x.get('grade', 'F'), 8)
                )
                
                best_email = valid_professional_emails[0]
                professional_email = best_email.get('email', '')
                email_grade = best_email.get('grade', '')
                smtp_valid = best_email.get('smtp_valid', '')
        
        # Sprawdź czy email ma smtp_valid = 'invalid'
        if smtp_valid == 'invalid':
            return {}
        
        return {
            "id": person_id,
            "name": data.get('name', ''),
            "title": data.get('current_title', ''),
            "email": professional_email,
            "email_grade": email_grade,
            "smtp_valid": smtp_valid,
            "linkedin": data.get('linkedin_url', ''),
            "company": data.get('current_employer', ''),
            "skills": data.get('skills', [])
        }

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
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        
        # Pole do wprowadzania klucza API
        api_key = st.text_input(
            "RocketReach API Key",
            type="password",
            help="Wprowadź swój klucz API z RocketReach"
        )
        
        st.subheader("Stanowiska do wyszukiwania")
        job_titles_input = st.text_area(
            "Nazwy stanowisk (po jednej w linii)",
            "M&A\nM and A\ncorporate development\nstrategy\nstrategic\ngrowth\nmerger\nacquisition\ndeal\norigination",
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
                
                # Optymalizowane wyszukiwanie z automatycznym sprawdzaniem emaili
                valid_contacts = rr_api.search_people_with_emails(website, job_titles, exclude_titles)
                
                result_row = {"Website": website}
                
                if not valid_contacts:
                    result_row["Status"] = "Nie znaleziono kontaktów z prawidłowymi emailami"
                    for j in range(1, 6):
                        result_row.update({
                            f"Imię i nazwisko osoby {j}": "",
                            f"Stanowisko osoby {j}": "",
                            f"Email osoby {j}": "",
                            f"LinkedIn URL osoby {j}": "",
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
                            f"Grade emaila osoby {j}": contact.get('email_grade', ''),
                            f"SMTP Valid osoby {j}": contact.get('smtp_valid', '')
                        })
                    
                    # Wypełnij pozostałe puste kolumny
                    for j in range(len(valid_contacts) + 1, 6):
                        result_row.update({
                            f"Imię i nazwisko osoby {j}": "",
                            f"Stanowisko osoby {j}": "",
                            f"Email osoby {j}": "",
                            f"LinkedIn URL osoby {j}": "",
                            f"Grade emaila osoby {j}": "",
                            f"SMTP Valid osoby {j}": ""
                        })
                
                results.append(result_row)
                progress_bar.progress((i + 1) / len(websites))
                
                # Dodaj opóźnienie między firmami dla dodatkowej ostrożności
                if i < len(websites) - 1:  # Nie czekaj po ostatniej firmie
                    time.sleep(random.uniform(2, 4))
            
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
        st.warning("⚠️ Wprowadź klucz API RocketReach w panelu bocznym")
    elif not websites:
        st.info("📝 Wprowadź dane firm do analizy")

if __name__ == "__main__":
    main()
