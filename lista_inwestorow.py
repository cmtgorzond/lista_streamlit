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
        
        # Do
