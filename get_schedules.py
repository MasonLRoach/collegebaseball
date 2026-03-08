from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import time
import re

def scrape_team_schedule(team_id, team_name, page):
    url = f"https://stats.ncaa.org/teams/{team_id}"
    try:
        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle")
        soup = BeautifulSoup(page.content(), "html.parser")

        # --- Overall records ---
        records = {}
        for card in soup.select("div.justify-content-center"):
            label_div = card.select_one("div:first-child")
            value_div = card.select_one("div:last-child")
            if label_div and value_div:
                label = label_div.text.strip()
                value = value_div.text.strip()
                if label:
                    records[label] = value

        # --- Find schedule card only ---
        schedule_card = None
        for card in soup.select("div.card"):
            header = card.select_one("div.card-header")
            if header and "Schedule" in header.text:
                schedule_card = card
                break

        if not schedule_card:
            print(f"  No schedule card found for {team_name}")
            return None

        # --- Schedule rows ---
        games = []
        for row in schedule_card.select("tr.underline_rows"):
            try:
                tds = row.select("td")
                if len(tds) < 3:
                    continue

                # Date
                raw_date = tds[0].text.strip()
                game_num_match = re.search(r'\((\d+)\)', raw_date)
                game_number = int(game_num_match.group(1)) if game_num_match else None
                date_match = re.search(r'\d{2}/\d{2}/\d{4}', raw_date)
                date = date_match.group(0) if date_match else raw_date

                # Opponent — check for @ sign for away game
                opp_td = tds[1]
                opp_text = opp_td.get_text()
                is_away = "@" in opp_text

                opp_link = opp_td.select_one("a")
                opponent_name = opp_link.text.strip() if opp_link else opp_text.strip().replace("@", "").strip()
                opp_href = opp_link["href"] if opp_link else ""
                opponent_id = opp_href.split("/")[-1] if opp_href else None

                # Result / status
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

                # Attendance
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

        return {
            "team_id": team_id,
            "team_name": team_name,
            "records": records,
            "schedule": games,
        }

    except Exception as e:
        print(f"  Error scraping {team_name}: {e}")
        return None


if __name__ == "__main__":
    with open(r"C:\Users\mason\baseball\teams.json") as f:
        teams = json.load(f)

    print(f"Scraping schedules for {len(teams)} teams...")

    all_schedules = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        for i, team in enumerate(teams):
            print(f"[{i+1}/{len(teams)}] {team['name']}")
            result = scrape_team_schedule(team["id"], team["name"], page)
            if result:
                all_schedules.append(result)

            # Save progress every 25 teams
            if (i + 1) % 25 == 0:
                with open(r"C:\Users\mason\baseball\schedules.json", "w") as f:
                    json.dump(all_schedules, f, indent=2)
                print(f"  Progress saved ({len(all_schedules)} teams)")

            time.sleep(0.5)

        browser.close()

    with open(r"C:\Users\mason\baseball\schedules.json", "w") as f:
        json.dump(all_schedules, f, indent=2)

    print(f"\nDone! Saved {len(all_schedules)} team schedules to schedules.json")