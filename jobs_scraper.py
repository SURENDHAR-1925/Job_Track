#!/usr/bin/env python3
import os
import re
import requests
import pandas as pd
import smtplib
from urllib.parse import urlparse
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

# ---------- CONFIG ----------
API_URL = "https://jsearch.p.rapidapi.com/search"
API_KEY = os.environ.get("RAPIDAPI_KEY") or "YOUR_RAPIDAPI_KEY"

KEYWORDS = [
    "Software Engineer",
    "Frontend Developer",
    "UI UX Designer",
    "Software Developer"
]

# Allowed publisher substrings and link domains
ALLOWED_PUBLISHER_SUBSTRINGS = ["linkedin", "indeed", "internshala", "naukri"]
ALLOWED_DOMAINS = ["linkedin.com", "naukri.com", "indeed.com", "internshala.com"]

# Cities and fresher keywords
VALID_CITIES = ["chennai", "bengaluru", "coimbatore"]
FRESHER_KEYWORDS = ["fresher", "0 years", "0 year", "entry level", "graduate trainee", "new graduate", "freshers"]

CSV_ACCEPT = "job_results.csv"
CSV_REJECT = "rejected_jobs.csv"

# Email config (provided via GitHub Actions secrets)
SMTP_SERVER = os.environ.get("EMAIL_SMTP_SERVER")
SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_TO")

# ---------- helpers ----------
def clean(s):
    return (s or "").strip().lower()

def domain_from_url(url):
    try:
        p = urlparse(url)
        host = p.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except:
        return ""

def allowed_by_domain(link):
    d = domain_from_url(link)
    if not d:
        return False
    return any(ad in d for ad in ALLOWED_DOMAINS)

def allowed_by_publisher(pub):
    s = clean(pub)
    return any(tok in s for tok in ALLOWED_PUBLISHER_SUBSTRINGS)

def is_valid_city(city):
    s = clean(city)
    return any(vc in s for vc in VALID_CITIES)

def is_fresher(title, desc):
    text = f"{title or ''} {desc or ''}".lower()
    return any(k in text for k in FRESHER_KEYWORDS)

# ---------- fetch ----------
def fetch_for_keyword_and_city(keyword, city):
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {
        "query": f"{keyword} jobs in {city}",
        "page": "1",
        "num_pages": "1",
        "country": "in",
        "date_posted": "all"
    }
    try:
        r = requests.get(API_URL, headers=headers, params=params, timeout=30)
        data = r.json()
        return data.get("data", [])
    except Exception as e:
        print("[!] API error:", e)
        return []

# ---------- email ----------
def send_email_with_attachment(path, count):
    if not (SMTP_SERVER and EMAIL_USER and EMAIL_PASS and EMAIL_TO):
        print("[!] Email config missing. Skipping email.")
        return

    subject = f"Fresher Jobs ({count}) — LinkedIn/Indeed/Internshala/Naukri — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    body = f"Attached are {count} fresher jobs (Chennai/Bengaluru/Coimbatore)."

    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if os.path.exists(path):
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        msg.attach(part)

    try:
        print("[*] Connecting to SMTP:", SMTP_SERVER, SMTP_PORT)
        s = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=60)
        s.ehlo()
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        s.quit()
        print("[+] Email sent successfully to", EMAIL_TO)
    except Exception as e:
        print("[!] Email failed:", e)

def test_email():
    """Send a quick test email before job scraping."""
    if not (SMTP_SERVER and EMAIL_USER and EMAIL_PASS and EMAIL_TO):
        print("[!] Email config missing for test.")
        return
    try:
        msg = MIMEText("✅ Test email from GitHub Actions Job Tracker.\nIf you see this, your email setup works!")
        msg["Subject"] = "GitHub Actions Email Test"
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_TO
        s = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30)
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.sendmail(EMAIL_USER, [EMAIL_TO], msg.as_string())
        s.quit()
        print("[+] Test email sent successfully.")
    except Exception as e:
        print("[!] Test email failed:", e)

# ---------- main ----------
def main():
    accepted, rejected = [], []

    for kw in KEYWORDS:
        for city in VALID_CITIES:
            print(f"[*] Searching '{kw}' in {city} ...")
            items = fetch_for_keyword_and_city(kw, city)
            print(f"    -> returned {len(items)} items")

            for job in items:
                title = job.get("job_title", "")
                desc = job.get("job_description", "")
                pub = job.get("job_publisher", "")
                job_city = job.get("job_city", "")
                link = job.get("job_apply_link") or job.get("job_link") or ""

                domain_ok = allowed_by_domain(link)
                pub_ok = allowed_by_publisher(pub)
                city_ok = is_valid_city(job_city) or is_valid_city(city)
                fresher_ok = is_fresher(title, desc)

                if (domain_ok or pub_ok) and city_ok and fresher_ok:
                    accepted.append({
                        "title": title,
                        "company": job.get("employer_name", ""),
                        "location": f"{job_city}, {job.get('job_country','')}",
                        "snippet": desc[:300],
                        "link": link,
                        "source": pub
                    })
                else:
                    reason = []
                    if not (domain_ok or pub_ok): reason.append("bad_source")
                    if not city_ok: reason.append("bad_city")
                    if not fresher_ok: reason.append("not_fresher")
                    rejected.append({
                        "title": title, "company": job.get("employer_name", ""),
                        "location": job_city, "link": link, "source": pub,
                        "reason": ",".join(reason)
                    })

    # Save CSVs
    pd.DataFrame(accepted).to_csv(CSV_ACCEPT, index=False)
    pd.DataFrame(rejected).to_csv(CSV_REJECT, index=False)
    print(f"[+] Accepted {len(accepted)} -> {CSV_ACCEPT}")
    print(f"[+] Rejected {len(rejected)} -> {CSV_REJECT}")

    if accepted:
        send_email_with_attachment(CSV_ACCEPT, len(accepted))
    else:
        print("[*] No accepted jobs to email.")

if __name__ == "__main__":
    print("[*] EMAIL CONFIG:", SMTP_SERVER, SMTP_PORT, EMAIL_USER, "TO:", EMAIL_TO)
    test_email()  # <-- Always send a test mail before scraping
    main()
