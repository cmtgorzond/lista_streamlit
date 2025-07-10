import streamlit as st
import pandas as pd
import requests
import time
import random
import re
import io
from typing import List, Dict

# --- Ensure openpyxl for Excel export ---
try:
    import openpyxl
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])
    import openpyxl

class RocketReachAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.rocketreach.co/api/v2"
        self.headers = {
            "Api-Key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json"
        }
        self.request_timestamps: List[float] = []

    def _rate_limit_check(self):
        now = time.time()
        # keep timestamps within last second
        self.request_timestamps = [t for t in self.request_timestamps if t > now - 1]
        if len(self.request_timestamps) >= 5:
            sleep_time = 1 - (now - self.request_timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time + random.uniform(0.1, 0.3))
        self.request_timestamps.append(time.time())

    def _handle_rate_limit(self, resp: requests.Response) -> bool:
        if resp.status_code == 429:
            try:
                wait = float(resp.json().get("wait", 60))
            except:
                wait = float(resp.headers.get("Retry-After", 60))
            st.warning(f"⏳ Rate limit hit, sleeping {wait:.0f}s…")
            time.sleep(wait + random.uniform(1, 2))
            return True
        return False

    def search_people(self, domain: str, titles: List[str], exclude: List[str]) -> List[Dict]:
        self._rate_limit_check()
        if not domain.startswith(("http://","https://")):
            domain = "https://" + domain
        payload = {
            "query": {
                "company_domain": [domain],
                "current_title": [t.strip() for t in titles if t.strip()]
            },
            "start": 1,
            "page_size": 50
        }
        if exclude:
            payload["query"]["exclude_current_title"] = [e.strip() for e in exclude if e.strip()]
        resp = requests.post(f"{self.base_url}/person/search", headers=self.headers, json=payload)
        if self._handle_rate_limit(resp):
            return self.search_people(domain, titles, exclude)
        if resp.status_code != 201:
            st.error(f"Search error {resp.status_code}: {resp.text}")
            return []
        profiles = resp.json().get("profiles", [])
        # take up to 15 candidates
        return [{"id": p["id"], "name": p["name"], "title": p["current_title"], "linkedin": p["linkedin_url"]} 
                for p in profiles[:15]]

    def batch_lookup(self, ids: List[int]) -> List[Dict]:
        """Use bulk lookup for up to 100 IDs at once."""
        # must send at least 10 IDs per bulk request
        if len(ids) >= 10:
            self._rate_limit_check()
            payload = {"ids": ids[:100]}
            resp = requests.post(f"{self.base_url}/person/bulk_lookup", headers=self.headers, json=payload)
            if self._handle_rate_limit(resp):
                return self.batch_lookup(ids)
            if resp.status_code != 200:
                st.error(f"Bulk lookup error {resp.status_code}: {resp.text}")
                return []
            return resp.json().get("results", [])
        # fallback to individual
        results = []
        for pid in ids[:3]:
            details = self.lookup_person(pid)
            if details:
                results.append(details)
        return results

    def lookup_person(self, pid: int) -> Dict:
        self._rate_limit_check()
        resp = requests.get(f"{self.base_url}/person/lookup", headers=self.headers, params={"id": pid, "lookup_type": "standard"})
        if self._handle_rate_limit(resp):
            return self.lookup_person(pid)
        if resp.status_code != 200:
            return {}
        return resp.json()

    def extract_valid(self, raw: List[Dict]) -> List[Dict]:
        out = []
        grade_order = {"A":1,"A-":2,"B":3,"B-":4,"C":5,"D":6,"F":7}
        for person in raw:
            email = person.get("recommended_professional_email") or person.get("current_work_email")
            if not email:
                # find best professional
                profs = [e for e in person.get("emails",[]) 
                         if e.get("type")=="professional" and e.get("smtp_valid")!="invalid"]
                if not profs: continue
                profs.sort(key=lambda e: grade_order.get(e.get("grade","F"),99))
                email, grade, valid = profs[0]["email"], profs[0]["grade"], profs[0]["smtp_valid"]
            else:
                # find in emails
                match = next((e for e in person.get("emails",[]) if e["email"]==email), {})
                grade, valid = match.get("grade",""), match.get("smtp_valid","")
            if valid=="invalid":
                continue
            out.append({
                "name": person.get("name"),
                "title": person.get("current_title"),
                "email": email,
                "email_grade": grade,
                "smtp_valid": valid,
                "linkedin": person.get("linkedin_url")
            })
            if len(out)>=3: 
                break
        return out

    def search_with_emails(self, domain: str, titles: List[str], exclude: List[str]) -> List[Dict]:
        # step 1: search by titles
        candidates = self.search_people(domain, titles, exclude)
        ids = [c["id"] for c in candidates]
        details = self.batch_lookup(ids)
        valid = self.extract_valid(details)
        # if less than 3, try by skills
        if len(valid) < 3:
            skills = {"skills":[t.strip() for t in titles if t.strip()]}
            self._rate_limit_check()
            resp = requests.post(f"{self.base_url}/person/search", headers=self.headers,
                                 json={"query": {"company_domain":[domain], **skills}, "page_size":50})
            if resp.status_code==201:
                skills_ids = [p["id"] for p in resp.json().get("profiles",[])[:15] if p["id"] not in ids]
                details2 = self.batch_lookup(skills_ids)
                valid += [v for v in self.extract_valid(details2) if v not in valid]
        return valid[:3]

def create_excel(results_df: pd.DataFrame) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        results_df.to_excel(w, index=False, sheet_name="Kontakty")
    return out.getvalue()

def main():
    st.set_page_config(page_title="🎯 Wyszukiwarka kontaktów", layout="wide")
    st.title("🎯 Wyszukiwanie kontaktów do inwestorów")
    with st.sidebar:
        api_key = st.text_input("RocketReach API Key", type="password")
        titles = st.text_area("Stanowiska", "M&A\ncorporate development\nstrategy").splitlines()
        exclude = st.text_area("Wykluczenia", "hr\nmarketing").splitlines()
    source = st.radio("Źródło domen", ["CSV","Manual"])
    domains = []
    if source=="CSV":
        f = st.file_uploader("Wgraj CSV", type="csv")
        if f:
            df = pd.read_csv(f)
            domains = df.iloc[:,0].dropna().tolist()
            st.dataframe(df.head())
    else:
        dom = st.text_input("Domena", "https://example.com")
        if dom: domains=[dom]
    if domains and api_key and st.button("🚀 Wyszukaj"):
        rr = RocketReachAPI(api_key)
        rows = []
        progress = st.progress(0)
        for i, d in enumerate(domains):
            contacts = rr.search_with_emails(d, titles, exclude)
            row = {"Website":d, "Status":f"Znaleziono {len(contacts)} kontakt(ów)" if contacts else "Brak wyników"}
            for j in range(1,4):
                c = contacts[j-1] if j-1 < len(contacts) else {}
                row.update({
                    f"Name {j}": c.get("name",""),
                    f"Title {j}":c.get("title",""),
                    f"Email {j}":c.get("email",""),
                    f"LinkedIn {j}":c.get("linkedin",""),
                    f"Grade {j}":c.get("email_grade","")
                })
            rows.append(row)
            progress.progress((i+1)/len(domains))
            if i < len(domains)-1:
                time.sleep(random.uniform(1,2))
        df_res = pd.DataFrame(rows)
        st.dataframe(df_res, use_container_width=True)
        excel_bytes = create_excel(df_res)
        st.download_button("📥 Pobierz Excel", data=excel_bytes,
                            file_name="kontakty.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif not api_key:
        st.warning("Wprowadź klucz API")
    elif not domains:
        st.info("Podaj domeny")

if __name__ == "__main__":
    main()
