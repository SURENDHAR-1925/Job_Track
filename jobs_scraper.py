#!/usr/bin/env python3
import os
import requests
import pandas as pd
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# CONFIG
KEYWORDS = ["Software Developer", "UI/UX Designer", "Frontend Developer", "Software Engineer"]
CSV_FILENAME = "job_results.csv"
API_URL = "https://jsearch.p.rapidapi.com/search"

def fetch_jobs(keyword):
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        print("[!] Missing RAPIDAPI_KEY in environment")
        return []

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {"query": keyword, "page": "1", "num_pages": "1"}
    print(f"[*] Fetching jobs for: {keyword}")
    try:
        r = requests.get(API_URL, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        results = []
        for d in data:
            results.append({
                "title": d.get("job_title", ""),
                "company": d.get("employer_name", ""),
                "location": d.get("job_city", ""),
                "snippet": d.get("job_description", "")[:200],
                "link": d.get("job_apply_link", ""),
                "source": "JSearch"
            })
        return results
    except Exception as e:
        print("[!] Error fetching JSearch:", e)
        return []

def save_csv(data):
    df = pd.DataFrame(data or [], columns=["title", "company", "location", "snippet", "link", "source"])
    df.to_csv(CSV_FILENAME, index=False)
    return CSV_FILENAME

def send_email(attachment):
    smtp_server = os.environ.get("EMAIL_SMTP_SERVER")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    user = os.environ.get("EMAIL_USER")
    pwd = os.environ.get("EMAIL_PASS")
    to = os.environ.get("EMAIL_TO")

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = f"Job Alerts - {time.strftime('%Y-%m-%d')}"
    msg.attach(MIMEText("Here are your daily job alerts. See attached CSV file.", "plain"))

    if attachment and os.path.exists(attachment):
        with open(attachment, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{attachment}"')
            msg.attach(part)

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(user, pwd)
        server.sendmail(user, [to], msg.as_string())
        server.quit()
        print(f"[+] Email sent to {to}")
    except Exception as e:
        print("[!] Email sending failed:", e)

if __name__ == "__main__":
    all_jobs = []
    for kw in KEYWORDS:
        all_jobs += fetch_jobs(kw)
        time.sleep(1.5)

    print(f"[*] Total jobs fetched: {len(all_jobs)}")
    csv_file = save_csv(all_jobs)
    send_email(csv_file)
    print("[*] Done!")
