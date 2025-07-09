import streamlit as st
import pandas as pd
import requests
import time
import random
from typing import List, Dict
from urllib.parse import urlparse
import io

# --- STREAMLIT APP ---

def extract_domain(url: str) -> str:
    if not url.startswith(("http://","https://")):
        url = "https://" + url
    domain = urlparse(url).netloc.lower()
    return domain[4:] if domain.startswith("www.") else domain

class RocketReachAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base = "https://api.rocketreach.co"
        self.headers = {"Api-Key": api_key}

    def search_people(self, domain: str, titles: List[str], exclude: List[str]) -> List[Dict]:
        payload = {
            "query": {
                "company_domain": [domain],
                "current_title": titles,
                "exclude_current_title": exclude
            },
            "page_size": 25,
            "fields": ["id","name","current_title","current_employer","linkedin_url"]
        }
        r = requests.post(f"{self.base}/api/v2/person/search", json=payload, headers=self.headers)
        if r.status_code in (200,201):
            return r.json().get("profiles", [])[:5]
        st.error(f"Search API error {r.status_code}: {r.text}")
        return []

    def lookup_person(self, person_id: int) -> Dict:
        r = requests.get(
            f"{self.base}/api/v2/person/lookup",
            params={"id": person_id, "lookup_type": "standard"},
            headers=self.headers
        )
        if r.status_code == 200:
            data = r.json()
            # wyciągnij zweryfikowany email
            for e in data.get("emails", []):
                if e.get("type")=="professional" and e.get("smtp_valid")=="valid":
                    return {
                        "name": data["name"],
                        "title": data["current_title"],
                        "email": e["email"],
                        "email_grade": e.get("grade",""),
                        "smtp_valid": e.get("smtp_valid",""),
                        "linkedin": data.get("linkedin_url","")
                    }
            return {}
        st.error(f"Lookup API error {r.status_code}")
        return {}

def main():
    st.set_page_config(page_title="RocketReach Contact Finder", layout="wide")
    st.title("RocketReach Contact Finder")

    api_key = st.sidebar.text_input("RocketReach API Key", type="password")
    st.sidebar.subheader("Stanowiska")
    titles = [t.strip() for t in st.sidebar.text_area(
        "", "sales\nM&A\ncorporate development\nstrategy\ngrowth\nmerger\nacquisition"
    ).split("\n") if t.strip()]
    st.sidebar.subheader("Wykluczenia")
    exclude = [t.strip() for t in st.sidebar.text_area(
        "", "hr\nmarketing\nsales\ntalent\nhuman resources"
    ).split("\n") if t.strip()]

    st.header("Wprowadź domenę albo plik CSV")
    mode = st.radio("", ["Ręcznie", "CSV"])
    sites = []
    if mode=="Ręcznie":
        dom = st.text_input("Domena firmy lub URL", placeholder="example.com")
        if dom: sites = [dom.strip()]
    else:
        f = st.file_uploader("CSV z listą domen (kol A)", type="csv")
        if f:
            df = pd.read_csv(f)
            sites = df.iloc[:,0].dropna().tolist()
            st.dataframe(df.head())

    if api_key and sites and st.button("Szukaj"):
        rr = RocketReachAPI(api_key)
        all_rows = []
        for site in sites:
            domain = extract_domain(site)
            st.write(f"🔍 Szukam w {domain}")
            profiles = rr.search_people(domain, titles, exclude)
            row = {"Company": domain}
            if profiles:
                row["Status"] = f"Found {len(profiles)}"
                for i,p in enumerate(profiles,1):
                    details = rr.lookup_person(p["id"])
                    time.sleep(1)
                    if details:
                        row[f"Name {i}"] = details["name"]
                        row[f"Title {i}"] = details["title"]
                        row[f"Email {i}"] = details["email"]
                        row[f"Grade {i}"] = details["email_grade"]
                        row[f"SMTP {i}"] = details["smtp_valid"]
                        row[f"LinkedIn {i}"] = details["linkedin"]
                # fill empty up to 5
                for j in range(len(profiles)+1,6):
                    for col in ["Name","Title","Email","Grade","SMTP","LinkedIn"]:
                        row[f"{col} {j}"]=""
            else:
                row["Status"]="No profiles"
                for j in range(1,6):
                    for col in ["Name","Title","Email","Grade","SMTP","LinkedIn"]:
                        row[f"{col} {j}"]=""
            all_rows.append(row)
        df_out = pd.DataFrame(all_rows)
        st.dataframe(df_out)
        buf = io.BytesIO()
        df_out.to_excel(buf, index=False)
        st.download_button("Pobierz XLSX", buf.getvalue(), "results.xlsx")

if __name__=="__main__":
    main()
