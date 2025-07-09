import streamlit as st
import pandas as pd
import requests
import time
import random
import re
from typing import List, Dict
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

def extract_domain(url: str) -> str:
    """Wyciąga czystą domenę z URL"""
    if '@' in url:
        return url.split('@')[1].lower()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc

class RocketReachAPI:
    def __init__(self, api_key: str, webhook_id: str = None):
        self.api_key = api_key
        self.webhook_id = webhook_id
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

    def search_people_profiles(self, company_url: str, titles: List[str], exclude_titles: List[str]) -> List[Dict]:
        """Wyszukaj profile bez lookupów - zwraca tylko podstawowe dane"""
        try:
            all_results = []
            
            # ETAP 1: Wyszukiwanie po stanowiskach
            st.info("🔍 Etap 1: Wyszukiwanie po stanowiskach...")
            title_results = self._search_optimized(company_url, "current_title", titles, exclude_titles)
            all_results.extend(title_results[:10])
            
            # ETAP 2: Jeśli mało wyników, szukaj po skills
            if len(all_results) < 10:
                st.info(f"🎯 Etap 2: Znaleziono {len(all_results)} profili. Rozszerzam wyszukiwanie o umiejętności...")
                skill_results = self._search_optimized(company_url, "skills", titles, exclude_titles)
                
                # Dodaj tylko unikalne wyniki
                existing_ids = {result['id'] for result in all_results}
                for result in skill_results:
                    if result['id'] not in existing_ids:
                        all_results.append(result)
                        if len(all_results) >= 10:
                            break
            
            st.info(f"📊 Znaleziono {len(all_results)} profili do sprawdzenia")
            return all_results[:5]  # Zwróć maksymalnie 5 profili
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania: {str(e)}")
            return []

    def _search_optimized(self, company_url: str, field: str, values: List[str], exclude_values: List[str]) -> List[Dict]:
        """Optymalizowane wyszukiwanie z batchowaniem wszystkich tytułów"""
        try:
            self._rate_limit_check()
            
            domain = extract_domain(company_url)
            
            # Filtruj puste wartości
            clean_values = [v.strip() for v in values if v.strip()]
            clean_exclude = [v.strip() for v in exclude_values if v.strip()]
            
            if not clean_values:
                return []
            
            # Przygotuj payload z wszystkimi tytułami naraz
            payload = {
                "query": {
                    "company_domain": [domain],
                    field: clean_values  # Wszystkie tytuły w jednym zapytaniu
                },
                "start": 1,
                "page_size": 25,
                "fields": ["id", "name", "current_title", "current_employer", "linkedin_url", "skills"]
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
                    json=payload,
                    timeout=30
                )
                
                if self._handle_rate_limit(response):
                    retry_count += 1
                    continue
                
                elif response.status_code == 201:
                    data = response.json()
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
                    
                    return results
                
                else:
                    st.error(f"Błąd search API: {response.status_code} - {response.text}")
                    break
            
            return []
            
        except Exception as e:
            st.error(f"Błąd wyszukiwania po {field}: {str(e)}")
            return []

    def bulk_lookup(self, ids: List[int]):
        """Wywołaj bulk lookup z webhookiem - POPRAWIONY ENDPOINT Z PODKREŚLENIEM"""
        try:
            self._rate_limit_check()
            
            payload = {
                "profiles": [{"id": pid} for pid in ids],
                "lookup_type": "standard"
            }
            
            if self.webhook_id:
                payload["webhook_id"] = self.webhook_id
            
            response = requests.post(
                f"{self.base_url}/api/v2/person/bulk_lookup",  # POPRAWIONY ENDPOINT Z PODKREŚLENIEM
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code in (200, 201, 202):  # Akceptuj wszystkie kody sukcesu
                if self.webhook_id:
                    st.success("🔔 Bulk lookup wysłany, wyniki przyjdą na webhook")
                else:
                    st.info("📋 Bulk lookup wykonany synchronicznie")
                    return response.json()
            else:
                st.error(f"Bulk lookup error {response.status_code}: {response.text}")
                return {}
                
        except Exception as e:
            st.error(f"Błąd bulk lookup: {str(e)}")
            return {}

    # Zachowaj oryginalną metodę dla fallback (tryb synchroniczny)
    def lookup_person_details(self, person_id: int) -> Dict:
        """Pojedynczy lookup - używany jako fallback gdy brak webhook"""
        try:
            self._rate_limit_check()
            
            response = requests.get(
                f"{self.base_url}/api/v2/person/lookup",
                headers=self.headers,
                params={
                    "id": person_id,
                    "lookup_type": "standard"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._process_email_data(data, person_id)
            else:
                st.error(f"Błąd lookup API: {response.status_code}")
                return {}
                
        except Exception as e:
            st.error(f"Błąd pobierania szczegółów: {str(e)}")
            return {}

    def _process_email_data(self, data: Dict, person_id: int) -> Dict:
        """Wspólna metoda przetwarzania emaili z hierarchią wyboru"""
        professional_email = ""
        email_grade = ""
        smtp_valid = ""
        
        # Hierarchia wyboru emaila
        if data.get('recommended_professional_email'):
            professional_email = data.get('recommended_professional_email')
            for email_obj in data.get('emails', []):
                if email_obj.get('email') == professional_email:
                    email_grade = email_obj.get('grade', '')
                    smtp_valid = email_obj.get('smtp_valid', '')
                    break
        
        elif data.get('current_work_email'):
            professional_email = data.get('current_work_email')
            for email_obj in data.get('emails', []):
                if email_obj.get('email') == professional_email:
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
                email_grade = best_email.get('grade', '')
                smtp_valid = best_email.get('smtp_valid', '')
        
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
        
        # Pole do wprowadzania Webhook ID
        webhook_id = st.text_input(
            "Webhook ID (opcjonalnie)",
            help="ID webhook z panelu RocketReach dla asynchronicznych wyników"
        )
        
        if webhook_id:
            st.success("🔔 Webhook włączony - wyniki będą wysyłane asynchronicznie")
        else:
            st.info("📋 Tryb synchroniczny - wyniki w czasie rzeczywistym")
        
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
            rr_api = RocketReachAPI(api_key, webhook_id)
            
            if webhook_id:
                # Tryb webhook - tylko wyszukiwanie i bulk lookup
                st.info("🔔 Tryb webhook - wyniki będą wysyłane na Twój endpoint")
                
                for i, website in enumerate(websites):
                    st.write(f"🔍 Analizowanie: {website} ({i+1}/{len(websites)})")
                    
                    # Znajdź profile
                    profiles = rr_api.search_people_profiles(website, job_titles, exclude_titles)
                    
                    if profiles:
                        ids = [p["id"] for p in profiles[:5]]
                        st.write(f"📋 Znaleziono {len(profiles)} profili, wysyłam {len(ids)} do bulk lookup")
                        
                        # Wyświetl znalezione profile
                        for profile in profiles[:5]:
                            st.write(f"• {profile.get('name', 'N/A')} - {profile.get('title', 'N/A')} ({profile.get('company', 'N/A')})")
                        
                        rr_api.bulk_lookup(ids)
                    else:
                        st.write("❌ Brak profili do sprawdzenia")
                    
                    time.sleep(random.uniform(1, 2))
                
                st.success("📬 Wszystkie zapytania wysłane. Sprawdź swój webhook endpoint!")
                st.info("💡 Wyniki z emailami, grade i SMTP validation przyjdą na Twój serwer webhook")
                
            else:
                # Tryb synchroniczny - oryginalny kod
                results = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, website in enumerate(websites):
                    status_text.text(f"Analizowanie: {website} ({i+1}/{len(websites)})")
                    
                    # Znajdź profile
                    profiles = rr_api.search_people_profiles(website, job_titles, exclude_titles)
                    
                    result_row = {"Website": website}
                    
                    if not profiles:
                        result_row["Status"] = "Nie znaleziono profili"
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
                        valid_contacts = []
                        
                        # Synchroniczne lookupy
                        for person in profiles:
                            details = rr_api.lookup_person_details(person['id'])
                            time.sleep(1)  # Rate limiting
                            
                            if details.get('email') and details.get('smtp_valid') != 'invalid':
                                combined_contact = {**person, **details}
                                valid_contacts.append(combined_contact)
                                st.success(f"✅ {details.get('name')} - {details.get('email')} (Grade: {details.get('email_grade', 'N/A')})")
                        
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
                    
                    # Opóźnienie między firmami
                    if i < len(websites) - 1:
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
