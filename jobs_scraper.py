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

# ---------- CONFIG ----------
API_URL = "https://jsearch.p.rapidapi.com/search"
API_KEY = os.environ.get("RAPIDAPI_KEY") or "YOUR_RAPIDAPI_KEY"
KEYWORDS = ["Software Engineer", "Frontend Developer", "UI UX Designer", "Software Developer"]
CSV_FILENAME = "job_results.csv"

# ---------- EMAIL ----------
SMTP_SERVER = os.environ.get("EMAIL_SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", 587))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_TO")

# ---------- FETCH ----------
def fetch_jobs(keyword):
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"}
    params = {
        "query": f"{keyword} jobs in India",
        "page": "1",
        "num_pages": "1",
        "country": "in",
        "date_posted": "all",
    }

    try:
        r = requests.get(API_URL, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        jobs = []
        for j in data.get("data", []):
            jobs.append({
                "title": j.get("job_title", ""),
                "company": j.get("employer_name", ""),
                "location": f"{j.get('job_city','')}, {j.get('job_country','')}",
                "snippet": (j.get("job_description", "") or "")[:250],
                "link": j.get("job_apply_link", ""),
                "source": j.get("job_publisher", "")
            })
        print(f"[+] {len(jobs)} results for {keyword}")
        return jobs
    except Exception as e:
        print(f"[!] Error fetching {keyword}: {e}")
        return []

# ---------- SAVE ----------
def save_to_csv(jobs):
    df = pd.DataFrame(jobs)
    df.to_csv(CSV_FILENAME, index=False)
    print(f"[+] Saved {len(df)} jobs to {CSV_FILENAME}")
    return CSV_FILENAME

# ---------- SEND EMAIL ----------
def send_email(attachment_path=None, job_count=0):
    if not (EMAIL_USER and EMAIL_PASS and EMAIL_TO):
        print("[!] Missing email credentials.")
        return

    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg["Reply-To"] = EMAIL_USER
    msg["Subject"] = f"Daily Job Alerts ({job_count} results) - {datetime.now():%Y-%m-%d %H:%M}"
    msg["X-Mailer"] = "GitHub-Actions-Mailer"

    body = (
        f"Attached are {job_count} job results for today.\n\n-- Automated Daily Job Tracker"
        if job_count > 0
        else "No new job results today.\n\nThis is a Gmail delivery test — email system is working correctly."
    )
    msg.attach(MIMEText(body, "plain"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(attachment_path)}")
        msg.attach(part)

    try:
        print(f"[*] Connecting to {SMTP_SERVER}:{SMTP_PORT} as {EMAIL_USER}")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=60) as s:
            s.set_debuglevel(1)  # 🔍 show full SMTP conversation
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(EMAIL_USER, EMAIL_PASS)
            print("[SMTP] Login successful.")
            resp = s.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
            print("[SMTP] Server response:", resp)
        print("[+] Email sent successfully to:", EMAIL_TO)
    except Exception as e:
        print(f"[!] Email failed: {e}")

# ---------- MAIN ----------
if __name__ == "__main__":
    all_jobs = []
    for kw in KEYWORDS:
        all_jobs.extend(fetch_jobs(kw))

    if all_jobs:
        csv_file = save_to_csv(all_jobs)
        send_email(csv_file, len(all_jobs))
    else:
        print("[!] No jobs found, sending test email...")
        send_email(None, 0)
