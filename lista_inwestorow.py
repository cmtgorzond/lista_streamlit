import streamlit as st
import pandas as pd
import requests
import re
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

    def search_people(self, domain: str, titles: List[str], exclude_titles: List[str]) -> List[Dict]:
        try:
            all_results = []
            clean_domain = re.sub(r"^https?://(www\.)?", "", domain).split('/')[0]
            
            for title in titles:
                payload = {
                    "query": {
                        "current_title": [title],
                        "current_employer_domain": [clean_domain]
                    },
                    "start": 1,
                    "page_size": 5
                }
                
                response = requests.post(
                    f"{self.base_url}/api/v2/person/search",
                    headers=self.headers,
                    json=payload
                )
                
                if response.status_code == 201:  # Zmiana na 201 Created
                    data = response.json()
                    for person in data.get('profiles', []):
                        if any(excl.lower() in person.get('current_title', '').lower() for excl in exclude_titles):
                            continue
                        all_results.append({
                            "id": person.get('id'),
                            "name": person.get('name'),
                            "title": person.get('current_title'),
                            "linkedin": person.get('linkedin_url')
                        })
                time.sleep(0.5)
            
            return all_results[:5]
        
        except Exception as e:
            st.error(f"Błąd wyszukiwania: {str(e)}")
            return []

    def lookup_email(self, person_id: int) -> Dict:
        try:
            response = requests.get(
                f"{self.base_url}/api/v2/person/lookup",
                headers=self.headers,
                params={"id": person_id, "lookup_type": "standard"}
            )
            
            if response.status_code == 200:
                data = response.json()
                emails = [e['email'] for e in data.get('emails', []) 
                         if e.get('type') == 'professional' and e.get('smtp_valid') == 'valid']
                
                return {
                    "email": emails[0] if emails else '',
                    "linkedin": data.get('linkedin_url', '')
                }
            return {}
        
        except Exception as e:
            st.error(f"Błąd pobierania emaila: {str(e)}")
            return {}

def main():
    st.set_page_config(page_title="🚀 RocketReach Pro", layout="wide")
    st.title("🚀 Wyszukiwarka Kontaktów RocketReach Pro")
    
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        api_key = st.text_input("API Key RocketReach", type="password")
        
        st.subheader("Filtry stanowisk")
        job_titles = st.text_area(
            "Szukane stanowiska (po jednej w linii)",
            "sales\nM&A\ncorporate development\nstrategy\ngrowth",
            height=150
        ).split('\n')
        
        exclude_titles = st.text_area(
            "Wykluczane stanowiska (po jednej w linii)",
            height=100
        ).split('\n')

    st.header("📁 Prześlij plik CSV")
    uploaded_file = st.file_uploader("Wybierz plik z listą URL firm", type=['csv'])
    
    if uploaded_file and api_key:
        try:
            df = pd.read_csv(uploaded_file)
            websites = df.iloc[:, 0].dropna().tolist()
            
            if st.button("🚀 Rozpocznij wyszukiwanie", type="primary"):
                rr_api = RocketReachAPI(api_key)
                results = []
                progress_bar = st.progress(0)
                
                for i, website in enumerate(websites):
                    domain = website.strip()
                    people = rr_api.search_people(domain, job_titles, exclude_titles)
                    
                    result_row = {"Strona": domain}
                    if not people:
                        result_row["Status"] = "Nie znaleziono kontaktów"
                        for j in range(1, 6):
                            result_row.update({
                                f"Osoba {j}": "",
                                f"Email {j}": "",
                                f"LinkedIn {j}": ""
                            })
                    else:
                        result_row["Status"] = f"Znaleziono {len(people)} kontaktów"
                        for j, person in enumerate(people[:5], 1):
                            details = rr_api.lookup_email(person['id'])
                            time.sleep(1)  # Rate limiting
                            
                            result_row.update({
                                f"Osoba {j}": person['name'],
                                f"Stanowisko {j}": person['title'],
                                f"Email {j}": details.get('email', ''),
                                f"LinkedIn {j}": details.get('linkedin', '')
                            })
                            
                        # Wypełnij puste pozycje
                        for j in range(len(people)+1, 6):
                            result_row.update({
                                f"Osoba {j}": "",
                                f"Email {j}": "",
                                f"LinkedIn {j}": ""
                            })
                    
                    results.append(result_row)
                    progress_bar.progress((i + 1) / len(websites))
                
                results_df = pd.DataFrame(results)
                st.dataframe(results_df)
                
                csv = results_df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                st.download_button(
                    "💾 Pobierz wyniki",
                    data=csv,
                    file_name="rocketreach_wyniki.csv",
                    mime="text/csv"
                )
        
        except Exception as e:
            st.error(f"Błąd: {str(e)}")

if __name__ == "__main__":
    main()
