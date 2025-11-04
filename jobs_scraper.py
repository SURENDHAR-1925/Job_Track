#!/usr/bin/env python3
# jobs_scraper.py

import os
import time
import smtplib
import pandas as pd
from typing import List, Dict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# ----- CONFIG -----
KEYWORDS = ["Software Developer", "UI/UX Designer", "Frontend Developer", "Software Engineer"]
PLATFORMS = ["naukri", "internshala", "indeed", "google", "linkedin"]
MAX_PER_PLATFORM = 20
CSV_FILENAME = "job_results.csv"


# ----- HELPERS -----
def normalize_text(s: str) -> str:
    return " ".join(s.split()) if s else ""


def build_queries(keywords: List[str], platform: str) -> List[str]:
    qs = []
    for kw in keywords:
        kw_dash = kw.replace(" ", "-")
        kw_plus = kw.replace(" ", "+")
        kw_url = kw.replace(" ", "%20")

        match platform:
            case "naukri":
                qs.append(f"https://www.naukri.com/{kw_dash}-jobs")
            case "internshala":
                qs.append(f"https://internshala.com/internships/{kw_dash}-internship")
            case "indeed":
                qs.append(f"https://www.indeed.co.in/jobs?q={kw_plus}&l=")
            case "linkedin":
                qs.append(f"https://www.linkedin.com/jobs/search?keywords={kw_url}")
            case "google":
                qs.append(f"https://www.google.com/search?q={kw_plus}+jobs")

    return qs


# ---- PARSERS ----
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


def parse_indeed(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    data = []
    for card in soup.select("a.tapItem, .result")[:MAX_PER_PLATFORM]:
        title = normalize_text(card.select_one("h2.jobTitle, .jobTitle").get_text() if (card.select_one("h2.jobTitle") or card.select_one(".jobTitle")) else "")
        company = normalize_text(card.select_one(".companyName").get_text() if card.select_one(".companyName") else "")
        loc = normalize_text(card.select_one(".companyLocation").get_text() if card.select_one(".companyLocation") else "")
        href = card["href"] if card.has_attr("href") else ""
        link = href if "http" in href else ("https://www.indeed.co.in" + href if href else "")
        snippet = normalize_text(card.select_one(".job-snippet").get_text() if card.select_one(".job-snippet") else "")
        data.append({"title": title, "company": company, "location": loc, "snippet": snippet, "link": link, "source": "Indeed"})
    return data


def parse_google(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for card in soup.select("div")[:MAX_PER_PLATFORM * 4]:
        text = card.get_text(" ", strip=True)
        if len(text) > 30 and any(x in text.lower() for x in ["company", "hiring", "jobs"]):
            results.append({"title": text[:80] + "...", "company": "", "location": "", "snippet": text, "link": "", "source": "GoogleSearch"})
            if len(results) >= MAX_PER_PLATFORM:
                break
    return results


def parse_linkedin(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    for card in soup.select(".result-card, .jobs-search-results__list-item")[:MAX_PER_PLATFORM]:
        title = normalize_text(card.select_one("h3").get_text() if card.select_one("h3") else "")
        company = normalize_text(card.select_one(".result-card__subtitle, .job-card-container__company-name").get_text() if card.select_one(".result-card__subtitle, .job-card-container__company-name") else "")
        loc = normalize_text(card.select_one(".job-result-card__location").get_text() if card.select_one(".job-result-card__location") else "")
        link = card.select_one("a")["href"] if card.select_one("a") and card.select_one("a").has_attr("href") else ""
        results.append({"title": title, "company": company, "location": loc, "snippet": "", "link": link, "source": "LinkedIn"})
    return results


# SCRAPER
def scrape_all(keys: List[str]) -> List[Dict]:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page()

        for pf in PLATFORMS:
            data = []
            for q in build_queries(keys, pf):
                try:
                    page.goto(q, timeout=35000)
                    time.sleep(2)
                    html = page.content()
                    match pf:
                        case "naukri": data.extend(parse_naukri(html))
                        case "internshala": data.extend(parse_internshala(html))
                        case "indeed": data.extend(parse_indeed(html))
                        case "google": data.extend(parse_google(html))
                        case "linkedin": data.extend(parse_linkedin(html))
                except Exception as e:
                    print(f"[!] {pf} error {e}")

            # dedupe
            seen = set()
            final = []
            for r in data:
                key = r.get("link") or (r["title"] + "|" + r["company"])
                if key in seen: continue
                seen.add(key)
                final.append(r)

            results.extend(final[:MAX_PER_PLATFORM])

        browser.close()
    return results


def save_csv(data, fname=CSV_FILENAME):
    df = pd.DataFrame(data or [], columns=["title","company","location","snippet","link","source"])
    df.to_csv(fname, index=False)
    return fname


def send_email(body_html, attach=None):
    server = os.environ["EMAIL_SMTP_SERVER"]
    port = int(os.environ["EMAIL_SMTP_PORT"])
    user = os.environ["EMAIL_USER"]
    pwd = os.environ["EMAIL_PASS"]
    to = os.environ["EMAIL_TO"]

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
    s.sendmail(user, to, msg.as_string())
    s.quit()


def make_html(items: List[Dict]):
    html = [f"<h2>Job Alerts - {time.strftime('%Y-%m-%d')}</h2>", "<ol>"]
    for x in items:
        html.append(f"<li><b>{x['title']}</b> - {x['company']}<br><a href='{x['link']}'>Apply</a> <br><small>{x['source']}</small></li>")
    html.append("</ol>")
    return "\n".join(html)


if __name__ == "__main__":
    all_jobs = scrape_all(KEYWORDS)

    # keyword final filtering
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
    print("Jobs sent:", len(filtered))
