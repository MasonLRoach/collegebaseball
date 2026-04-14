from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import datetime
import os
import time
import sqlite3
import random
import re

BASE_URL = "https://stats.ncaa.org/season_divisions/18783/livestream_scoreboards"
DB_PATH = r"C:\Users\mason\baseball\data\box_scores.db"


def clean_name(name):
    if not name:
        return None
    return re.sub(r'\s*\(\d+-\d+\)', '', name).strip()


def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--lang=en-US")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            contest_id   TEXT PRIMARY KEY,
            date         TEXT,
            game_number  INTEGER,
            status       TEXT,
            attendance   TEXT,
            winner       TEXT,
            away_id      TEXT,
            away_name    TEXT,
            away_runs    INTEGER,
            away_hits    INTEGER,
            away_errors  INTEGER,
            home_id      TEXT,
            home_name    TEXT,
            home_runs    INTEGER,
            home_hits    INTEGER,
            home_errors  INTEGER
        )
    ''')
    conn.commit()
    return conn


def save_games(conn, games):
    cursor = conn.cursor()
    for game in games:
        cursor.execute('''
            INSERT OR REPLACE INTO games VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
        ''', (
            game["contest_id"],
            game["date"],
            game["game_number"],
            game["status"],
            game["attendance"],
            game["winner"],
            game["away"]["id"],
            game["away"]["name"],
            game["away"]["runs"],
            game["away"]["hits"],
            game["away"]["errors"],
            game["home"]["id"],
            game["home"]["name"],
            game["home"]["runs"],
            game["home"]["hits"],
            game["home"]["errors"],
        ))
    conn.commit()


def scrape_date(date_str, driver):
    url = f"{BASE_URL}?game_date={date_str}"
    print("Scraping:", url)

    try:
        driver.get(url)

        time.sleep(random.uniform(5,10))
    except Exception as e:
        print(f"  Failed to load page: {e}")
        time.sleep(60)
        return []

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.card"))
        )
    except Exception:
        print("  No cards found (timeout) — skipping")
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")
    games = []

    for card in soup.select("div.card"):
        try:
            date_div = card.select_one("div.col-6.p-0")
            attend_div = card.select_one("div.col.p-0.text-right")

            raw_date = date_div.text.strip() if date_div else date_str
            attendance_raw = attend_div.text.strip() if attend_div else None
            attendance = attendance_raw.replace("Attend:", "").strip() if attendance_raw else None

            game_num_match = re.search(r'\((\d+)\)', raw_date)
            game_number = int(game_num_match.group(1)) if game_num_match else None

            game_date_match = re.search(r'\d{2}/\d{2}/\d{4}', raw_date)
            game_date = game_date_match.group(0) if game_date_match else date_str

            contest_rows = card.select("tr[id^='contest_']")
            if not contest_rows:
                continue

            contest_id = contest_rows[0]["id"].replace("contest_", "")

            status_td = card.select_one("td[rowspan='2'][colspan='3']")
            if status_td:
                status_text = status_td.text.strip()
                if status_text == "Ppd":
                    status = "postponed"
                elif status_text == "Canceled":
                    status = "cancelled"
                else:
                    status = "unknown"
            else:
                status = "final"

            def parse_team(tr, is_final):
                team_td = tr.select_one("td.opponents_min_width, td.winner_background")
                team_link = team_td.select_one("a") if team_td else None
                raw_name = team_link.text.strip() if team_link else None
                name = clean_name(raw_name)
                href = team_link["href"] if team_link else ""
                team_id = href.split("/")[-1] if href else None

                if is_final:
                    r_td = tr.select_one("td.totalcolborder-bottom, td.totalcol")
                    h_td = tr.select_one("td.hitscol")
                    e_td = tr.select_one("td.errorscol")
                    runs = r_td.text.strip() if r_td else None
                    hits = h_td.text.strip() if h_td else None
                    errors = e_td.text.strip() if e_td else None
                else:
                    runs = hits = errors = None

                return {
                    "id": team_id,
                    "name": name,
                    "runs": runs,
                    "hits": hits,
                    "errors": errors,
                }

            if len(contest_rows) < 2:
                continue

            is_final = status == "final"
            away = parse_team(contest_rows[0], is_final)
            home = parse_team(contest_rows[1], is_final)

            if is_final and away["runs"] is not None and home["runs"] is not None:
                ar, hr = int(away["runs"]), int(home["runs"])
                winner = "away" if ar > hr else ("home" if hr > ar else "tie")
            else:
                winner = None

            games.append({
                "contest_id": contest_id,
                "date": game_date,
                "game_number": game_number,
                "status": status,
                "attendance": attendance if is_final else None,
                "winner": winner,
                "away": away,
                "home": home,
            })

        except Exception as e:
            print(f"  Error parsing card: {e}")
            continue

    return games


if __name__ == "__main__":
    start = datetime.date(2026, 4, 13)
    end = datetime.date.today()

    # Make sure the output directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = init_db()

    # Print how many games are already in the DB
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM games")
    existing_count = cursor.fetchone()[0]
    print(f"Existing games in DB: {existing_count}")

    driver = get_driver()

    try:
        current = start
        while current <= end:
            date_str = current.strftime("%m/%d/%Y")
            games = scrape_date(date_str, driver)
            print(f"  Found {len(games)} games")

            if games:
                save_games(conn, games)

            current += datetime.timedelta(days=1)

    finally:
        driver.quit()
        conn.close()

    # Print final stats
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM games")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM games WHERE status = 'final'")
    finals = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM games WHERE status = 'postponed'")
    postponed = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM games WHERE status = 'cancelled'")
    cancelled = cursor.fetchone()[0]
    conn.close()

    print(f"\nDone! Total games in DB: {total}")
    print(f"  Final: {finals} | Postponed: {postponed} | Cancelled: {cancelled}")