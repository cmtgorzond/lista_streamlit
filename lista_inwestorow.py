import streamlit as st
import pandas as pd
import requests
import time
import random
from typing import List, Dict
from urllib.parse import urlparse
import io

# ──────────────────────────────────────────────────────────────────────
#  POMOCNICZE
# ──────────────────────────────────────────────────────────────────────
def extract_domain(url: str) -> str:
    """Zwraca czystą domenę z URL lub domenę z e-maila."""
    if '@' in url:
        return url.split('@')[1].lower()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


# ──────────────────────────────────────────────────────────────────────
#  KLASA API
# ──────────────────────────────────────────────────────────────────────
class RocketReachAPI:
    def __init__(self, api_key: str, webhook_id: str | None = None):
        self.api_key   = api_key
        self.webhook_id = webhook_id
        self.base      = "https://api.rocketreach.co"
        self.headers   = {"Api-Key": api_key, "accept": "application/json"}
        self.timestamps: list[float] = []          # rate-limit 5 req/s

    # ------------------------------- rate-limit -----------------------
    def _rate_limit(self):
        now = time.time()
        self.timestamps = [t for t in self.timestamps if t > now - 1]
        if len(self.timestamps) >= 5:
            time.sleep(1 - (now - self.timestamps[0]) + random.uniform(.1, .3))
        self.timestamps.append(time.time())

    # ------------------------------- search ---------------------------
    def search_people(self, domain: str,
                      titles: List[str],
                      exclude: List[str]) -> List[Dict]:
        self._rate_limit()
        payload = {
            "query": {
                "company_domain": [domain],
                "current_title": titles,
                "exclude_current_title": exclude
            },
            "page_size": 25,
            "fields": [
                "id", "name", "current_title",
                "current_employer", "linkedin_url"
            ]
        }
        resp = requests.post(f"{self.base}/api/v2/person/search",
                             headers=self.headers, json=payload, timeout=30)
        if resp.status_code in (200, 201):
            return resp.json().get("profiles", [])[:10]
        st.error(f"Search API error {resp.status_code}: {resp.text}")
        return []

    # ------------------------------- bulk lookup ----------------------
    def bulk_lookup(self, ids: List[int]) -> Dict | None:
        """Wywołuje bulk lookup; przy webhook_id wyniki przyjdą na webhook."""
        self._rate_limit()
        payload = {
            "profiles": [{"id": i} for i in ids],
            "lookup_type": "standard"
        }
        if self.webhook_id:
            payload["webhook_id"] = self.webhook_id

        resp = requests.post(f"{self.base}/api/v2/person/bulk_lookup",   #  <- PODKREŚLENIE
                             headers=self.headers, json=payload, timeout=30)

        if resp.status_code in (200, 201, 202):
            if self.webhook_id:
                st.success("🔔 Bulk lookup wysłany, wyniki przyjdą na webhook.")
                return None
            return resp.json()             # synchroniczny fallback (rzadko używany)
        st.error(f"Bulk lookup error {resp.status_code}: {resp.text}")
        return None


# ──────────────────────────────────────────────────────────────────────
#  STREAMLIT UI
# ──────────────────────────────────────────────────────────────────────
def create_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Kontakty")
    return buf.getvalue()


def main() -> None:
    st.set_page_config("RocketReach Contact Finder", layout="wide")
    st.title("🚀 RocketReach Contact Finder (Bulk webhook / synchroniczny)")

    # -------------------------- sidebar ------------------------------
    api_key    = st.sidebar.text_input("RocketReach API Key", type="password")
    webhook_id = st.sidebar.text_input("Webhook ID (opcjonalnie)",
                                       help="Jeśli podasz – lookup będzie asynchroniczny")
    mode_info  = "🔔 TRYB WEBHOOK" if webhook_id else "📋 TRYB SYNCHRONICZNY"
    st.sidebar.markdown(mode_info)

    default_titles = (
        "M&A\nM and A\ncorporate development\nstrategy\nstrategic\n"
        "growth\nmerger\nacquisition\ndeal\norigination"
    )
    titles  = [t.strip() for t in
               st.sidebar.text_area("Stanowiska", default_titles, height=140).splitlines()
               if t.strip()]

    default_ex = "hr\nhuman resources\nmarketing\nsales\ntalent"
    excludes = [e.strip() for e in
                st.sidebar.text_area("Wykluczenia", default_ex, height=90).splitlines()
                if e.strip()]

    # -------------------------- źródło domen -------------------------
    source = st.radio("Źródło domen:", ["CSV", "Ręcznie"])
    sites: list[str] = []
    if source == "CSV":
        csv = st.file_uploader("Plik CSV (kol A)", type="csv")
        if csv:
            df_csv = pd.read_csv(csv)
            sites = df_csv.iloc[:, 0].dropna().tolist()
            st.dataframe(df_csv.head())
    else:
        manual = st.text_input("Domena lub URL",
                               placeholder="example.com lub https://example.com")
        if manual:
            sites = [manual.strip()]

    if not api_key:
        st.info("⏳ Podaj klucz API.")
        return
    if not sites:
        st.info("⏳ Wprowadź przynajmniej jedną domenę.")
        return

    # -------------------------- START --------------------------------
    if st.button("🚀 Szukaj"):
        rr = RocketReachAPI(api_key, webhook_id)
        for site in sites:
            domain = extract_domain(site)
            st.write(f"🔍 Szukam profili w **{domain}** ...")
            profiles = rr.search_people(domain, titles, excludes)
            ids = [p["id"] for p in profiles[:5]]       # 5 ID na firmę
            if ids:
                rr.bulk_lookup(ids)
            else:
                st.warning("Brak profili spełniających kryteria.")
            time.sleep(random.uniform(1, 2))

        st.success("✔️ Wszystkie zapytania wysłane.")
        if webhook_id:
            st.info("Sprawdź swój serwer webhook, aby odebrać wyniki.")

if __name__ == "__main__":
    main()
