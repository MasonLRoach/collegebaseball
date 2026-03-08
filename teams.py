import json

with open(r"C:\Users\mason\baseball\data\box_scores.json") as f:
    data = json.load(f)

teams = {}
for game in data:
    for side in ["away", "home"]:
        team_id = game[side]["id"]
        team_name = game[side]["name"]
        if team_id and team_name and team_id not in teams:
            teams[team_id] = team_name

teams_list = [{"id": tid, "name": name} for tid, name in sorted(teams.items(), key=lambda x: x[1])]

with open(r"C:\Users\mason\baseball\teams.json", "w") as f:
    json.dump(teams_list, f, indent=2)

print(f"Saved {len(teams_list)} teams to teams.json")