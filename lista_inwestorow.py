import streamlit as st
import requests
import re

st.set_page_config(page_title="RocketReach Search", layout="centered")

st.title("🔍 RocketReach People Search")

# --- INPUTS ---
api_key = st.text_input("🔑 Klucz API RocketReach", type="password").strip()
domain = st.text_input("🌐 Domena firmy (np. nvidia.com)").strip()
include_kw = st.text_input("📌 Słowa kluczowe (oddziel przecinkami)").strip()
exclude_kw = st.text_input("🚫 Wyklucz tytuły zawierające (oddziel przecinkami)").strip()
pages = st.number_input("🔁 Liczba stron do przeszukania (po 10 wyników)", min_value=1, max_value=50, value=5)

if st.button("🔎 Szukaj"):
    if not api_key or not domain:
        st.error("Podaj klucz API i domenę.")
    else:
        include_keywords = [w.strip().lower() for w in include_kw.split(",") if w.strip()]
        exclude_keywords = [w.strip().lower() for w in exclude_kw.split(",") if w.strip()]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        collected = []
        skipped = []

        for page in range(1, pages + 1):
            for keyword in include_keywords or [""]:
                payload = {
                    "company_domain": [domain],
                    "current_title": [keyword],
                    "page": page
                }

                st.markdown(f"📡 **Zapytanie API (strona {page})**: `{payload}`")

                try:
                    res = requests.post(
                        "https://api.rocketreach.co/v1/api/search/profiles",
                        headers=headers,
                        json=payload
                    )
                    if res.status_code == 401:
                        st.error("❌ Błąd API (401): Nieprawidłowy klucz API.")
                        st.stop()

                    elif res.status_code != 200:
                        st.warning(f"⚠️ Błąd API ({res.status_code}): {res.text}")
                        continue

                    data = res.json()
                    profiles = data.get("profiles", [])

                    for prof in profiles:
                        title = (prof.get("current_title") or "").lower()
                        status = prof.get("status", "")
                        profile_id = prof.get("id")

                        if any(ex in title for ex in exclude_keywords):
                            skipped.append((profile_id, title, "⛔ exclude"))
                            continue
                        if include_keywords and not any(kw in title for kw in include_keywords):
                            skipped.append((profile_id, title, "⚪ no match"))
                            continue
                        if status not in {"complete", "progress"}:
                            skipped.append((profile_id, title, f"⚠️ status={status}"))
                            continue
                        collected.append({
                            "id": profile_id,
                            "name": prof.get("name"),
                            "title": prof.get("current_title"),
                            "linkedin": prof.get("linkedin_url"),
                            "location": prof.get("location"),
                            "company": prof.get("current_employer"),
                            "email_domains": ", ".join(prof.get("teaser", {}).get("emails", []))
                        })

                except Exception as e:
                    st.error(f"❌ Wyjątek: {e}")
                    continue

        st.success(f"✅ Znaleziono {len(collected)} profili.")
        st.markdown("### 📄 Wyniki")
        if collected:
            st.dataframe(collected, use_container_width=True)

        if skipped:
            with st.expander("⏭️ Pomięte rekordy"):
                for s in skipped:
                    st.text(f"{s[0]} | {s[1]} ➤ {s[2]}")
