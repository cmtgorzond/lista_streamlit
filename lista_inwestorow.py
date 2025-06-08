import streamlit as st
import pandas as pd
import requests
import re
from typing import List

def extract_full_url(url: str) -> str:
    """Zachowuje pełny URL z protokołem"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    return url

def search_people(api_key: str, company_url: str, titles: List[str], exclude_titles: List[str]) -> List[dict]:
    """Wyszukuje osoby według pełnego URL firmy i stanowisk"""
    headers = {
        "Api-Key": api_key,
        "Content-Type": "application/json",
        "accept": "application/json"
    }
    
    all_results = []
    
    for title in titles:
        if not title.strip():
            continue
            
        try:
            payload = {
                "query": {
                    "company_domain": [company_url],  # Użyj company_domain zamiast current_employer_domain
                    "current_title": [title.strip()]  # Bez cudzysłowów
                },
                "start": 1,
                "page_size": 10
            }
            
            st.write(f"Szukam stanowiska: {title} w firmie: {company_url}")
            
            response = requests.post(
                "https://api.rocketreach.co/api/v2/person/search",
                headers=headers,
                json=payload
            )
            
            st.write(f"Status odpowiedzi: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                st.write(f"Odpowiedź API: {data}")
                
                profiles = data.get('profiles', [])
                st.write(f"Znaleziono {len(profiles)} profili")
                
                for person in profiles:
                    current_title = person.get('current_title', '').lower()
                    
                    # Sprawdź wykluczenia
                    if exclude_titles and any(excl.lower() in current_title for excl in exclude_titles if excl.strip()):
                        continue
                        
                    all_results.append({
                        "name": person.get('name'),
                        "title": person.get('current_title'),
                        "company": person.get('current_employer'),
                        "linkedin": person.get('linkedin_url'),
                        "id": person.get('id'),
                        "location": person.get('location')
                    })
            else:
                st.error(f"Błąd API: {response.status_code} - {response.text}")
                
        except Exception as e:
            st.error(f"Błąd dla stanowiska '{title}': {str(e)}")
    
    return all_results[:5]

def main():
    st.set_page_config(page_title="🔍 RocketReach Searcher - Poprawiony", layout="wide")
    st.title("🔍 RocketReach Searcher - Poprawiony")
    
    with st.sidebar:
        st.header("⚙️ Konfiguracja")
        api_key = st.text_input("API Key RocketReach", type="password")
        
        st.subheader("Filtry stanowisk")
        titles = st.text_area(
            "Szukane stanowiska (jedno w linii)",
            "sales\nM&A\nM and A\ncorporate development\nstrategy\ngrowth",
            height=150
        ).split('\n')
        
        exclude_titles = st.text_area(
            "Wykluczane stanowiska (jedno w linii)",
            height=100
        ).split('\n')
    
    # Test section
    st.header("🧪 Test pojedynczego zapytania")
    col1, col2 = st.columns(2)
    
    with col1:
        test_url = st.text_input("URL firmy do testu", "https://www.nvidia.com/")
    with col2:
        test_title = st.text_input("Stanowisko do testu", "sales")
    
    if st.button("🔍 Testuj pojedyncze zapytanie") and api_key:
        full_url = extract_full_url(test_url)
        results = search_people(api_key, full_url, [test_title], exclude_titles)
        
        if results:
            st.success(f"Znaleziono {len(results)} wyników!")
            for i, person in enumerate(results, 1):
                st.write(f"**{i}. {person['name']}** - {person['title']} @ {person['company']}")
                if person['linkedin']:
                    st.write(f"LinkedIn: {person['linkedin']}")
        else:
            st.warning("Nie znaleziono wyników")
    
    st.header("📁 Przetwarzanie pliku CSV")
    uploaded_file = st.file_uploader("Wybierz plik CSV", type=['csv'])
    
    if uploaded_file and api_key:
        try:
            df = pd.read_csv(uploaded_file)
            websites = df.iloc[:, 0].dropna().tolist()
            
            if st.button("🚀 Rozpocznij wyszukiwanie dla wszystkich", type="primary"):
                results = []
                progress_bar = st.progress(0)
                
                for i, website in enumerate(websites):
                    st.write(f"Przetwarzam: {website}")
                    full_url = extract_full_url(website)
                    people = search_people(api_key, full_url, titles, exclude_titles)
                    
                    if not people:
                        result_row = {
                            "Strona": website,
                            "Status": "Nie znaleziono",
                            "Liczba wyników": 0
                        }
                    else:
                        result_row = {
                            "Strona": website,
                            "Status": "Znaleziono",
                            "Liczba wyników": len(people)
                        }
                        
                        for j, person in enumerate(people, 1):
                            result_row[f"Osoba {j}"] = f"{person['name']} ({person['title']})"
                            result_row[f"LinkedIn {j}"] = person['linkedin']
                    
                    results.append(result_row)
                    progress_bar.progress((i + 1) / len(websites))
                
                results_df = pd.DataFrame(results)
                st.dataframe(results_df)
                
                csv = results_df.to_csv(index=False, sep=';', encoding='utf-8-sig')
                st.download_button("💾 Pobierz wyniki", csv, "rocketreach_results.csv", "text/csv")
        
        except Exception as e:
            st.error(f"Błąd: {str(e)}")

if __name__ == "__main__":
    main()
