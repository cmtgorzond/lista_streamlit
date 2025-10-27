import streamlit as st
import pandas as pd
import requests
import time
import random
import io
from typing import List, Dict, Optional

# Sprawdź czy openpyxl jest zainstalowane
try:
    import openpyxl
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    import openpyxl

# --- Stałe listy dla filtrów ---

DEPARTMENTS_LIST = [
    "C-Suite", "Executive", "Founder", "Product & Engineering Executive", "Finance Executive",
    "HR Executive", "Legal Executive", "Marketing Executive", "Health Executive", "Operations Executive",
    "Sales Executive", "Product & Engineering", "DevOps", "Graphic Design", "Product Design",
    "Web Design", "Information Technology", "Project Engineering", "Quality Assurance", "Mechanical Engineering",
    "Electrical Engineering", "Data Science", "Software Development", "Web Development", "Information Security",
    "Network Operations", "Systems Administration", "Product Management", "Artificial Intelligence / Machine Learning",
    "Digital Transformation", "Finance", "Accounting", "Tax", "Investment Management",
    "Financial Planning & Analysis", "Risk", "Financial Reporting", "Investor Relations",
    "Financial Strategy", "Internal Audit & Control", "HR", "Recruiting", "Compensation & Benefits",
    "Learning & Development", "Diversity & Inclusion", "Employee & Labor Relations", "Talent Management",
    "Legal", "Legal Counsel", "Compliance", "Contracts", "Corporate Secretary", "Litigation",
    "Privacy", "Paralegal", "Judicial", "Marketing", "Content Marketing", "Product Marketing",
    "Brand Management", "Public Relations (PR)", "Event Marketing", "Advertising", "Customer Experience",
    "Demand Generation", "Digital Marketing", "Search Engine Optimization (SEO)", "Social Media Marketing",
    "Broadcasting", "Editorial", "Journalism", "Video", "Writing", "Health", "Dental", "Doctor",
    "Fitness", "Nursing", "Therapy", "Wellness", "Medical Administration", "Medical Education & Training",
    "Medical Research", "Clinical Operations", "Operations", "Logistics", "Project Management",
    "Office Operations", "Customer Service / Support", "Product", "Call Center", "Corporate Strategy",
    "Facilities Management", "Quality Management", "Supply Chain", "Manufacturing", "Real Estate",
    "Sales", "Business Development", "Customer Success", "Account Management", "Channel Sales",
    "Inside Sales", "Sales Enablement", "Sales Operations", "Pipeline", "Education", "Administration",
    "Professor", "Teacher", "Researcher"
]

MANAGEMENT_LEVELS_MAP = {
    "Founder/Owner": "Founder/Owner",
    "C-Level": "c-level",
    "Vice President": "Vice President",
    "Head": "head",
    "Director": "director",
    "Manager": "manager",
    "Senior": "senior",
    "Individual Contributor": "Individual Contributor",
    "Entry": "entry",
    "Intern": "intern",
    "Volunteer": "volunteer"
}
# ---------------------------------


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
        self.request_timestamps = [t for t in self.request_timestamps if t > now - 1]
        if len(self.request_timestamps) >= 5:
            sleep_time = 1.0 - (now - self.request_timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time + random.uniform(0.1, 0.3))
        self.request_timestamps.append(time.time())

    def _handle_rate_limit(self, resp: requests.Response) -> bool:
        if resp.status_code == 429:
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

    # ZMIANA: Funkcja _search jest teraz bardziej elastyczna
    # field i values są opcjonalne, aby pozwolić na wyszukiwanie tylko po filtrach
    def _search(self, domain: str, exclude: List[str], management_levels: List[str], country: str, 
                field: Optional[str] = None, values: Optional[List[str]] = None) -> List[Dict]:
        
        self._rate_limit_check()
        if not domain.startswith(("http://", "https://")):
            domain = "https://" + domain
            
        payload = {
            "query": {
                "company_domain": [domain]
            },
            "start": 1,
            "page_size": 50
        }
        
        log_field_name = "tylko filtry" # Domyślna nazwa do logów

        # Jeśli podano pole (field) i wartości (values) - dodaj je do zapytania
        if field and values:
            clean_values = [v.strip() for v in values if v.strip()]
            if not clean_values:
                st.warning(f"⚠️ Pusta lista wartości dla pola '{field}', pomijam wyszukiwanie.")
                return []
            payload["query"][field] = clean_values
            log_field_name = field # Użyj nazwy pola w logach
        elif field and not values:
            st.warning(f"⚠️ Podano pole '{field}' ale bez wartości, pomijam.")
            return []

        # --- Dodawanie filtrów i wykluczeń do zapytania ---
        if exclude:
            exclude_field = f"exclude_{field}" if field else "exclude_current_title" # Domyślne wykluczenie
            if field == "current_title":
                exclude_field = "exclude_current_title"
            elif field == "skills":
                exclude_field = "exclude_skills"
            elif field == "department":
                exclude_field = "exclude_department"
                
            payload["query"][exclude_field] = [e.strip() for e in exclude if e.strip()]
        
        if management_levels:
            payload["query"]["management_level"] = management_levels
            
        if country and country.strip():
            payload["query"]["location"] = [country.strip()] 
        # ----------------------------------------------------

        for _ in range(3):
            resp = requests.post(f"{self.base_url}/person/search", headers=self.headers, json=payload)
            if self._handle_rate_limit(resp):
                continue
            if resp.status_code == 201:
                profiles = resp.json().get("profiles", [])
                st.info(f"🔎 Wyszukiwanie (pole: '{log_field_name}') znalazło {len(profiles)} profili. Sprawdzam emaile dla max 15...")
                return [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "title": p.get("current_title", ""),
                        "linkedin": p.get("linkedin_url", "")
                    }
                    for p in profiles[:15]
                ]
            st.error(f"Search API error {resp.status_code} dla pola '{log_field_name}'. Treść: {resp.text}")
            st.error(f"Wysłane zapytanie (payload): {payload}")
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
            if resp.status_code == 404:
                st.warning(f"Profil o ID {person_id} nie został znaleziony (404).")
                break
            st.error(f"Lookup API error {resp.status_code} dla ID {person_id}. Treść: {resp.text}")
            break
        return {}

    def _process(self, data: Dict) -> Dict:
        if not data or 'id' not in data:
            return {}
            
        grade_order = {"A": 1, "A-": 2, "B": 3, "B-": 4, "C": 5, "D": 6, "F": 7}
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

        if not email_obj or email_obj.get("smtp_valid") == "invalid":
            return {}

        return {
            "name": data.get("name", ""),
            "title": data.get("current_title", ""),
            "email": email_obj.get("email", ""),
            "email_grade": email_obj.get("grade", ""),
            "smtp_valid": email_obj.get("smtp_valid", ""),
            "linkedin": data.get("linkedin_url", "")
        }

    # ZMIANA: Dodano Etap 4 (Fallback)
    def search_with_emails(self, domain: str, search_terms: List[str], departments: List[str], exclude: List[str], management_levels: List[str], country: str) -> List[Dict]:
        valid_contacts = []
        seen_profile_ids = set() 

        def process_candidates(candidates: List[Dict], stage_name: str):
            for c in candidates:
                if len(valid_contacts) >= 3:
                    break
                if c["id"] in seen_profile_ids:
                    continue
                    
                detail = self._lookup(c["id"])
                processed = self._process(detail)
                if processed:
                    valid_contacts.append(processed)
                    seen_profile_ids.add(c["id"])
                    st.success(
                        f"✅ ({stage_name}) Znaleziono kontakt: {processed['name']} ({processed['title']}) | "
                        f"{processed['email']} (Grade:{processed['email_grade']}, SMTP:{processed['smtp_valid']})"
                    )

        # ETAP 1: Wyszukiwanie po STANOWISKACH (current_title)
        st.info(f"🔍 Etap 1: Wyszukiwanie po STANOWISKACH dla domeny: {domain}...")
        if search_terms:
            # ZMIANA: Zaktualizowane wywołanie _search
            candidates_title = self._search(domain, exclude, management_levels, country,
                                            field="current_title", values=search_terms)
            process_candidates(candidates_title, "Etap 1: Stanowisko")
        else:
            st.info("Pominięto Etap 1 (brak słów kluczowych dla stanowisk).")

        # ETAP 2: Wyszukiwanie po DZIAŁACH (department)
        if len(valid_contacts) < 3 and departments:
            st.info(f"🎯 Etap 2: Wyszukiwanie po DZIAŁACH dla domeny: {domain}...")
            # ZMIANA: Zaktualizowane wywołanie _search
            candidates_dept = self._search(domain, exclude, management_levels, country,
                                          field="department", values=departments)
            process_candidates(candidates_dept, "Etap 2: Dział")
        elif not departments:
            st.info("Pominięto Etap 2 (nie wybrano działów).")

        # ETAP 3: Wyszukiwanie po UMIEJĘTNOŚCIACH (skills)
        if len(valid_contacts) < 3 and search_terms:
            st.info(f"✨ Etap 3: Wyszukiwanie po UMIEJĘTNOŚCIACH dla domeny: {domain}...")
            # ZMIANA: Zaktualizowane wywołanie _search
            candidates_skills = self._search(domain, exclude, management_levels, country,
                                             field="skills", values=search_terms)
            process_candidates(candidates_skills, "Etap 3: Umiejętności")
        elif not search_terms:
            st.info("Pominięto Etap 3 (brak słów kluczowych dla umiejętności).")

        # ZMIANA: ETAP 4 - Fallback
        if len(valid_contacts) == 0:
            st.warning(f"⚠️ Nie znaleziono żadnych kontaktów. Uruchamiam Etap 4 (Fallback)...")
            st.info(f"👑 Etap 4: Wyszukiwanie 'Founder/Owner' lub 'C-Level' dla: {domain}...")
            
            # Użyj tylko tych dwóch poziomów, ignorując wybór użytkownika z panelu bocznego
            fallback_levels = [
                MANAGEMENT_LEVELS_MAP["Founder/Owner"], 
                MANAGEMENT_LEVELS_MAP["C-Level"]
            ]
            
            # Wywołaj _search bez 'field' i 'values', ale z nowymi poziomami
            # Oryginalne filtry 'country' i 'exclude' SĄ nadal stosowane
            candidates_fallback = self._search(
                domain, 
                exclude, 
                fallback_levels, # Użyj tylko poziomów fallback
                country, 
                field=None,      # Bez słów kluczowych
                values=None
            )
            process_candidates(candidates_fallback, "Etap 4: Fallback")


        st.info(f"📊 Zakończono dla {domain}. Łącznie: {len(valid_contacts)} kontaktów")
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
        
        st.subheader("Kryteria wyszukiwania")
        # Pole dla Etapu 1 i 3
        search_terms = st.text_area(
            "1. Słowa kluczowe (dla Stanowisk i Umiejętności)",
            "M&A\ncorporate development\nstrategy\ngrowth\nMerger\nM and A\nstrategic\ninvestment\nfinancial\nfinance\nCFO\nCEO\nAcquisitions\nOrigination\nChief Financial Officer\nChief Executive Officer\nChief Strategy Officer\nCSO"
        ).splitlines()

        default_departments = [
            "Finance Executive", "Investment Management", "Financial Planning & Analysis",
            "Financial Reporting", "Financial Strategy"
        ]
        
        # Pole dla Etapu 2
        departments = st.multiselect(
            "2. Działy (Departments)",
            options=DEPARTMENTS_LIST,
            default=default_departments
        )

        st.subheader("Filtry (Opcjonalne)")
        
        # Filtr Poziomu Zarządzania
        selected_levels_display = st.multiselect(
            "Poziom zarządzania (Management Level)",
            options=list(MANAGEMENT_LEVELS_MAP.keys()) 
        )
        management_levels = [MANAGEMENT_LEVELS_MAP[level] for level in selected_levels_display]

        # Filtr Kraju
        country = st.text_input("Kraj (np. France, Germany, Poland)")

        st.subheader("Wykluczenia")
        exclude = st.text_area(
            "Słowa kluczowe do wykluczenia ze stanowisk",
            "hr\nmarketing\nsales\npeople\ntalent\nproduct\nclient\nintern\nanalyst\nAccount\nDeveloper\nCommercial\nStudent\nEngineer\nReporting\nSourcing\nController\nService\nPurchaser\ncustomer\nemployee"
        ).splitlines()

    # --- Główny interfejs ---
    source = st.radio("Źródło domen", ["CSV", "Manual"])
    domains: List[str] = []
    if source == "CSV":
        uploaded = st.file_uploader("Wgraj plik CSV z domenami", type="csv")
        if uploaded:
            try:
                df_in = pd.read_csv(uploaded)
                domains = df_in.iloc[:, 0].dropna().str.strip().tolist()
                st.dataframe(df_in.head())
                st.info(f"Załadowano {len(domains)} domen.")
            except Exception as e:
                st.error(f"Błąd podczas wczytywania pliku CSV: {e}")
    else:
        manual = st.text_input("Wpisz domenę (np. example.com lub https://example.com)")
        if manual:
            domains = [manual.strip()]

    if not api_key:
        st.warning("⚠️ Wprowadź klucz API RocketReach")
    elif not domains:
        st.info("📝 Podaj przynajmniej jedną domenę (przez CSV lub manualnie)")
    elif not search_terms and not departments:
        st.warning("⚠️ Wprowadź przynajmniej jedno słowo kluczowe lub wybierz dział")
    elif st.button("🚀 Rozpocznij wyszukiwanie"):
        rr = RocketReachAPI(api_key)
        results = []
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        for idx, domain in enumerate(domains):
            if not domain: 
                continue
            
            status_text.info(f"Przetwarzam domenę {idx+1}/{len(domains)}: {domain}")
            
            contacts = rr.search_with_emails(
                domain, 
                search_terms, 
                departments, 
                exclude, 
                management_levels, 
                country
            )
            
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
            progress_bar.progress((idx + 1) / len(domains))

        status_text.success("🎉 Wyszukiwanie zakończone!")
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

