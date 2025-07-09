import streamlit as st
import pandas as pd
import requests
import time
import random
import re
from typing import List, Dict
from functools import lru_cache
from urllib.parse import urlparse

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
        self.request_history = []
        self.cache = {}
        self.email_cache = {}

    def _extract_domain(self, url_or_email: str) -> str:
        """Wyciągnij domenę z URL lub emaila"""
        if '@' in url_or_email:
            # To jest email
            return url_or_email.split('@')[1].lower()
        else:
            # To jest URL
            if not url_or_email.startswith(('http://', 'https://')):
                url_or_email = f'https://{url_or_email}'
            
            parsed = urlparse(url_or_email)
            domain = parsed.netloc.lower()
            # Usuń www. jeśli jest
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain

    def _rate_limit_delay(self):
        """Dynamiczne opóźnienie bazujące na historii requestów"""
        now = time.time()
        # Śledzenie ostatnich 60 sekund
        self.request_history = [t for t in self.request_history if t > now - 60]
        
        # RocketReach limit: 45 requestów/minutę
        if len(self.request_history) >= 40:  # Bezpieczny margines
            sleep_time = 60 - (now - self.request_history[0]) + random.uniform(1, 3)
            st.warning(f"⏳ Osiągnięto limit RPM. Czekam {sleep_time:.1f}s...")
            time.sleep(sleep_time)
            self.request_history = []

    def _make_request(self, method: str, endpoint: str, **kwargs):
        """Uniwersalna metoda do requestów z retry logic i cache'owaniem"""
        # Tworzenie klucza cache dla GET requestów
        cache_key = None
        if method == "GET" and "params" in kwargs:
            cache_key = f"{endpoint}_{str(kwargs['params'])}"
            if cache_key in self.cache:
                return self.cache[cache_key]

        max_retries = 3
        backoff_factor = 1.5
        
        for attempt in range(max_retries):
            self._rate_limit_delay()
            
            try:
                response = requests.request(
                    method,
                    f"{self.base_url}{endpoint}",
                    headers=self.headers,
                    timeout=30,
                    **kwargs
                )
                
                if response.status_code == 429:
                    try:
                        error_data = response.json()
                        retry_after = float(error_data.get('wait', 60))
                    except:
                        retry_after = float(response.headers.get('Retry-After', 60))
                    
                    st.warning(f"⏳ Limit API. Czekam {retry_after:.0f}s...")
                    time.sleep(retry_after + random.uniform(1, 3))
                    continue
                    
                if response.status_code in [200, 201]:
                    self.request_history.append(time.time())
                    result = response.json()
                    
                    # Cache dla GET requestów
                    if cache_key:
                        self.cache[cache_key] = result
                    
                    return result
                else:
                    st.error(f"Błąd API {response.status_code}: {response.text}")
                    return {}
                
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    st.error(f"Błąd połączenia: {str(e)}")
                    return {}
                delay = backoff_factor ** attempt + random.uniform(0.5, 1.5)
                time.sleep(delay)
                
        return {}

    def search_people_with_emails(self, company_url: str, titles: List[str], exclude_titles: List[str]) -> List[Dict]:
        """Zoptymalizowane wyszukiwanie osób z weryfikacją domeny emaila"""
        try:
            valid_contacts = []
            company_domain = self._extract_domain(company_url)
            
            # ETAP 1: Wyszukiwanie po stanowiskach (wszystkie tytuły w jednym zapytaniu)
            st.info("🔍 Etap 1: Wyszukiwanie po stanowiskach...")
            title_results = self._search_optimized(company_url, "current_title", titles, exclude_titles)
            
            # Sprawdź emaile dla wyników z stanowisk
            for person in title_results:
                if len(valid_contacts) >= 3:  # Zmiana: tylko 3 kontakty
                    break
                    
                contact_with_email = self._get_person_with_verified_email(person, company_domain)
                
                if contact_with_email:
                    valid_contacts.append(contact_with_email)
                    st.success(f"✅ Znaleziono kontakt przez stanowisko: {contact_with_email.get('name')} - {contact_with_email.get('title')} | {contact_with_email.get('email')} (Grade: {contact_with_email.get('email_grade', 'N/A')}, SMTP: {contact_with_email.get('smtp_valid', 'N/A')})")
            
            # ETAP 2: Jeśli mniej niż 3 kontaktów, szukaj po skills
            if len(valid_contacts) < 3:
                st.info(f"🎯 Etap 2: Znaleziono {len(valid_contacts)} kontaktów. Rozszerzam wyszukiwanie o umiejętności...")
                skill_results = self._search_optimized(company_url, "skills", titles, exclude_titles)
                
                # Sprawdź emaile dla wyników z skills (pomijając już znalezione)
                existing_ids = {contact.get('id') for contact in valid_contacts if 'id' in contact}
                
                for person in skill_results:
                    if len(valid_contacts) >= 3:  # Zmiana: tylko 3 kontakty
                        break
                    
                    # Pomiń jeśli już mamy tę osobę
                    if person['id'] in existing_ids:
                        continue
                        
                    contact_with_email = self._get_person_with_verified_email(person, company_domain)
                    
                    if contact_with_email:
                        valid_contacts.append(contact_with_email)
                        st.success(f"✅ Znaleziono kontakt przez umiejętności: {contact_with_email.get('name')} - {contact_with_email.get('title')} | {contact_with_email.get('email')} (Grade: {contact_with_email.get('email_grade', 'N/A')}, SMTP: {contact_with_email.get('smtp_valid', 'N/A')})")
            
            st.info(f"📊 Łącznie znaleziono {len(valid_contacts)} kontaktów z prawidłowymi emailami")
            return valid_contacts[:3]  # Zmiana: maksymalnie 3 kontakty
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania: {str(e)}")
            return []

    def _get_person_with_verified_email(self, person: Dict, company_domain: str) -> Dict:
        """Pobierz dane osoby i zweryfikuj domenę emaila"""
        try:
            # Sprawdź czy już mamy email w cache
            person_id = person['id']
            if person_id in self.email_cache:
                cached_result = self.email_cache[person_id]
                if cached_result.get('email'):
                    email_domain = self._extract_domain(cached_result['email'])
                    if email_domain == company_domain:
                        return {**person, **cached_result}
                return None
            
            # Pobierz szczegóły osoby
            details = self.lookup_person_details(person_id)
            
            # Cache wynik
            self.email_cache[person_id] = details
            
            if not details.get('email') or details.get('smtp_valid') == 'invalid':
                return None
            
            # Weryfikacja domeny emaila
            email_domain = self._extract_domain(details['email'])
            if email_domain != company_domain:
                st.info(f"⚠️ Email {details['email']} ma inną domenę ({email_domain}) niż firma ({company_domain}) - pomijam")
                return None
            
            # Połącz dane
            return {**person, **details}
            
        except Exception as e:
            st.error(f"Błąd weryfikacji emaila: {str(e)}")
            return None

    def _search_optimized(self, company_url: str, field: str, values: List[str], exclude_values: List[str]) -> List[Dict]:
        """Zoptymalizowane wyszukiwanie z minimalnym zużyciem tokenów"""
        try:
            if not company_url.startswith(('http://', 'https://')):
                company_url = f'https://{company_url}'
            
            # Filtruj puste wartości
            clean_values = [v.strip() for v in values if v.strip()]
            clean_exclude = [v.strip() for v in exclude_values if v.strip()]
            
            if not clean_values:
                return []
            
            # Przygotuj payload z wszystkimi tytułami naraz - OPTYMALIZACJA TOKENÓW
            payload = {
                "query": {
                    "company_domain": [company_url],
                    field: clean_values  # Wszystkie tytuły w jednym zapytaniu
                },
                "start": 1,
                "page_size": 25,  # Zmniejszono z 50 do 25 dla optymalizacji
                "fields": ["id", "name", "current_title", "current_employer", "linkedin_url", "skills"]  # Tylko potrzebne pola
            }
            
            # Dodaj wykluczenia jeśli istnieją
            if clean_exclude:
                exclude_field = f"exclude_{field}" if field != "skills" else "exclude_current_title"
                payload["query"][exclude_field] = clean_exclude
            
            data = self._make_request("POST", "/api/v2/person/search", json=payload)
            
            results = []
            for person in data.get('profiles', []):
                # Dodatkowe filtrowanie po stronie klienta
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
            
            return results[:10]  # Ogranicz do 10 kandydatów dla optymalizacji
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania po {field}: {str(e)}")
            return []

    def lookup_person_details(self, person_id: int) -> Dict:
        """Zoptymalizowane pobieranie szczegółów osoby"""
        try:
            # Sprawdź cache
            if person_id in self.email_cache:
                return self.email_cache[person_id]
            
            params = {
                "id": person_id,
                "lookup_type": "standard",
                "fields": ["emails", "name", "current_title", "linkedin_url", "current_employer"]  # Tylko potrzebne pola
            }
            
            data = self._make_request("GET", "/api/v2/person/lookup", params=params)
            
            if data:
                result = self._process_email_data(data, person_id)
                self.email_cache[person_id] = result
                return result
            
            return {}
                
        except Exception as e:
            st.error(f"Błąd pobierania szczegółów: {str(e)}")
            return {}

    def _process_email_data(self, data: Dict, person_id: int) -> Dict:
        """Zoptymalizowane przetwarzanie danych emaila"""
        professional_email = ""
        email_grade = ""
        smtp_valid = ""
        
        # Hierarchia wyboru emaila
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
                
                # Zoptymalizowane wyszukiwanie z weryfikacją domeny emaila
                valid_contacts = rr_api.search_people_with_emails(website, job_titles, exclude_titles)
                
                result_row = {"Website": website}
                
                if not valid_contacts:
                    result_row["Status"] = "Nie znaleziono kontaktów z prawidłowymi emailami"
                    for j in range(1, 4):  # Zmiana: tylko 3 kontakty
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
                    
                    for j, contact in enumerate(valid_contacts[:3], 1):  # Zmiana: tylko 3 kontakty
                        result_row.update({
                            f"Imię i nazwisko osoby {j}": contact.get('name', ''),
                            f"Stanowisko osoby {j}": contact.get('title', ''),
                            f"Email osoby {j}": contact.get('email', ''),
                            f"LinkedIn URL osoby {j}": contact.get('linkedin', ''),
                            f"Grade emaila osoby {j}": contact.get('email_grade', ''),
                            f"SMTP Valid osoby {j}": contact.get('smtp_valid', '')
                        })
                    
                    # Wypełnij pozostałe puste kolumny
                    for j in range(len(valid_contacts) + 1, 4):  # Zmiana: tylko 3 kontakty
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
                
                # Opóźnienie między firmami dla stabilności API
                if i < len(websites) - 1:
                    time.sleep(random.uniform(1, 2))
            
            status_text.text("✅ Analiza zakończona!")
            
            # Wyświetl wyniki
            st.subheader("📋 Wyniki wyszukiwania")
            results_df = pd.DataFrame(results)
            st.dataframe(results_df, use_container_width=True)
            
            # Statystyki
            st.subheader("📊 Statystyki")
            total_contacts = sum(1 for result in results 
                               for j in range(1, 4)  # Zmiana: tylko 3 kontakty
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
