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

# ----------------- CONFIG -----------------
API_URL = "https://jsearch.p.rapidapi.com/search"
API_KEY = "38d41a5027msh6d8e74569f19c5ap1bf2cejsn9cb1273e3bbe"

KEYWORDS = [
    "Software Engineer",
    "Frontend Developer",
    "UI UX Designer",
    "Software Developer"
]

# only from these sources
ALLOWED_SOURCES = ["LinkedIn", "Indeed", "Internshala"]

# only in these locations
ALLOWED_CITIES = ["Chennai", "Bengaluru", "Coimbatore"]

CSV_FILENAME = "job_results.csv"
MAX_RESULTS = 30

# ----------------- EMAIL CONFIG -----------------
SMTP_SERVER = os.environ.get("EMAIL_SMTP_SERVER")
SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", 587))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_TO")

# ----------------- FETCH JOBS -----------------
def fetch_jobs(keyword):
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }

    # Build query for multiple cities
    city_query = " OR ".join([f"{keyword} jobs in {city}" for city in ALLOWED_CITIES])

    params = {
        "query": city_query,
        "page": "1",
        "num_pages": "1",
        "country": "in",
        "date_posted": "all"
    }

    try:
        response = requests.get(API_URL, headers=headers, params=params)
        data = response.json()

        results = []
        for job in data.get("data", []):
            publisher = job.get("job_publisher", "").lower()
            city = job.get("job_city", "")
            if any(source.lower() in publisher for source in ALLOWED_SOURCES) and \
               any(loc.lower() in city.lower() for loc in ALLOWED_CITIES):

                results.append({
                    "title": job.get("job_title", ""),
                    "company": job.get("employer_name", ""),
                    "location": f"{job.get('job_city', '')}, {job.get('job_country', '')}",
                    "snippet": job.get("job_description", "")[:250],
                    "link": job.get("job_apply_link", ""),
                    "source": job.get("job_publisher", "")
                })

        print(f"[+] {keyword}: Found {len(results)} filtered jobs.")
        return results
    except Exception as e:
        print(f"[!] Error fetching {keyword}: {e}")
        return []

# ----------------- SAVE TO CSV -----------------
def save_to_csv(jobs):
    df = pd.DataFrame(jobs)
    df.to_csv(CSV_FILENAME, index=False)
    print(f"[+] Saved {len(df)} jobs to {CSV_FILENAME}")
    return CSV_FILENAME

# ----------------- EMAIL RESULTS -----------------
def send_email(attachment_path, job_count):
    if not (SMTP_SERVER and EMAIL_USER and EMAIL_PASS and EMAIL_TO):
        print("[!] Missing email credentials.")
        return

    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = f"Daily LinkedIn/Indeed/Internshala Jobs - {datetime.now().strftime('%Y-%m-%d')}"

    body = f"Here are the latest {job_count} jobs from LinkedIn, Indeed, and Internshala in Chennai, Bengaluru, and Coimbatore."
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
        print(f"[!] Failed to send email: {e}")

# ----------------- MAIN -----------------
if __name__ == "__main__":
    all_jobs = []
    for kw in KEYWORDS:
        print(f"[*] Searching for: {kw}")
        all_jobs.extend(fetch_jobs(kw))

    if all_jobs:
        csv_path = save_to_csv(all_jobs)
        send_email(csv_path, len(all_jobs))
    else:
        print("[!] No jobs found.")
