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
                        "company_domain": [company_url],
                        "current_title": [title.strip()]
                    },
                    "start": 1,
                    "page_size": 20  # Zwiększono limit aby mieć więcej opcji
                }
                
                response = requests.post(
                    f"{self.base_url}/api/v2/person/search",
                    headers=self.headers,
                    json=payload
                )
                
                if response.status_code == 201:
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
                
                # Hierarchia wyboru emaila:
                # 1. recommended_professional_email
                # 2. current_work_email
                # 3. Najlepszy email zawodowy z listy emails
                
                professional_email = ""
                email_grade = ""
                
                # Pierwsza opcja: recommended_professional_email
                if data.get('recommended_professional_email'):
                    professional_email = data.get('recommended_professional_email')
                    # Znajdź grade dla tego emaila
                    for email_obj in data.get('emails', []):
                        if email_obj.get('email') == professional_email:
                            email_grade = email_obj.get('grade', '')
                            break
                
                # Druga opcja: current_work_email
                elif data.get('current_work_email'):
                    professional_email = data.get('current_work_email')
                    # Znajdź grade dla tego emaila
                    for email_obj in data.get('emails', []):
                        if email_obj.get('email') == professional_email:
                            email_grade = email_obj.get('grade', '')
                            break
                
                # Trzecia opcja: najlepszy email zawodowy z listy
                elif 'emails' in data:
                    # Sortuj emaile zawodowe według grade (A > A- > B > B- > C > D > F)
                    grade_order = {'A': 1, 'A-': 2, 'B': 3, 'B-': 4, 'C': 5, 'D': 6, 'F': 7}
                    
                    professional_emails = [
                        email_obj for email_obj in data['emails']
                        if email_obj.get('type') == 'professional'
                    ]
                    
                    if professional_emails:
                        # Sortuj według grade
                        professional_emails.sort(
                            key=lambda x: grade_order.get(x.get('grade', 'F'), 8)
                        )
                        
                        best_email = professional_emails[0]
                        professional_email = best_email.get('email', '')
                        email_grade = best_email.get('grade', '')
                
                return {
                    "name": data.get('name', ''),
                    "title": data.get('current_title', ''),
                    "email": professional_email,
                    "email_grade": email_grade,
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
    st.set_page_config(page_title="🚀 RocketReach Contact Finder Pro", layout="wide")
    st.title("🚀 RocketReach Contact Finder Pro")
    st.markdown("Aplikacja do wyszukiwania kontaktów w firmach z zaawansowanymi filtrami")
    
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
    
    else:  # Ręczne wpisanie domeny
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
                            f"Grade emaila osoby {j}": "",
                            f"LinkedIn URL osoby {j}": ""
                        })
                else:
                    # Pobierz szczegółowe dane i filtruj osoby z emailami
                    valid_contacts = []
                    
                    for person in people:
                        details = rr_api.lookup_person_details(person['id'])
                        time.sleep(1)  # Rate limiting
                        
                        # Dodaj tylko osoby z emailem
                        if details.get('email'):
                            valid_contacts.append(details)
                        
                        # Przerwij jeśli mamy już 5 kontaktów
                        if len(valid_contacts) >= 5:
                            break
                    
                    if not valid_contacts:
                        result_row["Status"] = "Nie znaleziono kontaktów z emailami"
                        # Wypełnij puste kolumny
                        for j in range(1, 6):
                            result_row.update({
                                f"Imię i nazwisko osoby {j}": "",
                                f"Stanowisko osoby {j}": "",
                                f"Email osoby {j}": "",
                                f"Grade emaila osoby {j}": "",
                                f"LinkedIn URL osoby {j}": ""
                            })
                    else:
                        result_row["Status"] = f"Znaleziono {len(valid_contacts)} kontakt(ów) z emailami"
                        
                        # Dodaj dane kontaktów
                        for j, contact in enumerate(valid_contacts[:5], 1):
                            result_row.update({
                                f"Imię i nazwisko osoby {j}": contact.get('name', ''),
                                f"Stanowisko osoby {j}": contact.get('title', ''),
                                f"Email osoby {j}": contact.get('email', ''),
                                f"Grade emaila osoby {j}": contact.get('email_grade', ''),
                                f"LinkedIn URL osoby {j}": contact.get('linkedin', '')
                            })
                        
                        # Wypełnij pozostałe puste kolumny
                        for j in range(len(valid_contacts) + 1, 6):
                            result_row.update({
                                f"Imię i nazwisko osoby {j}": "",
                                f"Stanowisko osoby {j}": "",
                                f"Email osoby {j}": "",
                                f"Grade emaila osoby {j}": "",
                                f"LinkedIn URL osoby {j}": ""
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
            csv = results_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                "📥 Pobierz wyniki jako CSV",
                data=csv,
                file_name="rocketreach_results.csv",
                mime="text/csv"
            )
    
    elif not api_key:
        st.warning("⚠️ Wprowadź klucz API RocketReach")
    elif not websites:
        st.info("📝 Wprowadź dane firm do analizy")

    # Informacje o aplikacji
    with st.expander("ℹ️ Informacje o aplikacji"):
        st.markdown("""
        ### Nowe funkcjonalności:
        
        - **Filtrowanie kontaktów**: Pomijane są osoby bez adresów email
        - **Grade emaila**: Wyświetlana jest ocena jakości emaila (A, A-, B, B-, C, D, F)
        - **Hierarchia emaili**: 
          1. recommended_professional_email
          2. current_work_email  
          3. Najlepszy email zawodowy z listy
        - **Ręczne wprowadzanie domen**: Możliwość testowania pojedynczych firm
        - **Rozszerzone wyszukiwanie**: Zwiększony limit wyników dla lepszego filtrowania
        - **Statystyki**: Podsumowanie wyników wyszukiwania
        """)

if __name__ == "__main__":
    main()
