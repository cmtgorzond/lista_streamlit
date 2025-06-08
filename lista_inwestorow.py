import streamlit as st
import pandas as pd
import requests
import re
from typing import List

def extract_domain(url: str) -> str:
    """Wyodrębnia czystą domenę z URL"""
    url = url.strip().lower()
    if not url.startswith(('http://', 'https://')):
        url = f'http://{url}'
    
    # Usuń ścieżki, parametry i subdomenę 'www'
    domain = re.search(
        r'(?:https?://)?(?:www\.)?([^/.:]+?\.[a-z]{2,})(?:/|:|$)',
        url
    )
    return domain.group(1) if domain else url

def search_people(api_key: str, domain: str, titles: List[str], exclude_titles: List[str]) -> List[dict]:
    """Wyszukuje osoby wg domeny i stanowisk"""
    headers = {
        "Api-Key": api_key,
        "Content-Type": "application/json",
        "accept": "application/json"
    }
    
    all_results = []
    
    for title in titles:
        try:
            payload = {
                "query": {
                    "current_title": [f'"{title}"'],  # Dokładne dopasowanie frazy
                    "current_employer_domain": [domain]
                },
                "start": 1,
                "page_size": 5  # Maksymalna liczba wyników na stanowisko
            }
            
            response = requests.post(
                "https://api.rocketreach.co/api/v2/person/search",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                for person in data.get('profiles', []):
                    # Filtruj wykluczone stanowiska
                    if any(excl.lower() in person.get('current_title', '').lower() for excl in exclude_titles):
                        continue
                    all_results.append({
                        "name": person.get('name'),
                        "title": person.get('current_title'),
                        "company": person.get('current_employer'),
                        "linkedin": person.get('linkedin_url'),
                        "id": person.get('id')
                    })
        except Exception as e:
            st.error(f"Błąd dla stanowiska {title}: {str(e)}")
    
    return all_results[:5]  # Ogranicz do 5 wyników

def main():
    st.set_page_config(page_title="🔍 RocketReach Searcher", layout="wide")
    st.title("🔍 Wyszukiwarka kontaktów - People Search API")
    
    # Panel boczny
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        api_key = st.text_input("Wprowadź API Key", type="password")
        
        st.subheader("Filtry stanowisk")
        titles = st.text_area(
            "Szukane stanowiska (jedno w linii)",
            "M&A\nM and A\ncorporate development\nstrategy\ngrowth",
            height=150
        ).split('\n')
        
        exclude_titles = st.text_area(
            "Wykluczane stanowiska (jedno w linii)",
            height=100
        ).split('\n')
    
    # Główny panel
    st.header("📁 Prześlij plik CSV")
    uploaded_file = st.file_uploader("Wybierz plik z listą URL firm", type=['csv'])
    
    if uploaded_file and api_key:
        try:
            df = pd.read_csv(uploaded_file)
            websites = df.iloc[:, 0].dropna().tolist()
            
            if st.button("🔍 Rozpocznij wyszukiwanie", type="primary"):
                results = []
                
                for website in websites:
                    domain = extract_domain(website)
                    people = search_people(api_key, domain, titles, exclude_titles)
                    
                    if not people:
                        results.append({
                            "Strona": website,
                            "Status": "Nie znaleziono",
                            "Liczba wyników": 0
                        })
                    else:
                        results.append({
                            "Strona": website,
                            "Status": "Znaleziono",
                            "Liczba wyników": len(people),
                            **{f"Osoba {i+1}": f"{p['name']} ({p['title']})" for i, p in enumerate(people)}
                        })
                
                results_df = pd.DataFrame(results)
                st.dataframe(results_df)
                
                # Eksport wyników
                csv = results_df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                st.download_button(
                    "💾 Pobierz wyniki",
                    csv,
                    "people_search_results.csv",
                    "text/csv"
                )
        
        except Exception as e:
            st.error(f"Błąd przetwarzania pliku: {str(e)}")

if __name__ == "__main__":
    main()
