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

# Definicje list wyboru
DEPARTMENTS = [
    "C-Suite", "Executive", "Founder", "Product & Engineering Executive",
    "Finance Executive", "HR Executive", "Legal Executive", "Marketing Executive",
    "Health Executive", "Operations Executive", "Sales Executive",
    "Product & Engineering", "DevOps", "Graphic Design", "Product Design",
    "Web Design", "Information Technology", "Project Engineering",
    "Quality Assurance", "Mechanical Engineering", "Electrical Engineering",
    "Data Science", "Software Development", "Web Development",
    "Information Security", "Network Operations", "Systems Administration",
    "Product Management", "Artificial Intelligence / Machine Learning",
    "Digital Transformation", "Finance", "Accounting", "Tax",
    "Investment Management", "Financial Planning & Analysis", "Risk",
    "Financial Reporting", "Investor Relations", "Financial Strategy",
    "Internal Audit & Control", "HR", "Recruiting", "Compensation & Benefits",
    "Learning & Development", "Diversity & Inclusion", "Employee & Labor Relations",
    "Talent Management", "Legal", "Legal Counsel", "Compliance", "Contracts",
    "Corporate Secretary", "Litigation", "Privacy", "Paralegal", "Judicial",
    "Marketing", "Content Marketing", "Product Marketing", "Brand Management",
    "Public Relations (PR)", "Event Marketing", "Advertising", "Customer Experience",
    "Demand Generation", "Digital Marketing", "Search Engine Optimization (SEO)",
    "Social Media Marketing", "Broadcasting", "Editorial", "Journalism",
    "Video", "Writing", "Health", "Dental", "Doctor", "Fitness", "Nursing",
    "Therapy", "Wellness", "Medical Administration", "Medical Education & Training",
    "Medical Research", "Clinical Operations", "Operations", "Logistics",
    "Project Management", "Office Operations", "Customer Service / Support",
    "Product", "Call Center", "Corporate Strategy", "Facilities Management",
    "Quality Management", "Supply Chain", "Manufacturing", "Real Estate",
    "Sales", "Business Development", "Customer Success", "Account Management",
    "Channel Sales", "Inside Sales", "Sales Enablement", "Sales Operations",
    "Pipeline", "Education", "Administration", "Professor", "Teacher", "Researcher"
]

MANAGEMENT_LEVELS = [
    "Founder/Owner", "C-Level", "Vice President", "Head", "Director",
    "Manager", "Senior", "Individual Contributor", "Entry", "Intern", "Volunteer"
]

# Domyślnie zaznaczone departments
DEFAULT_DEPARTMENTS = [
    "Founder", "Finance Executive", "Executive", "Finance",
    "Investment Management", "Financial Planning & Analysis",
    "Financial Reporting", "Financial Strategy", "Operations Executive"
]

# Domyślnie zaznaczone management levels dla filtrowania etapów 1-3
DEFAULT_MANAGEMENT_LEVELS = [
    "Founder/Owner", "C-Level", "Vice President", "Head", "Director", "Manager", "Senior"
]

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
            sleep_time = 1.0 - (now - self.request_timestamps)
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

    def _search(self, domain: str, field: str, values: List[str], exclude: List[str], 
                management_levels: Optional[List[str]] = None, country: Optional[str] = None) -> List[Dict]:
        self._rate_limit_check()
        if not domain.startswith(("http://", "https://")):
            domain = "https://" + domain
        clean_values = [v.strip() for v in values if v.strip()]
        if not clean_values:
            return []
        
        # Podstawowa struktura query
        payload = {
            "query": {
                "company_domain": [domain]
            },
            "start": 1,
            "page_size": 50
        }
        
        # Dodaj główne pole wyszukiwania
        payload["query"][field] = clean_values
        
        # Dodaj wykluczenia
        if exclude and field in ["current_title", "skills"]:
            exclude_field = f"exclude_{field}"
            payload["query"][exclude_field] = [e.strip() for e in exclude if e.strip()]
        
        # Dodaj management levels jeśli wybrane (jako dodatkowy filtr dla wszystkich etapów)
        if management_levels and field != "management_levels":
            payload["query"]["management_levels"] = management_levels
        
        # Dodaj filtr kraju jeśli podany
        if country:
            payload["query"]["company_country_code"] = [country.strip()]

        for attempt in range(3):
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
                    for p in profiles[:15]  # Limit na 15 profili
                ]
            elif resp.status_code == 400:
                try:
                    error_msg = resp.json()
                    st.error(f"❌ Search API error 400: {error_msg}")
                except:
                    st.error(f"Search API error 400: Bad request")
                return []
            else:
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
        if not data:
            return {}
        
        grade_order = {"A": 1, "A-": 2, "B": 3, "B-": 4, "C": 5, "D": 6, "F": 7}
        email = data.get("recommended_professional_email") or data.get("current_work_email")
        email_obj = {}
        
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
            email_obj = next((e for e in data.get("emails", []) if e.get("email") == email), 
                           {"email": email, "grade": "", "smtp_valid": ""})

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

    def search_with_emails(self, domain: str, titles: List[str], departments: List[str], 
                          exclude: List[str], management_levels_filter: Optional[List[str]], 
                          country: Optional[str]) -> List[Dict]:
        valid_contacts = []
        seen_emails = set()

        # ETAP 1: Keywords stanowisk (z filtrem management_levels)
        if titles and len(valid_contacts) < 3:
            st.info("🔍 Etap 1: wyszukiwanie po keywords stanowisk...")
            candidates = self._search(domain, "current_title", titles, exclude, 
                                     management_levels_filter, country)
            for c in candidates:
                if len(valid_contacts) >= 3:
                    break
                detail = self._lookup(c["id"])
                processed = self._process(detail)
                if processed and processed["email"] not in seen_emails:
                    valid_contacts.append(processed)
                    seen_emails.add(processed["email"])
                    st.success(
                        f"✅ Kontakt (keywords): {processed['name']} ({processed['title']}) | "
                        f"{processed['email']} (Grade:{processed['email_grade']}, SMTP:{processed['smtp_valid']})"
                    )

        # ETAP 2: Departments (z filtrem management_levels)
        if len(valid_contacts) < 3 and departments:
            st.info("🔍 Etap 2: wyszukiwanie po departments...")
            candidates = self._search(domain, "department", departments, exclude, 
                                     management_levels_filter, country)
            for c in candidates:
                if len(valid_contacts) >= 3:
                    break
                detail = self._lookup(c["id"])
                processed = self._process(detail)
                if processed and processed["email"] not in seen_emails:
                    valid_contacts.append(processed)
                    seen_emails.add(processed["email"])
                    st.success(
                        f"✅ Kontakt (department): {processed['name']} ({processed['title']}) | "
                        f"{processed['email']} (Grade:{processed['email_grade']}, SMTP:{processed['smtp_valid']})"
                    )

        # ETAP 3: Skills (z filtrem management_levels)
        if len(valid_contacts) < 3 and titles:
            st.info("🎯 Etap 3: wyszukiwanie po skills...")
            candidates = self._search(domain, "skills", titles, exclude, 
                                     management_levels_filter, country)
            for c in candidates:
                if len(valid_contacts) >= 3:
                    break
                detail = self._lookup(c["id"])
                processed = self._process(detail)
                if processed and processed["email"] not in seen_emails:
                    valid_contacts.append(processed)
                    seen_emails.add(processed["email"])
                    st.success(
                        f"✅ Kontakt (skills): {processed['name']} ({processed['title']}) | "
                        f"{processed['email']} (Grade:{processed['email_grade']}, SMTP:{processed['smtp_valid']})"
                    )

        # ETAP 4: Management Levels - STAŁY FILTR (Founder/Owner, C-Level, Vice President)
        if len(valid_contacts) < 3:
            st.info("👔 Etap 4: wyszukiwanie po management levels (Founder/Owner, C-Level, Vice President)...")
            # Etap 4 ma stały filtr bez możliwości edycji
            fixed_levels = ["Founder/Owner", "C-Level", "Vice President"]
            candidates = self._search(domain, "management_levels", fixed_levels, exclude, 
                                     None, country)
            for c in candidates:
                if len(valid_contacts) >= 3:
                    break
                detail = self._lookup(c["id"])
                processed = self._process(detail)
                if processed and processed["email"] not in seen_emails:
                    valid_contacts.append(processed)
                    seen_emails.add(processed["email"])
                    st.success(
                        f"✅ Kontakt (management): {processed['name']} ({processed['title']}) | "
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
        st.header("⚙️ Konfiguracja")
        
        api_key = st.text_input("RocketReach API Key", type="password")
        
        st.subheader("1️⃣ Keywords stanowisk")
        titles = st.text_area(
            "Nazwy stanowisk (jedna linia = jeden keyword)",
            "M&A\ncorporate development\nstrategy\ngrowth\nMerger\nM and A\nstrategic\ninvestment\nfinancial\nfinance\nCFO\nCEO\nAcquisitions\nOrigination\nChief Financial Officer\nChief Executive Officer\nChief Strategy Officer\nCSO",
            height=100
        ).splitlines()
        
        st.subheader("2️⃣ Departments")
        selected_departments = st.multiselect(
            "Wybierz departments (można wybrać wiele)",
            options=DEPARTMENTS,
            default=DEFAULT_DEPARTMENTS
        )
        
        st.subheader("Wykluczenia")
        exclude = st.text_area(
            "Stanowiska do wykluczenia (jedna linia = jedno stanowisko)",
            "hr\nmarketing\nsales\npeople\ntalent\nproduct\nclient\nintern\nanalyst\nAccount\nDeveloper\nCommercial\nStudent\nEngineer\nReporting\nSourcing\nController\nService\nPurchaser\ncustomer\nemployee",
            height=80
        ).splitlines()
        
        st.subheader("🎯 Dodatkowe filtry")
        
        st.markdown("**Management Levels** - dla etapów 1-3 (do edycji)")
        selected_management_levels = st.multiselect(
            "Wybierz management levels do filtrowania etapów 1-3",
            options=MANAGEMENT_LEVELS,
            default=DEFAULT_MANAGEMENT_LEVELS,
            key="filter_management_levels"
        )
        
        st.markdown("**Etap 4 (Management Levels)** - stały filtr:")
        st.markdown("🔒 Founder/Owner, C-Level, Vice President (bez możliwości edycji)")
        
        country = st.text_input(
            "Kod kraju (puste = bez ograniczeń)",
            placeholder="np. US, PL, GB"
        )

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
            contacts = rr.search_with_emails(
                domain, 
                titles, 
                selected_departments,
                exclude, 
                selected_management_levels if selected_management_levels else None,
                country if country.strip() else None
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
            progress.progress((idx + 1) / len(domains))
            if idx < len(domains) - 1:
                time.sleep(random.uniform(1, 2))

        df_out = pd.DataFrame(results)
        st.subheader("📋 Wyniki wyszukiwania")
        st.dataframe(df_out, use_container_width=True)
        
        # Statystyki
        st.subheader("📊 Statystyki")
        total_contacts = sum(1 for r in results for i in range(1, 4) if r.get(f"Email {i}"))
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Przeanalizowane firmy", len(domains))
        with col2:
            st.metric("Znalezione kontakty", total_contacts)
        with col3:
            firms_with_contacts = sum(1 for r in results if "Znaleziono" in r["Status"] and int(r["Status"].split()[1]) > 0)
            st.metric("Firmy z kontaktami", firms_with_contacts)
        
        excel_data = create_excel(df_out)
        st.download_button(
            "📥 Pobierz wyniki jako Excel",
            data=excel_data,
            file_name="kontakty_inwestorzy.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


if __name__ == "__main__":
    main()
