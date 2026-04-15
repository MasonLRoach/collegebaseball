from bs4 import BeautifulSoup
from driver import get_driver, wait_for
import datetime
import os
import time
import sqlite3
import random
import re
 
BASE_URL = "https://stats.ncaa.org/season_divisions/18783/livestream_scoreboards"
DB_PATH = r"C:\Users\mason\baseball\data\collegebaseball.db"
LOG_PATH = r"C:\Users\mason\baseball\data\last_updated.txt"
 
 
def clean_name(name):
    if not name:
        return None
    return re.sub(r'\s*\(\d+-\d+\)', '', name).strip()
 
 
def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)
 
 
def get_start_date():
    if os.path.exists(LOG_PATH):
        last = open(LOG_PATH).read().strip()
        return datetime.datetime.strptime(last, "%m/%d/%Y").date() + datetime.timedelta(days=1)
    return datetime.date(2026, 2, 13)
 
 
def update_game(conn, game):
    cursor = conn.cursor()
    away = game["away"]
    home = game["home"]
 
    if away["runs"] is not None and home["runs"] is not None:
        ar, hr = int(away["runs"]), int(home["runs"])
        winner = "away" if ar > hr else ("home" if hr > ar else "tie")
        away_result = f"{'W' if ar > hr else ('L' if hr > ar else 'T')} {ar}-{hr}"
        home_result = f"{'W' if hr > ar else ('L' if ar > hr else 'T')} {hr}-{ar}"
    else:
        winner = None
        away_result = None
        home_result = None
 
    def do_update(team_id, result):
        # First try matching by contest_id
        cursor.execute('''
            UPDATE schedules SET
                status = ?, result = ?, attendance = ?,
                away_runs = ?, away_hits = ?, away_errors = ?,
                home_runs = ?, home_hits = ?, home_errors = ?,
                winner = ?
            WHERE contest_id = ? AND team_id = ?
        ''', (
            game["status"], result, game["attendance"],
            away["runs"], away["hits"], away["errors"],
            home["runs"], home["hits"], home["errors"],
            winner, game["contest_id"], team_id,
        ))
 
        # If no rows updated, fall back to matching by team_id + date + game_number
        if cursor.rowcount == 0:
            cursor.execute('''
                UPDATE schedules SET
                    contest_id = ?,
                    status = ?, result = ?, attendance = ?,
                    away_runs = ?, away_hits = ?, away_errors = ?,
                    home_runs = ?, home_hits = ?, home_errors = ?,
                    winner = ?
                WHERE team_id = ? AND date = ?
                AND (game_number = ? OR game_number IS NULL)
                AND status != 'final'
            ''', (
                game["contest_id"],
                game["status"], result, game["attendance"],
                away["runs"], away["hits"], away["errors"],
                home["runs"], home["hits"], home["errors"],
                winner, team_id, game["date"], game["game_number"],
            ))
 
    do_update(away["id"], away_result)
    do_update(home["id"], home_result)
 
    conn.commit()
 
 
def scrape_date(date_str, driver):
    url = f"{BASE_URL}?game_date={date_str}"
    print("Scraping:", url)
 
    try:
        driver.get(url)
        time.sleep(random.uniform(10, 18))
    except Exception as e:
        print(f"  Failed to load page: {e}")
        time.sleep(60)
        return []
 
    try:
        wait_for(driver, "div.card")
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
 
            games.append({
                "contest_id": contest_id,
                "date": game_date,
                "game_number": game_number,
                "status": status,
                "attendance": attendance if is_final else None,
                "away": away,
                "home": home,
            })
 
        except Exception as e:
            print(f"  Error parsing card: {e}")
            continue
 
    return games
 
 
if __name__ == "__main__":
    start = datetime.date(2026, 4, 14)
    end = datetime.date.today()
 
    print(f"Scraping from {start.strftime('%m/%d/%Y')} to {end.strftime('%m/%d/%Y')}")
 
    conn = get_connection()
    driver = get_driver()
 
    try:
        current = start
        while current <= end:
            date_str = current.strftime("%m/%d/%Y")
            games = scrape_date(date_str, driver)
            print(f"  Found {len(games)} games")
 
            for game in games:
                update_game(conn, game)
 
            open(LOG_PATH, "w").write(date_str)
            current += datetime.timedelta(days=1)
 
    finally:
        driver.quit()
        conn.close()
 
    # Final stats
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM schedules WHERE status = 'final'")
    finals = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM schedules WHERE status = 'postponed'")
    postponed = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM schedules WHERE status = 'scheduled'")
    upcoming = cursor.fetchone()[0]
    conn.close()
 
    print(f"\nDone!")
    print(f"  Final: {finals} | Postponed: {postponed} | Upcoming: {upcoming}")