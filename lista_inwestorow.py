import streamlit as st
import pandas as pd
import requests
import time
import re
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

    def search_people(self, domain: str, job_titles: List[str], exclude_titles: List[str]) -> List[Dict]:
        try:
            all_results = []
            
            for title in job_titles:
                search_params = {
                    "query": {
                        "current_title": [f'"{title}"'],
                        "current_employer_domain": [domain]
                    },
                    "start": 1,
                    "page_size": 5
                }
                
                response = requests.post(
                    f"{self.base_url}/api/v2/person/search",
                    headers=self.headers,
                    json=search_params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'profiles' in data:
                        for person in data['profiles']:
                            current_title = person.get('current_title', '').lower()
                            if any(excl.lower() in current_title for excl in exclude_titles):
                                continue
                            all_results.append(person)
                time.sleep(1)
            
            return all_results

        except Exception as e:
            st.error(f"Błąd wyszukiwania: {str(e)}")
            return []

    def lookup_person(self, person_id: int) -> Dict:
        try:
            response = requests.get(
                f"{self.base_url}/api/v2/person/lookup",
                headers=self.headers,
                params={"id": person_id, "lookup_type": "standard"}
            )
            return response.json() if response.status_code == 200 else {}
        except Exception as e:
            st.error(f"Błąd pobierania danych: {str(e)}")
            return {}

def extract_domain(url: str) -> str:
    url = url.strip().lower()
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    
    match = re.match(
        r'^(?:https?://)?(?:www\.)?([^/.:]+)\.([a-z]{2,})(?:/|$)', 
        url,
        re.IGNORECASE
    )
    return f"{match.group(1)}.{match.group(2)}" if match else url

def main():
    st.set_page_config(page_title="🚀 RocketReach Contact Finder Pro", layout="wide")
    st.title("🚀 RocketReach Contact Finder Pro")
    
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        api_key = st.text_input("API Key RocketReach", type="password")
        
        st.subheader("Filtry stanowisk")
        job_titles = st.text_area(
            "Szukane stanowiska (po jednej w linii)",
            value="sales\nM&A\ncorporate development",
            height=150
        ).split('\n')
        
        exclude_titles = st.text_area(
            "Wykluczane stanowiska (po jednej w linii)",
            height=100
        ).split('\n')

    st.header("📁 Prześlij plik CSV")
    uploaded_file = st.file_uploader("Wybierz plik z listą stron firmowych", type=['csv'])
    
    if uploaded_file and api_key:
        try:
            df = pd.read_csv(uploaded_file)
            websites = df.iloc[:, 0].dropna().tolist()
            
            if st.button("🔍 Rozpocznij wyszukiwanie", type="primary"):
                rr_api = RocketReachAPI(api_key)
                results = []
                progress = st.progress(0)
                
                for idx, website in enumerate(websites):
                    domain = extract_domain(website)
                    people = rr_api.search_people(domain, job_titles, exclude_titles)
                    
                    result_row = {"Strona": website}
                    if people:
                        result_row["Status"] = f"Znaleziono {len(people)} kontaktów"
                        for i, person in enumerate(people[:5], 1):
                            details = rr_api.lookup_person(person['id'])
                            email = next(
                                (e['email'] for e in details.get('emails', []) 
                                if e.get('type') == 'professional' and e.get('smtp_valid') == 'valid'),
                                ''
                            )
                            result_row.update({
                                f"Osoba {i}": details.get('name'),
                                f"Stanowisko {i}": details.get('current_title'),
                                f"Email {i}": email,
                                f"LinkedIn {i}": details.get('linkedin_url')
                            })
                            time.sleep(1.5)
                    else:
                        result_row.update({
                            "Status": "Nie znaleziono",
                            **{f"Osoba {i}": "" for i in range(1,6)},
                            **{f"Email {i}": "" for i in range(1,6)},
                            **{f"LinkedIn {i}": "" for i in range(1,6)}
                        })
                    
                    results.append(result_row)
                    progress.progress((idx + 1) / len(websites))
                
                results_df = pd.DataFrame(results)
                st.dataframe(results_df)
                
                csv = results_df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                st.download_button(
                    "💾 Pobierz wyniki",
                    csv,
                    "rocketreach_wyniki.csv",
                    "text/csv"
                )

        except Exception as e:
            st.error(f"Krytyczny błąd: {str(e)}")

if __name__ == "__main__":
    main()
