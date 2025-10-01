import streamlit as st
import pandas as pd
import requests
import time
import random
import io
from typing import List, Dict

# Sprawdź czy openpyxl jest zainstalowane
try:
    import openpyxl
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    import openpyxl

class RocketReachAPI:
    def __init__(self, api_key: str, strict_backoff: bool = True):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co/api/v2"
        self.headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json"
        }
        self.strict_backoff = strict_backoff
        self.request_timestamps: List[float] = []

    def _rate_limit_check(self):
        now = time.time()
        # Zachowaj tylko timestampy z ostatniej sekundy
        self.request_timestamps = [t for t in self.request_timestamps if t > now - 1]
        if len(self.request_timestamps) >= 5:
            sleep_time = 1.0 - (now - self.request_timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time + random.uniform(0.1, 0.3))
        self.request_timestamps.append(time.time())

    def _handle_rate_limit(self, resp: requests.Response) -> bool:
        if resp.status_code == 429:
            # Odczytaj dokładny czas oczekiwania z JSON.wait lub nagłówka Retry-After
            retry_after = None
            try:
                retry_after = float(resp.json().get("wait"))
            except:
                pass
            if retry_after is None:
                retry_after = float(resp.headers.get("Retry-After", 60))
            st.warning(f"⏳ Przekroczono limit. Czekam {retry_after:.0f}s…")
            sleep_time = retry_after if self.strict_backoff else retry_after + random.uniform(0.5, 1.5)
            time.sleep(sleep_time)
            return True
        return False

    def _search(self, domain: str, field: str, values: List[str], exclude: List[str]) -> List[Dict]:
        self._rate_limit_check()
        if not domain.startswith(("http://", "https://")):
            domain = "https://" + domain
        clean_values = [v.strip() for v in values if v.strip()]
        if not clean_values:
            return []
        payload = {
            "query": {
                "company_domain": [domain],
                field: clean_values
            },
            "start": 1,
            "page_size": 50
        }
        if exclude:
            exclude_field = f"exclude_{field}" if field != "skills" else "exclude_current_title"
            payload["query"][exclude_field] = [e.strip() for e in exclude if e.strip()]

        for _ in range(3):
            resp = requests.post(f"{self.base_url}/person/search", headers=self.headers, json=payload)
            if self._handle_rate_limit(resp):
                continue
            if resp.status_code == 201:
                profiles = resp.json().get("profiles", [])
                return [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "title": p.get("current_title", ""),
                        "linkedin": p.get("linkedin_url", "")
                    }
                    for p in profiles[:15]
                ]
            st.error(f"Search API error {resp.status_code}")
            break
        return []

    def _lookup(self, person_id: int) -> Dict:
        self._rate_limit_check()
        for _ in range(3):
            resp = requests.get(
                f"{self.base_url}/person/lookup",
                headers=self.headers,
                params={"id": person_id, "lookup_type": "standard"}
            )
            if self._handle_rate_limit(resp):
                continue
            if resp.status_code == 200:
                return resp.json()
            break
        return {}

    def _process(self, data: Dict) -> Dict:
        grade_order = {"A": 1, "A-": 2, "B": 3, "B-": 4, "C": 5, "D": 6, "F": 7}
        # Wybór emaila
        email = data.get("recommended_professional_email") or data.get("current_work_email")
        if not email:
            professional_emails = [
                e for e in data.get("emails", [])
                if e.get("type") == "professional" and e.get("smtp_valid") != "invalid"
            ]
            if not professional_emails:
                return {}
            professional_emails.sort(key=lambda e: grade_order.get(e.get("grade", "F"), 99))
            email_obj = professional_emails[0]
        else:
            email_obj = next((e for e in data.get("emails", []) if e.get("email") == email), {})

        if email_obj.get("smtp_valid") == "invalid":
            return {}

        return {
            "name": data.get("name", ""),
            "title": data.get("current_title", ""),
            "email": email_obj.get("email", ""),
            "email_grade": email_obj.get("grade", ""),
            "smtp_valid": email_obj.get("smtp_valid", ""),
            "linkedin": data.get("linkedin_url", "")
        }

    def search_with_emails(self, domain: str, titles: List[str], exclude: List[str]) -> List[Dict]:
        valid_contacts = []

        # ETAP 1: wyszukiwanie po stanowiskach
        st.info("🔍 Etap 1: wyszukiwanie po stanowiskach...")
        candidates = self._search(domain, "current_title", titles, exclude)
        for c in candidates:
            if len(valid_contacts) >= 3:
                break
            detail = self._lookup(c["id"])
            processed = self._process(detail)
            if processed:
                valid_contacts.append(processed)
                st.success(
                    f"✅ Znaleziono kontakt: {processed['name']} ({processed['title']}) | "
                    f"{processed['email']} (Grade:{processed['email_grade']}, SMTP:{processed['smtp_valid']})"
                )

        # ETAP 2: wyszukiwanie po skills, jeśli mniej niż 3
        if len(valid_contacts) < 3:
            st.info("🎯 Etap 2: rozszerzone wyszukiwanie (skills)...")
            candidates2 = self._search(domain, "skills", titles, exclude)
            seen_emails = {c["email"] for c in valid_contacts}
            for c in candidates2:
                if len(valid_contacts) >= 3:
                    break
                detail = self._lookup(c["id"])
                processed = self._process(detail)
                if processed and processed["email"] not in seen_emails:
                    valid_contacts.append(processed)
                    st.success(
                        f"✅ Znaleziono kontakt: {processed['name']} ({processed['title']}) | "
                        f"{processed['email']} (Grade:{processed['email_grade']}, SMTP:{processed['smtp_valid']})"
                    )

        st.info(f"📊 Łącznie: {len(valid_contacts)} kontaktów")
        return valid_contacts[:3]


def create_excel(results_df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        results_df.to_excel(writer, index=False, sheet_name="Kontakty")
    return out.getvalue()


def main():
    st.set_page_config(page_title="🎯 Wyszukiwanie kontaktów", layout="wide")
    st.title("🎯 Wyszukiwanie kontaktów do inwestorów")
    with st.sidebar:
        api_key = st.text_input("RocketReach API Key", type="password")
        titles = st.text_area(
            "Nazwy stanowisk (jedna linia = jeden tytuł)",
            "M&A\ncorporate development\nstrategy\ngrowth\nMerger\nM and A\nstrategic\ninvestment\nfinancial\nfinance\nCFO\nCEO\nAcquisitions\nOrigination\nChief Financial Officer\nChief Executive Officer\nChief Strategy Officer\nCSO"
        ).splitlines()
        exclude = st.text_area(
            "Nazwy stanowisk do wykluczenia (jedna linia = jeden tytuł)",
            "hr\nmarketing\nsales\npeople\ntalent\nproduct\nclient\nintern\nanalyst\nAccount\nDeveloper\nCommercial\nStudent\nEngineer\nReporting\nSourcing\nController\nService\nPurchaser\ncustomer\nemployee"
        ).splitlines()

    source = st.radio("Źródło domen", ["CSV", "Manual"])
    domains: List[str] = []
    if source == "CSV":
        uploaded = st.file_uploader("Wgraj plik CSV z domenami", type="csv")
        if uploaded:
            df_in = pd.read_csv(uploaded)
            domains = df_in.iloc[:, 0].dropna().tolist()
            st.dataframe(df_in.head())
    else:
        manual = st.text_input("Wpisz domenę (np. https://example.com)")
        if manual:
            domains = [manual.strip()]

    if not api_key:
        st.warning("⚠️ Wprowadź klucz API RocketReach")
    elif not domains:
        st.info("📝 Podaj przynajmniej jedną domenę")
    elif st.button("🚀 Rozpocznij wyszukiwanie"):
        rr = RocketReachAPI(api_key)
        results = []
        progress = st.progress(0)
        for idx, domain in enumerate(domains):
            contacts = rr.search_with_emails(domain, titles, exclude)
            row = {"Website": domain, "Status": f"Znaleziono {len(contacts)} kontakt(ów)"}
            for i in range(1, 4):
                c = contacts[i - 1] if i - 1 < len(contacts) else {}
                row.update({
                    f"Name {i}": c.get("name", ""),
                    f"Title {i}": c.get("title", ""),
                    f"Email {i}": c.get("email", ""),
                    f"LinkedIn {i}": c.get("linkedin", ""),
                    f"Grade {i}": c.get("email_grade", "")
                })
            results.append(row)
            progress.progress((idx + 1) / len(domains))
            if idx < len(domains) - 1:
                time.sleep(random.uniform(1, 2))

        df_out = pd.DataFrame(results)
        st.subheader("📋 Wyniki wyszukiwania")
        st.dataframe(df_out, use_container_width=True)
        excel_data = create_excel(df_out)
        st.download_button(
            "📥 Pobierz wyniki jako Excel",
            data=excel_data,
            file_name="kontakty_inwestorzy.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


if __name__ == "__main__":
    main()


