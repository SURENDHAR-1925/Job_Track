#!/usr/bin/env python3
# jobs_scraper_api.py  (you can keep the same name)

import os, time, smtplib, requests, pandas as pd
from typing import List, Dict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from bs4 import BeautifulSoup

KEYWORDS = ["Software Developer", "UI/UX Designer", "Frontend Developer", "Software Engineer"]
CSV_FILENAME = "job_results.csv"

# ------------------ Fetchers ------------------

def fetch_remoteok():
    print("[+] Fetching RemoteOK")
    r = requests.get("https://remoteok.com/api", headers={"User-Agent":"Mozilla/5.0"})
    if r.status_code != 200: return []
    data = r.json()
    jobs = []
    for j in data[1:]:
        title = j.get("position","")
        company = j.get("company","")
        link = j.get("url","")
        location = j.get("location","Remote")
        jobs.append({"title":title,"company":company,"location":location,"snippet":j.get("description","")[:200],"link":link,"source":"RemoteOK"})
    return jobs

def fetch_jsearch(keyword: str):
    print(f"[+] Fetching JSearch for {keyword}")
    # RapidAPI JSearch (free tier)
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": os.getenv("RAPIDAPI_KEY",""),
        "x-rapidapi-host": "jsearch.p.rapidapi.com"
    }
    if not headers["x-rapidapi-key"]:
        print("[!] No RAPIDAPI_KEY provided; skipping JSearch.")
        return []
    params = {"query": keyword, "page": "1", "num_pages": "1"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        data = r.json().get("data", [])
        results = []
        for d in data:
            results.append({
                "title": d.get("job_title",""),
                "company": d.get("employer_name",""),
                "location": d.get("job_city","") or d.get("job_country",""),
                "snippet": d.get("job_description","")[:200],
                "link": d.get("job_apply_link",""),
                "source": "JSearch"
            })
        return results
    except Exception as e:
        print("[!] JSearch error:", e)
        return []

def fetch_google_jobs(keyword: str):
    print(f"[+] Fetching Google Jobs RSS for {keyword}")
    url = f"https://news.google.com/rss/search?q={keyword.replace(' ','%20')}+jobs"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "xml")
    items = soup.find_all("item")
    jobs = []
    for i in items[:20]:
        jobs.append({
            "title": i.title.text,
            "company": "",
            "location": "",
            "snippet": i.description.text[:200],
            "link": i.link.text,
            "source": "GoogleJobs"
        })
    return jobs

# ------------------ Utilities ------------------

def save_csv(data, fname=CSV_FILENAME):
    df = pd.DataFrame(data or [], columns=["title","company","location","snippet","link","source"])
    df.to_csv(fname, index=False)
    return fname

def make_html(items: List[Dict]):
    html = [f"<h2>Job Alerts - {time.strftime('%Y-%m-%d')}</h2>", "<ol>"]
    for x in items:
        html.append(f"<li><b>{x['title']}</b> - {x['company']}<br>"
                    f"<a href='{x['link']}'>Apply</a> "
                    f"<br><small>{x['source']}</small></li>")
    html.append("</ol>")
    return "\n".join(html)

def send_email(body_html, attach=None):
    server = os.environ["EMAIL_SMTP_SERVER"].strip()
    port = int(os.environ["EMAIL_SMTP_PORT"].strip())
    user = os.environ["EMAIL_USER"].strip()
    pwd = os.environ["EMAIL_PASS"].strip()
    to = os.environ["EMAIL_TO"].strip()

    msg = MIMEMultipart()
    msg["From"], msg["To"] = user, to
    msg["Subject"] = "Daily Job Alerts"
    msg.attach(MIMEText(body_html, "html"))

    if attach and os.path.exists(attach):
        with open(attach, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(attach)}"')
            msg.attach(part)

    s = smtplib.SMTP(server, port, timeout=60)
    s.starttls(); s.login(user, pwd)
    s.sendmail(user, [to], msg.as_string()); s.quit()
    print(f"[+] Email sent to {to}")

# ------------------ Main ------------------

if __name__ == "__main__":
    print("[*] Starting API job fetch")

    all_jobs = []
    all_jobs += fetch_remoteok()
    for kw in KEYWORDS:
        all_jobs += fetch_jsearch(kw)
        all_jobs += fetch_google_jobs(kw)
        time.sleep(1)

    # dedupe by title+company+source
    seen, final = set(), []
    for j in all_jobs:
        key = (j["title"]+"|"+j["company"]+"|"+j["source"]).lower()
        if key not in seen:
            seen.add(key)
            final.append(j)

    print(f"[*] Found {len(final)} total jobs")

    csv_file = save_csv(final)
    html_body = make_html(final)
    send_email(html_body, csv_file)

    print("[*] Done. Jobs sent:", len(final))
