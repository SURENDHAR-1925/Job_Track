#!/usr/bin/env python3
# jobs_scraper.py

import os
import time
import smtplib
import pandas as pd
from pathlib import Path
from typing import List, Dict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# ----- CONFIG -----
KEYWORDS = ["Software Developer", "UI/UX Designer", "Frontend Developer", "Software Engineer","Data Analyst"]
PLATFORMS = ["naukri", "internshala", "linkedin"]
MAX_PER_PLATFORM = 20
CSV_FILENAME = "job_results.csv"

# create folder for debug HTML
DEBUG_HTML_DIR = Path("debug_html")
DEBUG_HTML_DIR.mkdir(exist_ok=True)

# ----- HELPERS -----
def normalize_text(s: str) -> str:
    return " ".join(s.split()) if s else ""

def build_queries(keywords: List[str], platform: str) -> List[str]:
    qs = []
    for kw in keywords:
        kw_dash = kw.replace(" ", "-")
        kw_plus = kw.replace(" ", "+")
        kw_url = kw.replace(" ", "%20")

        if platform == "naukri":
            qs.append(f"https://www.naukri.com/{kw_dash}-jobs")
        elif platform == "internshala":
            qs.append(f"https://internshala.com/internships/{kw_dash}-internship")
        elif platform == "linkedin":
            qs.append(f"https://www.linkedin.com/jobs/search?keywords={kw_url}")
    return qs

def save_debug_html(platform: str, idx: int, html: str):
    fname = DEBUG_HTML_DIR / f"{platform}_{idx}.html"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[debug] Saved HTML -> {fname}")

# ----- PARSERS -----
def parse_naukri(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("article.jobTuple, .jobTuple")[:MAX_PER_PLATFORM]
    data = []
    for card in cards:
        title = normalize_text(card.select_one(".title a, .jobTitle").get_text()) if card.select_one(".title a, .jobTitle") else ""
        company = normalize_text(card.select_one(".subTitle span").get_text() if card.select_one(".subTitle span") else "")
        loc = normalize_text(card.select_one(".location").get_text() if card.select_one(".location") else "")
        snippet = normalize_text(card.select_one(".job-description").get_text() if card.select_one(".job-description") else "")
        link = card.select_one("a")["href"] if card.select_one("a") and card.select_one("a").has_attr("href") else ""
        data.append({"title": title, "company": company, "location": loc, "snippet": snippet, "link": link, "source": "Naukri"})
    return data

def parse_internshala(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    data = []
    for card in soup.select("div.single_internship")[:MAX_PER_PLATFORM]:
        title_tag = card.select_one(".profile a")
        title = normalize_text(title_tag.get_text()) if title_tag else ""
        company = normalize_text(card.select_one(".company a").get_text() if card.select_one(".company a") else "")
        loc = normalize_text(card.select_one(".location_link").get_text() if card.select_one(".location_link") else "")
        link = "https://internshala.com" + title_tag["href"] if title_tag and title_tag.has_attr("href") else ""
        data.append({"title": title, "company": company, "location": loc, "snippet": "", "link": link, "source": "Internshala"})
    return data
def parse_linkedin(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for card in soup.select(".jobs-search-results__list-item, .job-card-container, .result-card")[:MAX_PER_PLATFORM]:
        title = normalize_text(card.select_one("h3, .job-card-list__title, .result-card__title").get_text() if card.select_one("h3, .job-card-list__title, .result-card__title") else "")
        company = normalize_text(card.select_one(".job-card-container__company-name, .result-card__subtitle, .job-result-card__subtitle").get_text() if card.select_one(".job-card-container__company-name, .result-card__subtitle, .job-result-card__subtitle") else "")
        link = card.select_one("a")["href"] if card.select_one("a") and card.select_one("a").has_attr("href") else ""
        results.append({"title": title, "company": company, "location": "", "snippet": "", "link": link, "source": "LinkedIn"})
    return results

# ----- SCRAPER -----
def scrape_all(keywords):
    results = []
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=ua, viewport={"width":1280,"height":800}, locale="en-US")
        page = context.new_page()

        for platform in PLATFORMS:
            print(f"[+] Starting platform: {platform}")
            queries = build_queries(KEYWORDS, platform)
            platform_results = []

            for idx, q in enumerate(queries, 1):
                print(f"[+] Visiting ({platform}) {q}")
                try:
                    page.goto(q, timeout=60000)
                    time.sleep(5)
                    html = page.content()
                    save_debug_html(platform, idx, html)

                    if platform == "naukri":
                        platform_results.extend(parse_naukri(html))
                    elif platform == "internshala":
                        platform_results.extend(parse_internshala(html))
                    elif platform == "linkedin":
                        platform_results.extend(parse_linkedin(html))
                except Exception as e:
                    print(f"[!] Error visiting {q}: {e}")

                time.sleep(1.2)

            # dedupe
            seen = set()
            dedup = []
            for r in platform_results:
                key = (r.get("link") or (r.get("title","") + "|" + r.get("company",""))).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                dedup.append(r)

            print(f"[+] {platform} returned {len(dedup)} jobs")
            results.extend(dedup[:MAX_PER_PLATFORM])

        context.close()
        browser.close()

    print(f"[*] Total results found: {len(results)}")
    return results

# ----- SAVE & EMAIL -----
def save_csv(data, fname=CSV_FILENAME):
    df = pd.DataFrame(data or [], columns=["title","company","location","snippet","link","source"])
    df.to_csv(fname, index=False)
    return fname

def make_html(items: List[Dict]):
    html = [f"<h2>Job Alerts - {time.strftime('%Y-%m-%d')}</h2>", "<ol>"]
    for x in items:
        html.append(f"<li><b>{x['title']}</b> - {x['company']}<br><a href='{x['link']}'>Apply</a> <br><small>{x['source']}</small></li>")
    html.append("</ol>")
    return "\n".join(html)

def send_email(body_html, attach=None):
    server = os.environ["EMAIL_SMTP_SERVER"]
    port = int(os.environ["EMAIL_SMTP_PORT"].strip())
    user = os.environ["EMAIL_USER"].strip()
    pwd = os.environ["EMAIL_PASS"].strip()
    to = os.environ["EMAIL_TO"].strip()

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to
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
    s.starttls()
    s.login(user, pwd)
    s.sendmail(user, [to], msg.as_string())
    s.quit()
    print(f"[+] Email sent to {to}")

# ----- MAIN -----
if __name__ == "__main__":
    all_jobs = scrape_all(KEYWORDS)

    # final keyword filtering
    keys = [k.lower() for k in KEYWORDS]
    filtered = []
    seen = set()
    for j in all_jobs:
        txt = (j["title"] + j["company"] + j["snippet"]).lower()
        if any(k in txt for k in keys):
            key = j.get("link") or (j["title"] + "|" + j["company"])
            if key not in seen:
                seen.add(key)
                filtered.append(j)

    csv_file = save_csv(filtered)
    html_body = make_html(filtered)
    send_email(html_body, csv_file)
    print("[*] Done. Jobs sent:", len(filtered))
