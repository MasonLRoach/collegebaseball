from flask import Flask, render_template, jsonify
import sqlite3
 
app = Flask(__name__)
 
DB_PATH = r"C:\Users\mason\baseball\data\collegebaseball.db"
 
 
def get_connection():
    return sqlite3.connect(DB_PATH)
 
 
@app.route("/")
def index():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            t.team_name,
            t.conference_name,
            COUNT(*) as games_played,
            SUM(CASE WHEN s.result LIKE 'W%' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN s.result LIKE 'L%' THEN 1 ELSE 0 END) as losses,
            t.team_slug
        FROM schedules s
        JOIN teams t ON s.team_id = t.team_id
        WHERE s.status = 'final'
        GROUP BY s.team_id
        ORDER BY wins DESC
    ''')
    teams = cursor.fetchall()
    conn.close()
    return render_template("index.html", teams=teams)
 
 
@app.route("/schedule/<team_slug>")
def team_schedule(team_slug):
    conn = get_connection()
    cursor = conn.cursor()

    # Get the team id
    cursor.execute("SELECT team_id, team_name, conference_name FROM teams WHERE team_slug = ?", (team_slug,))
    team_data = cursor.fetchone()
    actual_id = team_data[0]
    # 3. Get games AND the opponent's slug
    cursor.execute('''
        SELECT 
            s.date,             -- [0]
            s.opponent_name,    -- [1]
            s.location,         -- [2]
            s.result,           -- [3]
            s.status,           -- [4]
            s.attendance,       -- [5]
            opp.team_slug       -- [6]
        FROM schedules s
        LEFT JOIN teams opp ON s.opponent_name = opp.team_name
        WHERE s.team_id = ?
        ORDER BY date
    ''', (actual_id,))
    games = cursor.fetchall()

    conn.close()
    return render_template("schedule.html", games=games, team=team_data)
 
 
if __name__ == "__main__":
    app.run(debug=True)