from bs4 import BeautifulSoup
from driver import get_driver, wait_for
import sqlite3
import time
import random
import re
 
DB_PATH = r"C:\Users\mason\baseball\data\collegebaseball.db"
 
 
def get_connection():
    return sqlite3.connect(DB_PATH)
 
 
def init_db(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            contest_id      TEXT,
            team_id         TEXT,
            team_name       TEXT,
            date            TEXT,
            game_number     INTEGER,
            location        TEXT,
            opponent_id     TEXT,
            opponent_name   TEXT,
            status          TEXT,
            result          TEXT,
            attendance      TEXT,
            away_runs       INTEGER,
            away_hits       INTEGER,
            away_errors     INTEGER,
            home_runs       INTEGER,
            home_hits       INTEGER,
            home_errors     INTEGER,
            winner          TEXT,
            PRIMARY KEY (team_id, date, game_number)
        )
    ''')
    conn.commit()
 
 
def get_teams(conn):
    """Pull all D1 teams from the teams table."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT team_id, team_name FROM teams
        WHERE division = 'D1'
        ORDER BY team_name
    ''')
    return [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]
 
 
def save_schedule(conn, team_id, team_name, games):
    cursor = conn.cursor()
    for game in games:
        cursor.execute('''
            INSERT OR REPLACE INTO schedules (
                contest_id, team_id, team_name, date, game_number,
                location, opponent_id, opponent_name, status, result, attendance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            game["contest_id"],
            team_id,
            team_name,
            game["date"],
            game["game_number"],
            game["location"],
            game["opponent_id"],
            game["opponent_name"],
            game["status"],
            game["result"],
            game["attendance"],
        ))
    conn.commit()
 
 
def scrape_team_schedule(team_id, team_name, driver):
    url = f"https://stats.ncaa.org/teams/{team_id}"
    print(f"  Scraping: {url}")
 
    try:
        driver.get(url)
        time.sleep(5)
    except Exception as e:
        print(f"  Failed to load page: {e}")
        time.sleep(60)
        return []
 
    try:
        wait_for(driver, "div.card")
    except Exception:
        print(f"  No cards found (timeout) — skipping {team_name}")
        return []
 
    soup = BeautifulSoup(driver.page_source, "html.parser")
 
    schedule_card = None
    for card in soup.select("div.card"):
        header = card.select_one("div.card-header")
        if header and "Schedule" in header.text:
            schedule_card = card
            break
 
    if not schedule_card:
        print(f"  No schedule card found for {team_name}")
        return []
 
    games = []
    for row in schedule_card.select("tr.underline_rows"):
        try:
            tds = row.select("td")
            if len(tds) < 3:
                continue
 
            raw_date = tds[0].text.strip()
            game_num_match = re.search(r'\((\d+)\)', raw_date)
            game_number = int(game_num_match.group(1)) if game_num_match else None
            date_match = re.search(r'\d{2}/\d{2}/\d{4}', raw_date)
            date = date_match.group(0) if date_match else raw_date
 
            opp_td = tds[1]
            opp_text = opp_td.get_text()
            is_away = "@" in opp_text
 
            opp_link = opp_td.select_one("a")
            opponent_name = opp_link.text.strip() if opp_link else opp_text.strip().replace("@", "").strip()
            opp_href = opp_link["href"] if opp_link else ""
            opponent_id = opp_href.split("/")[-1] if opp_href else None
 
            result_td = tds[2]
            result_link = result_td.select_one("a")
            result_text = result_td.text.strip()
            contest_id = None
 
            if result_link:
                href = result_link.get("href", "")
                contest_id_match = re.search(r'/contests/(\d+)/', href)
                contest_id = contest_id_match.group(1) if contest_id_match else None
                result_text = result_link.text.strip()
 
            if result_text == "Ppd":
                status = "postponed"
                result = None
            elif result_text == "Canceled":
                status = "cancelled"
                result = None
            elif result_text == "":
                status = "scheduled"
                result = None
            else:
                status = "final"
                result = result_text
 
            attend_td = tds[3] if len(tds) > 3 else None
            attendance = attend_td.text.strip() if attend_td else None
            if attendance == "":
                attendance = None
 
            games.append({
                "date": date,
                "game_number": game_number,
                "location": "away" if is_away else "home",
                "opponent_id": opponent_id,
                "opponent_name": opponent_name,
                "contest_id": contest_id,
                "status": status,
                "result": result,
                "attendance": attendance,
            })
 
        except Exception as e:
            print(f"  Error parsing row: {e}")
            continue
 
    return games
 
 
if __name__ == "__main__":
    conn = get_connection()
    init_db(conn)
 
    teams = get_teams(conn)
    print(f"Found {len(teams)} teams in DB — scraping schedules...")
 
    driver = get_driver()
 
    try:
        for i, team in enumerate(teams):
            print(f"[{i+1}/{len(teams)}] {team['name']}")
            games = scrape_team_schedule(team["id"], team["name"], driver)
 
            if games:
                save_schedule(conn, team["id"], team["name"], games)
                print(f"  Saved {len(games)} games")
 
            if (i + 1) % 25 == 0:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM schedules")
                total = cursor.fetchone()[0]
                print(f"  Progress: {len(teams) - (i+1)} teams remaining | {total} total rows in DB")
 
            time.sleep(random.uniform(10, 18))
 
    finally:
        driver.quit()
        conn.close()
 
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT team_id) FROM schedules")
    total_teams = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM schedules")
    total_games = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM schedules WHERE status = 'scheduled'")
    upcoming = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM schedules WHERE status = 'final'")
    finals = cursor.fetchone()[0]
    conn.close()
 
    print(f"\nDone!")
    print(f"  Teams scraped: {total_teams}")
    print(f"  Total schedule rows: {total_games}")
    print(f"  Final: {finals} | Upcoming: {upcoming}")