from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import datetime
import time
import json
import re

BASE_URL = "https://stats.ncaa.org/season_divisions/18783/livestream_scoreboards"


def clean_name(name):
    """Strip W-L record from team name e.g. 'Maine (1-1)' -> 'Maine'"""
    if not name:
        return None
    return re.sub(r'\s*\(\d+-\d+\)', '', name).strip()


def scrape_date(date_str, page):
    url = f"{BASE_URL}?game_date={date_str}"
    print("Scraping:", url)
    page.goto(url, timeout=60000)
    page.wait_for_load_state("networkidle")
    soup = BeautifulSoup(page.content(), "html.parser")

    games = []

    for card in soup.select("div.card"):
        try:
            # --- Date + attendance ---
            date_div = card.select_one("div.col-6.p-0")
            attend_div = card.select_one("div.col.p-0.text-right")

            raw_date = date_div.text.strip() if date_div else date_str
            attendance_raw = attend_div.text.strip() if attend_div else None
            attendance = attendance_raw.replace("Attend:", "").strip() if attendance_raw else None

            # Game number for doubleheaders e.g. "02/13/2026 03:30 PM (1)"
            game_num_match = re.search(r'\((\d+)\)', raw_date)
            game_number = int(game_num_match.group(1)) if game_num_match else None

            # Clean date to just MM/DD/YYYY
            game_date_match = re.search(r'\d{2}/\d{2}/\d{4}', raw_date)
            game_date = game_date_match.group(0) if game_date_match else date_str

            # --- Contest ID ---
            contest_rows = card.select("tr[id^='contest_']")
            if not contest_rows:
                continue

            contest_id = contest_rows[0]["id"].replace("contest_", "")

            # --- Game status from td[rowspan='2'][colspan='3'] ---
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

            # --- Parse each team row ---
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


def dedup(games):
    seen = {}
    for game in games:
        cid = game["contest_id"]
        if cid not in seen:
            seen[cid] = game
        else:
            if game["status"] == "final":
                seen[cid] = game
    return list(seen.values())


if __name__ == "__main__":
    start = datetime.date(2026, 2, 13)
    end = datetime.date.today()

    all_games = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        current = start
        while current <= end:
            date_str = current.strftime("%m/%d/%Y")
            games = scrape_date(date_str, page)
            print(f"  Found {len(games)} games")
            all_games.extend(games)

            with open(r"C:\Users\mason\baseball\data\box_scores.json", "w") as f:
                json.dump(all_games, f, indent=2)

            time.sleep(1)
            current += datetime.timedelta(days=1)

        browser.close()

    all_games = dedup(all_games)

    with open(r"C:\Users\mason\baseball\data\box_scores.json", "w") as f:
        json.dump(all_games, f, indent=2)

    print(f"\nDone! Saved {len(all_games)} games to \ data\ box_scores.json")

    finals = sum(1 for g in all_games if g['status'] == 'final')
    postponed = sum(1 for g in all_games if g['status'] == 'postponed')
    cancelled = sum(1 for g in all_games if g['status'] == 'cancelled')
    print(f"  Final: {finals} | Postponed: {postponed} | Cancelled: {cancelled}")