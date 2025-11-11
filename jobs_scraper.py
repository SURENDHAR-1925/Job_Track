#!/usr/bin/env python3
"""
Diagnostic job fetcher for JSearch (RapidAPI).
Saves raw responses, accepted rows, rejected rows (with reason).
Use RAPIDAPI_KEY env var (or RAPIDAPI_KEY hardcoded fallback).
"""

import os
import requests
import pandas as pd
import json
import time
from datetime import datetime

# ---------- CONFIG ----------
API_URL = "https://jsearch.p.rapidapi.com/search"
API_KEY = os.environ.get("RAPIDAPI_KEY") or os.environ.get("JSEARCH_API_KEY") or ""
if not API_KEY:
    print("[ERROR] RAPIDAPI_KEY not found in environment. Set RAPIDAPI_KEY and re-run.")
    # continue: script will likely fail network calls but we still keep the structure

KEYWORDS = [
    "Software Engineer",
    "Frontend Developer",
    "UI UX Designer",
    "Software Developer"
]

VALID_SOURCES = ["linkedin", "indeed", "internshala"]   # lower-case substrings to match
VALID_CITIES = ["chennai", "bengaluru", "coimbatore"]   # lower-case substrings to match
FRESHER_KEYWORDS = ["fresher", "0 years", "0 year", "entry level", "graduate trainee", "freshers"]

OUT_ACCEPTED = "accepted_jobs.csv"
OUT_REJECTED = "rejected_jobs.csv"
API_DEBUG_DIR = "api_debug"

os.makedirs(API_DEBUG_DIR, exist_ok=True)

# ---------- helpers ----------
def call_jsearch(query, page=1):
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {
        "query": query,
        "page": str(page),
        "num_pages": "1",
        "country": "in",
        "date_posted": "all"
    }
    r = requests.get(API_URL, headers=headers, params=params, timeout=30)
    return r

def lower_of(v):
    return (v or "").strip().lower()

def is_valid_source_str(pub):
    pub = lower_of(pub)
    return any(s in pub for s in VALID_SOURCES)

def is_valid_city_str(city):
    city = lower_of(city)
    return any(c in city for c in VALID_CITIES)

def is_fresher_text(title, desc):
    text = f"{title or ''} {desc or ''}".lower()
    return any(k in text for k in FRESHER_KEYWORDS)

# ---------- main logic ----------
all_raw_jobs = []
accepted = []
rejected = []

print(f"[*] Starting job fetch: {len(KEYWORDS)} keywords x {len(VALID_CITIES)} cities")

for kw in KEYWORDS:
    for city in VALID_CITIES:
        q = f"{kw} jobs in {city}"
        print(f"[*] Querying: {q}")
        try:
            resp = call_jsearch(q)
        except Exception as e:
            print(f"[!] Network error for query '{q}': {e}")
            continue

        fname = os.path.join(API_DEBUG_DIR, f"{kw.replace(' ','_')}_{city}_{int(time.time())}.json")
        try:
            data = resp.json()
        except Exception:
            data = {"error_text": resp.text if resp is not None else "no response"}

        # save raw
        with open(fname, "w", encoding="utf-8") as f:
            json.dump({"status_code": getattr(resp, "status_code", None), "url": getattr(resp, "url", q), "raw": data}, f, indent=2)

        print(f"    saved debug -> {fname} (status {getattr(resp,'status_code',None)})")

        items = (data.get("data") if isinstance(data, dict) else None) or []
        if not items:
            print(f"    [!] API returned 0 items for: {q}")
        for j in items:
            row = {
                "query_keyword": kw,
                "query_city": city,
                "job_title": j.get("job_title"),
                "employer_name": j.get("employer_name"),
                "job_city": j.get("job_city"),
                "job_country": j.get("job_country"),
                "job_description": j.get("job_description"),
                "job_apply_link": j.get("job_apply_link"),
                "job_publisher": j.get("job_publisher"),
                "raw": json.dumps(j, ensure_ascii=False)
            }
            all_raw_jobs.append(row)

            # filtering checks and reasons
            reasons = []
            pub = lower_of(j.get("job_publisher"))
            jobcity = lower_of(j.get("job_city"))
            title = j.get("job_title") or ""
            desc = j.get("job_description") or ""

            if not is_valid_source_str(pub):
                reasons.append(f"bad_source: {pub or 'NONE'}")
            if not is_valid_city_str(jobcity):
                reasons.append(f"bad_city: {jobcity or 'NONE'}")
            if not is_fresher_text(title, desc):
                reasons.append("not_fresher")

            if reasons:
                rej = dict(row)
                rej["reject_reasons"] = ";".join(reasons)
                rejected.append(rej)
            else:
                accepted.append(row)

        # be polite
        time.sleep(0.6)

# ---------- save outputs ----------
print(f"[*] Raw items collected: {len(all_raw_jobs)}")
print(f"[*] Accepted count: {len(accepted)}")
print(f"[*] Rejected count: {len(rejected)}")

if accepted:
    df_acc = pd.DataFrame(accepted)
    df_acc.to_csv(OUT_ACCEPTED, index=False, encoding="utf-8")
    print(f"[+] Accepted jobs saved to {OUT_ACCEPTED}")
else:
    print("[!] No accepted jobs found; {OUT_ACCEPTED} not created.")

if rejected:
    df_rej = pd.DataFrame(rejected)
    df_rej.to_csv(OUT_REJECTED, index=False, encoding="utf-8")
    print(f"[+] Rejected jobs saved to {OUT_REJECTED}")
else:
    print("[!] No rejected rows (all empty).")

print("[*] Done. Inspect api_debug/*.json, accepted_jobs.csv, rejected_jobs.csv")
