#!/usr/bin/env python3
import os
import requests
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

# ---------------- CONFIG ----------------
API_URL = "https://jsearch.p.rapidapi.com/search"
API_KEY = "38d41a5027msh6d8e74569f19c5ap1bf2cejsn9cb1273e3bbe"

KEYWORDS = [
    "Software Engineer",
    "Frontend Developer",
    "UI UX Designer",
    "Software Developer"
]

VALID_SOURCES = ["linkedin", "Narkri", "internshala"]
VALID_CITIES = ["chennai", "bengaluru", "coimbatore"]
FRESHER_KEYWORDS = ["fresher", "0 years", "0 year", "entry level", "graduate trainee"]

CSV_FILENAME = "job_results.csv"

# ---------------- EMAIL CONFIG ----------------
SMTP_SERVER = os.environ.get("EMAIL_SMTP_SERVER")
SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", 587))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_TO")

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

        print(f"[*] Searching '{keyword}' in {city}...")
        try:
            response = requests.get(API_URL, headers=headers, params=params)
            data = response.json()

            if "data" not in data:
                continue

            for job in data["data"]:
                publisher = (job.get("job_publisher") or "").strip().lower()
                city_name = (job.get("job_city") or "").strip().lower()
                title = (job.get("job_title") or "").lower()
                desc = (job.get("job_description") or "").lower()

                # ✅ Initial filtering
                if not any(src in publisher for src in VALID_SOURCES):
                    continue
                if not any(city in city_name for city in VALID_CITIES):
                    continue
                if not any(k in title or k in desc for k in FRESHER_KEYWORDS):
                    continue

                results.append({
                    "title": job.get("job_title", ""),
                    "company": job.get("employer_name", ""),
                    "location": f"{job.get('job_city', '')}, {job.get('job_country', '')}",
                    "snippet": (job.get("job_description", "") or "")[:250],
                    "link": job.get("job_apply_link", ""),
                    "source": job.get("job_publisher", "")
                })

        except Exception as e:
            print(f"[!] Error fetching '{keyword}' in {city}: {e}")

    print(f"[+] {keyword}: {len(results)} fresher jobs found.")
    return results


# ---------------- SAVE TO CSV ----------------
def save_to_csv(jobs):
    if not jobs:
        print("[!] No jobs found.")
        return None

    df = pd.DataFrame(jobs)

    # 🧹 Post-filter to clean everything again
    def is_valid_source(s):
        s = str(s).lower()
        return any(src in s for src in VALID_SOURCES)

    def is_valid_city(loc):
        loc = str(loc).lower()
        return any(city in loc for city in VALID_CITIES)

    def is_fresher(snippet, title):
        text = f"{title} {snippet}".lower()
        return any(k in text for k in FRESHER_KEYWORDS)

    before = len(df)
    df = df[df["source"].apply(is_valid_source)]
    df = df[df["location"].apply(is_valid_city)]
    df = df[df.apply(lambda x: is_fresher(x["snippet"], x["title"]), axis=1)]
    after = len(df)

    print(f"[+] Filtered {before} → {after} final fresher jobs.")
    df.to_csv(CSV_FILENAME, index=False)
    print(f"[+] Saved {CSV_FILENAME}")
    return CSV_FILENAME


# ---------------- EMAIL RESULTS ----------------
def send_email(attachment_path, job_count):
    if not (SMTP_SERVER and EMAIL_USER and EMAIL_PASS and EMAIL_TO):
        print("[!] Missing email credentials.")
        return

    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = f"Daily Fresher Jobs - {datetime.now().strftime('%Y-%m-%d')}"

    body = (
        f"Here are {job_count} verified fresher/0-year experience jobs "
        f"from LinkedIn, Indeed, and Internshala "
        f"in Chennai, Bengaluru, and Coimbatore."
    )
    msg.attach(MIMEText(body, "plain"))

    with open(attachment_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(attachment_path)}")
        msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print("[+] Email sent successfully.")
    except Exception as e:
        print(f"[!] Email sending failed: {e}")


# ---------------- MAIN ----------------
if __name__ == "__main__":
    all_jobs = []
    for kw in KEYWORDS:
        all_jobs.extend(fetch_jobs(kw))

    if all_jobs:
        csv_path = save_to_csv(all_jobs)
        if csv_path:
            df = pd.read_csv(csv_path)
            send_email(csv_path, len(df))
    else:
        print("[!] No matching fresher jobs found.")
