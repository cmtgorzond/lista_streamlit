import streamlit as st
import pandas as pd
import requests
import time
import re
from typing import List, Dict, Optional

class RocketReachAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co"
        self.headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json"
        }

    def search_people_by_domain(self, domain: str, job_titles: List[str], exclude_titles: List[str] = None) -> List[Dict]:
        try:
            all_results = []
            
            for title in job_titles:
                search_params = {
                    "query": {
                        "current_title": [title],
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
                            if exclude_titles and any(excl.lower() in person.get('current_title', '').lower() for excl in exclude_titles):
                                continue
                            all_results.append(person)
                time.sleep(0.5)
            
            return all_results[:5]
        
        except Exception as e:
            st.error(f"Błąd podczas wyszukiwania osób: {str(e)}")
            return []

    def lookup_person_by_id(self, person_id: int) -> Dict:
        try:
            response = requests.get(
                f"{self.base_url}/api/v2/person/lookup",
                headers=self.headers,
                params={"id": person_id, "lookup_type": "standard"}
            )
            
            if response.status_code == 200:
                return response.json()
            return {}
        
        except Exception as e:
            st.error(f"Błąd podczas pobierania szczegółów osoby: {str(e)}")
            return {}

def extract_domain(url: str) -> str:
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    if match:
        domain = match.group(1).lower()
        return domain.split('/')[0]  # Usuń ścieżki po domenie
    return url

def main():
    st.set_page_config(page_title="🚀 RocketReach Contact Finder", layout="wide")
    st.title("🚀 RocketReach Contact Finder")
    
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        api_key = st.text_input("RocketReach API Key", type="password")
        
        st.subheader("Stanowiska do wyszukiwania")
        job_titles_input = st.text_area(
            "Nazwy stanowisk (po jednej w linii)",
            value="\n".join(["M&A", "M and A", "corporate development", "strategy", "strategic", "growth", "merger"]),
            height=150
        )
        job_titles = [t.strip() for t in job_titles_input.split('\n') if t.strip()]
        
        st.subheader("Stanowiska do wykluczenia")
        exclude_titles = [t.strip() for t in st.text_area(
            "Nazwy stanowisk do wykluczenia (po jednej w linii)",
            height=100
        ).split('\n') if t.strip()]

    st.header("📁 Upload pliku CSV")
    uploaded_file = st.file_uploader("Wybierz plik CSV ze stronami internetowymi firm", type=['csv'])
    
    if uploaded_file and api_key:
        try:
            df = pd.read_csv(uploaded_file)
            websites = df.iloc[:, 0].dropna().tolist()
            
            if st.button("🚀 Rozpocznij wyszukiwanie", type="primary"):
                rr_api = RocketReachAPI(api_key)
                results = []
                progress_bar = st.progress(0)
                
                for i, website in enumerate(websites):
                    domain = extract_domain(website)
                    people = rr_api.search_people_by_domain(domain, job_titles, exclude_titles)
                    
                    result_row = {"Website": website}
                    if not people:
                        result_row["Status"] = "Nie znaleziono kontaktów"
                        for j in range(1, 6):
                            result_row.update({f"Osoba {j}": "", f"Email {j}": "", f"LinkedIn {j}": ""})
                    else:
                        result_row["Status"] = f"Znaleziono {len(people)} kontaktów"
                        for j, person in enumerate(people[:5], 1):
                            details = rr_api.lookup_person_by_id(person['id'])
                            email = details.get('recommended_professional_email') or \
                                    details.get('current_work_email') or \
                                    next((e['email'] for e in details.get('emails', []) if e['type'] == 'professional'), '')
                            
                            result_row.update({
                                f"Osoba {j}": details.get('name', ''),
                                f"Stanowisko {j}": details.get('current_title', ''),
                                f"Email {j}": email,
                                f"LinkedIn {j}": details.get('linkedin_url', '')
                            })
                            time.sleep(1)
                    
                    results.append(result_row)
                    progress_bar.progress((i + 1) / len(websites))
                
                results_df = pd.DataFrame(results)
                st.dataframe(results_df)
                
                csv = results_df.to_csv(index=False)
                st.download_button("📥 Pobierz wyniki", csv, "rocketreach_results.csv")
        
        except Exception as e:
            st.error(f"Błąd: {str(e)}")

if __name__ == "__main__":
    main()
