#!/usr/bin/env python3
# jobs_scraper.py
# Run by GitHub Actions. Uses Playwright to render pages and BeautifulSoup to parse.
# Expects SMTP env vars (set as GitHub Secrets): EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_USER, EMAIL_PASS, EMAIL_TO

import os
import time
import csv
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Dict
from dateutil import parser as dateparser
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import pandas as pd

# ----- CONFIG -----
KEYWORDS = ["Software Developer", "UI/UX Designer", "Frontend Developer", "Software Engineer"]
PLATFORMS = ["naukri", "internshala", "indeed", "google", "linkedin"]
MAX_PER_PLATFORM = 20
CSV_FILENAME = "job_results.csv"

# ----- HELPERS -----
def normalize_text(s):
    if not s:
        return ""
    return " ".join(s.split())

def build_queries(keywords: List[str], platform: str) -> List[str]:
    qs = []
    for kw in keywords:
        if platform == "naukri":
            qs.append(f"https://www.naukri.com/{kw.replace(' ', '-')}-jobs")
        elif platform == "internshala":
            qs.append(f"https://internshala.com/internships/{kw.replace(' ', '-')}-internship")
        elif platform == "indeed":
            qs.append(f"https://www.indeed.co.in/jobs?q={kw.replace(' ', '+')}&l=")
        elif platform == "linkedin":
            qs.append(f"https://www.linkedin.com/jobs/search?keywords={kw.replace(' ', '%20')}")
        elif platform == "google":
            qs.append(f"https://www.google.com/search?q={kw.replace(' ', '+')}+jobs")
    return qs

# parsers (best-effort)
def parse_naukri(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for card in soup.select("article.jobTuple, .jobTuple")[:MAX_PER_PLATFORM]:
        try:
            title = normalize_text((card.select_one('.title a') or card.select_one('.jobTitle') or "").get_text())
        except:
            title = ""
        company = normalize_text(card.select_one('.subTitle span').get_text() if card.select_one('.subTitle span') else "")
        loc = normalize_text(card.select_one('.location').get_text() if card.select_one('.location') else "")
        snippet = normalize_text(card.select_one('.job-description').get_text() if card.select_one('.job-description') else "")
        link_tag = card.select_one('a')
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""
        results.append({"title": title, "company": company, "location": loc, "snippet": snippet, "link": link, "source": "Naukri"})
    return results

def parse_internshala(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for card in soup.select('div.single_internship')[:MAX_PER_PLATFORM]:
        title_tag = card.select_one('.profile a')
        title = normalize_text(title_tag.get_text()) if title_tag else ""
        company = normalize_text(card.select_one('.company a').get_text() if card.select_one('.company a') else "")
        loc = normalize_text(card.select_one('.location_link').get_text() if card.select_one('.location_link') else "")
        link = "https://internshala.com" + title_tag['href'] if title_tag and title_tag.has_attr('href') else ""
        results.append({"title": title, "company": company, "location": loc, "snippet": "", "link": link, "source": "Internshala"})
    return results

def parse_indeed(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for card in soup.select('a.tapItem, .result')[:MAX_PER_PLATFORM]:
        title = normalize_text(card.select_one('h2.jobTitle').get_text() if card.select_one('h2.jobTitle') else (card.select_one('.jobTitle').get_text() if card.select_one('.jobTitle') else ""))
        company = normalize_text(card.select_one('.companyName').get_text() if card.select_one('.companyName') else "")
        loc = normalize_text(card.select_one('.companyLocation').get_text() if card.select_one('.companyLocation') else "")
        link = card['href'] if card.has_attr('href') and card['href'].startswith('http') else ("https://www.indeed.co.in" + card['href'] if card.has_attr('href') else "")
        snippet = normalize_text(card.select_one('.job-snippet').get_text() if card.select_one('.job-snippet') else "")
        results.append({"title": title, "company": company, "location": loc, "snippet": snippet, "link": link, "source": "Indeed"})
    return results

def parse_google(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    seen_texts = 0
    for card in soup.select('div')[:MAX_PER_PLATFORM*4]:
        text = card.get_text(separator=" ", strip=True)
        if len(text) < 30:
            continue
        if "company" in text.lower() or "hiring" in text.lower() or "jobs" in text.lower() or "posted" in text.lower():
            results.append({"title": text[:80]+"...", "company": "", "location": "", "snippet": text, "link": "", "source": "GoogleSearch"})
            seen_texts += 1
        if seen_texts >= MAX_PER_PLATFORM:
            break
    return results

def parse_linkedin(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for card in soup.select('.result-card, .jobs-search-results__list-item')[:MAX_PER_PLATFORM]:
        title = normalize_text(card.select_one('h3').get_text() if card.select_one('h3') else "")
        company = normalize_text(card.select_one('.result-card__subtitle, .job-card-container__company-name').get_text() if card.select_one('.result-card__subtitle, .job-card-container__company-name') else "")
        loc = normalize_text(card.select_one('.job-result-card__location').get_text() if card.select_one('.job-result-card__location') else "")
        link_tag = card.select_one('a')
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""
        results.append({"title": title, "company": company, "location": loc, "snippet": "", "link": link, "source": "LinkedIn"})
    return results

# ----- SCRAPE ALL -----
def scrape_all(keywords):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()
        for platform in PLATFORMS:
            queries = build_queries(keywords, platform)
            platform_results = []
            for q in queries:
                try:
                    page.goto(q, timeout=35000)
                    time.sleep(2.2)
                    html = page.content()
                    if platform == "naukri":
                        platform_results.extend(parse_naukri(html))
                    elif platform == "internshala":
                        platform_results.extend(parse_internshala(html))
                    elif platform == "indeed":
                        platform_results.extend(parse_indeed(html))
                    elif platform == "google":
                        platform_results.extend(parse_google(html))
                    elif platform == "linkedin":
                        platform_results.extend(parse_linkedin(html))
                except Exception as e:
                    print(f"[!] Error fetching {q}: {e}")
                if len(platform_results) >= MAX_PER_PLATFORM:
                    break
            # dedupe by link/title+company
            seen = set()
            dedup = []
            for r in platform_results:
                key = r.get("link") or (r.get("title","")+ "|" + r.get("company",""))
                if key in seen:
                    continue
                seen.add(key)
                dedup.append(r)
            results.extend(dedup[:MAX_PER_PLATFORM])
        browser.close()
    return results

# ----- EMAIL & CSV -----
def save_csv(results, fname=CSV_FILENAME):
    if not results:
        # write empty file with header
        df = pd.DataFrame([], columns=["title","company","location","snippet","link","source"])
        df.to_csv(fname, index=False)
        return fname
    df = pd.DataFrame(results)
    df.to_csv(fname, index=False)
    return fname

def make_html(results):
    html = []
    html.append("<html><body>")
    html.append(f"<h2>Job Alerts — {time.strftime('%Y-%m-%d %H:%M:%S')}</h2>")
    html.append(f"<p>Keywords: {', '.join(KEYWORDS)}</p>")
    html.append("<ol>")
    for r in results:
        html.append("<li style='margin-bottom:12px'>")
        html.append(f"<strong>{r.get('title','No title')}</strong><br>")
        html.append(f"{r.get('company','')} — {r.get('location','')}<br>")
        if r.get('link'):
            html.append(f"<a href='{r.get('link')}'>View / Apply</a><br>")
        if r.get('snippet'):
            html.append(f"<small>{r.get('snippet')[:300]}...</small><br>")
        html.append(f"<small>Source: {r.get('source')}</small>")
        html.append("</li>")
    html.append("</ol>")
    html.append("</body></html>")
    return "\n".join(html)

def send_email(html_body, attachment_path=None):
    smtp_server = os.environ.get("EMAIL_SMTP_SERVER")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    user = os.environ.get("EMAIL_USER")
    pwd = os.environ.get("EMAIL_PASS")
    to_addr = os.environ.get("EMAIL_TO")

    if not (smtp_server and user and pwd and to_addr):
        print("[!] Missing SMTP settings. Aborting email send.")
        return False

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = f"Job Alerts — {time.strftime('%Y-%m-%d %H:%M:%S')}"
    msg.attach(MIMEText("Open in HTML-capable client.", "plain"))
    msg.attach(MIMEText(html_body, "html"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(attachment_path)}"')
            msg.attach(part)

    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=60)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(user, pwd)
        server.sendmail(user, [to_addr], msg.as_string())
        server.quit()
        print("[+] Email sent to", to_addr)
        return True
    except Exception as e:
        print("[!] Failed to send email:", e)
        return False

# ----- MAIN -----
if __name__ == "__main__":
    print("[*] Starting scraping")
    jobs = scrape_all(KEYWORDS)
    # Filter to ensure keywords appear in text (case-insensitive)
    k_lower = [k.lower() for k in KEYWORDS]
    filtered = []
    seen = set()
    for j in jobs:
        content = " ".join([j.get("title",""), j.get("company",""), j.get("snippet","")]).lower()
        if any(k in content for k in k_lower):
            key = j.get("link") or (j.get("title","")+ "|" + j.get("company",""))
            if key not in seen:
                seen.add(key)
                filtered.append(j)
    # save CSV and send email
    csv_file = save_csv(filtered)
    html = make_html(filtered)
    send_email(html, attachment_path=csv_file)
    print("[*] Done. Found", len(filtered), "jobs.")
