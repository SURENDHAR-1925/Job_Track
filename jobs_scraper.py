import os
import re
import requests
import pandas as pd

# ---------------- CONFIG ----------------
API_URL = "https://jsearch.p.rapidapi.com/search"
API_KEY = os.environ.get("RAPIDAPI_KEY") or "YOUR_RAPIDAPI_KEY"

KEYWORDS = [
    "Software Engineer",
    "Frontend Developer",
    "UI UX Designer",
    "Software Developer"
]

# ✅ Only keep these exact sources
VALID_SOURCES = ["linkedin", "indeed", "internshala", "naukri"]

# 🚫 Block anything containing these patterns
BLOCK_PATTERNS = [
    r"what.?jobs", r"career", r"careers", r"recruit", r"roche", r"adobe",
    r"agoda", r"ebay", r"barclays", r"philips", r"accenture", r"hitachi",
    r"netapp", r"dice", r"ziprecruiter", r"monster", r"glassdoor",
    r"simplyhired", r"energy", r"bnp", r"shaw", r"team", r"paribas"
]

VALID_CITIES = ["chennai", "bengaluru", "coimbatore"]
FRESHER_KEYWORDS = [
    "fresher", "0 years", "0 year", "entry level", "graduate trainee", "new graduate"
]

CSV_FILENAME = "job_results.csv"

# ---------------- FILTER FUNCTIONS ----------------
def is_valid_source(source: str) -> bool:
    """Allow only exact trusted sources; reject common spam/career sites."""
    if not source:
        return False
    s = source.strip().lower()

    # Reject if any blocked pattern matches
    if any(re.search(pat, s) for pat in BLOCK_PATTERNS):
        return False

    # Accept if the name clearly matches allowed sources
    return any(ok in s for ok in VALID_SOURCES)

def is_valid_city(city: str) -> bool:
    """Check if city is one of Chennai, Bengaluru, Coimbatore."""
    if not city:
        return False
    city = city.lower()
    return any(c in city for c in VALID_CITIES)

def is_fresher_job(title: str, desc: str) -> bool:
    """Detect fresher/0-year roles in title or description."""
    text = f"{title or ''} {desc or ''}".lower()
    return any(k in text for k in FRESHER_KEYWORDS)

# ---------------- FETCH JOBS ----------------
def fetch_jobs(keyword):
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }

    results = []

    for city in VALID_CITIES:
        params = {
            "query": f"{keyword} jobs in {city}",
            "page": "1",
            "num_pages": "1",
            "country": "in",
            "date_posted": "all"
        }

        print(f"[*] Fetching: {keyword} in {city}...")
        try:
            response = requests.get(API_URL, headers=headers, params=params, timeout=30)
            data = response.json()

            for job in data.get("data", []):
                source = job.get("job_publisher", "")
                title = job.get("job_title", "")
                desc = job.get("job_description", "")
                city_name = job.get("job_city", "")

                # Apply filters
                if not is_valid_source(source):
                    continue
                if not is_valid_city(city_name):
                    continue
                if not is_fresher_job(title, desc):
                    continue

                results.append({
                    "title": title,
                    "company": job.get("employer_name", ""),
                    "location": f"{city_name}, {job.get('job_country', '')}",
                    "snippet": desc[:250],
                    "link": job.get("job_apply_link", ""),
                    "source": source
                })

        except Exception as e:
            print(f"[!] Error fetching {keyword} in {city}: {e}")

    print(f"[+] {keyword}: {len(results)} matching jobs found.")
    return results

# ---------------- SAVE TO CSV ----------------
def save_to_csv(jobs):
    if not jobs:
        print("[!] No jobs found.")
        return None

    df = pd.DataFrame(jobs)
    df.to_csv(CSV_FILENAME, index=False, encoding="utf-8")
    print(f"[+] Saved {len(df)} jobs to {CSV_FILENAME}")
    return CSV_FILENAME

# ---------------- MAIN ----------------
if __name__ == "__main__":
    all_jobs = []
    for kw in KEYWORDS:
        all_jobs.extend(fetch_jobs(kw))

    save_to_csv(all_jobs)
