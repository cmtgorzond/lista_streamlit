import streamlit as st
import pandas as pd
import re
import time
from typing import List, Dict


class RocketReachClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co/api/v2"
        self.headers = {"Api-Key": api_key, "Content-Type": "application/json"}

    def search_people(self, query_params: Dict) -> Dict:
        """Wykonuje zapytanie wyszukiwania osób"""
        url = f"{self.base_url}/person/search"
        try:
            response = requests.post(url, headers=self.headers, json=query_params)
            return response.json() if response.status_code == 200 else {}
        except Exception as e:
            st.error(f"Błąd połączenia: {str(e)}")
            return {}


def main():
    st.set_page_config(page_title="🏢 Advanced Contact Finder", layout="wide")
    st.title("🔍 Zaawansowane wyszukiwanie kontaktów B2B")

    # Panel boczny z konfiguracją
    with st.sidebar:
        st.header("⚙️ Konfiguracja wyszukiwania")
        api_key = st.text_input("🔑 Klucz API RocketReach", type="password")

        # Dynamiczne filtry stanowisk
        st.subheader("🎯 Filtry stanowisk")
        include_titles = st.text_input(
            "➕ Włączane stanowiska (oddziel przecinkami)",
            value="M&A, corporate development, strategy",
            help="Np.: 'M&A, M and A, strategic development'"
        )
        exclude_titles = st.text_input(
            "➖ Wykluczane stanowiska (oddziel przecinkami)",
            help="Np.: 'HR, marketing, sales'"
        )

        # Przetwarzanie inputów
        include_list = [x.strip() for x in include_titles.split(",") if x.strip()]
        exclude_list = [x.strip() for x in exclude_titles.split(",") if x.strip()]

        st.markdown("---")
        st.subheader("📤 Dane wejściowe")
        input_method = st.radio("Metoda wprowadzania danych:", ["Plik CSV", "Ręczne wprowadzanie"])

    if not api_key:
        st.warning("⚠️ Wprowadź klucz API w panelu bocznym")
        return

    client = RocketReachClient(api_key)

    # Obsługa różnych metod wprowadzania danych
    if input_method == "Plik CSV":
        uploaded_file = st.file_uploader("📤 Prześlij plik CSV", type=["csv"])
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            if 'website' not in df.columns:
                st.error("❌ Brak wymaganej kolumny 'website' w pliku CSV")
                return

            if st.button("🚀 Rozpocznij przetwarzanie", type="primary"):
                process_csv(client, df, include_list, exclude_list)
    else:
        domains = st.text_area(
            "🌐 Wprowadź domeny firm (jedna na linijkę)",
            height=150,
            placeholder="przykład.com\nfirma.pl\ninna-firma.net"
        )
        if st.button("🔍 Wyszukaj kontakty"):
            process_manual_input(client, domains, include_list, exclude_list)


def process_csv(client: RocketReachClient, df: pd.DataFrame, include: List[str], exclude: List[str]):
    """Przetwarza plik CSV i wyświetla wyniki"""
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, row in df.iterrows():
        domain = clean_domain(row['website'])
        status_text.text(f"🔍 Przeszukuję: {domain}")

        query = build_query(domain, include, exclude)
        response = client.search_people(query)

        if response.get('profiles'):
            processed = process_profiles(response['profiles'])
            results.append(format_results(domain, processed))
        else:
            results.append({"Domena": domain, "Status": "Nie znaleziono kontaktów"})

        progress_bar.progress((idx + 1) / len(df))
        time.sleep(1)  # Rate limiting

    display_results(pd.DataFrame(results))


def build_query(domain: str, include: List[str], exclude: List[str]) -> Dict:
    """Buduje zapytanie z uwzględnieniem filtrów"""
    return {
        "query": {
            "current_employer": [domain],
            "current_title": include,
            "exclude_current_title": exclude
        },
        "page_size": 5,
        "dedup_emails": True
    }


def process_profiles(profiles: List[Dict]) -> List[Dict]:
    """Przetwarza profile na strukturalne dane"""
    return [{
        'name': f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
        'title': p.get('current_title', ''),
        'email': next((e['email'] for e in p.get('emails', []) if e.get('type') == 'work'), ''),
        'linkedin': next((l['url'] for l in p.get('links', []) if 'linkedin' in l.get('type', '').lower()), '')
    } for p in profiles]


def format_results(domain: str, profiles: List[Dict], max_contacts: int = 5) -> Dict:
    """Formatuje wyniki do struktury tabelarycznej"""
    result = {"Domena": domain}
    for i in range(max_contacts):
        if i < len(profiles):
            result.update({
                f"Osoba {i + 1} - Imię i nazwisko": profiles[i]['name'],
                f"Osoba {i + 1} - Stanowisko": profiles[i]['title'],
                f"Osoba {i + 1} - Email": profiles[i]['email'],
                f"Osoba {i + 1} - LinkedIn": profiles[i]['linkedin']
            })
        else:
            result.update({
                f"Osoba {i + 1} - Imię i nazwisko": "",
                f"Osoba {i + 1} - Stanowisko": "",
                f"Osoba {i + 1} - Email": "",
                f"Osoba {i + 1} - LinkedIn": ""
            })
    return result


def display_results(df: pd.DataFrame):
    """Wyświetla wyniki w formie tabeli"""
    st.subheader("📊 Wyniki wyszukiwania")

    # Podświetlanie wierszy bez wyników
    def highlight_row(row):
        if "Nie znaleziono" in row.values:
            return ['background-color: #ffebee'] * len(row)
        return [''] * len(row)

    # Konfiguracja kolumn
    column_config = {
        col: st.column_config.LinkColumn("LinkedIn")
        if "LinkedIn" in col else None
        for col in df.columns
    }

    st.dataframe(
        df.style.apply(highlight_row, axis=1),
        use_container_width=True,
        column_config=column_config
    )

    # Eksport wyników
    csv = df.to_csv(index=False, sep=';', encoding='utf-8-sig')
    st.download_button(
        label="💾 Pobierz wyniki jako CSV",
        data=csv,
        file_name=f"kontakty_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )


def clean_domain(url: str) -> str:
    """Czyści i weryfikuje domenę"""
    return re.sub(r"https?://(www\.)?", "", url).split('/')[0].strip()


if __name__ == "__main__":
    main()