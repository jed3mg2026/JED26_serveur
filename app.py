"""
Serveur Flask — Collecte des évaluations de posters
====================================================
Endpoints :
  POST /api/rate          → soumettre une note
  GET  /api/status        → vérifier si un participant a déjà soumis
  GET  /admin             → tableau de bord admin (protégé par mot de passe)
  GET  /admin/export      → télécharger le CSV des résultats

Déploiement : Railway.app (gratuit, ~5 min)
"""

from flask import Flask, request, jsonify, Response, render_template_string
from flask_cors import CORS
import sqlite3
import csv
import io
import os
import hashlib
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Autorise les appels depuis GitHub Pages

# ── Configuration ──────────────────────────────────────────────
DB_PATH      = os.environ.get("DB_PATH", "ratings.db")
ADMIN_PASS   = os.environ.get("ADMIN_PASSWORD", "conference2024")  # changez ceci !
# ───────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                participant_id  TEXT NOT NULL,
                participant_name TEXT,
                participant_topic TEXT,
                poster_id       TEXT NOT NULL,
                poster_title    TEXT,
                score           INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
                comment         TEXT,
                submitted_at    TEXT NOT NULL,
                UNIQUE(participant_id, poster_id)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                participant_id  TEXT PRIMARY KEY,
                submitted_at    TEXT NOT NULL
            )
        """)
        db.commit()

init_db()

# ── API : soumettre des notes ───────────────────────────────────
@app.route("/api/rate", methods=["POST"])
def submit_ratings():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON invalide"}), 400

    pid   = str(data.get("participantId", "")).strip()
    name  = str(data.get("participantName", ""))
    topic = str(data.get("participantTopic", ""))
    ratings = data.get("ratings", [])

    if not pid or not ratings:
        return jsonify({"error": "Données manquantes"}), 400

    now = datetime.utcnow().isoformat()

    try:
        with get_db() as db:
            for r in ratings:
                poster_id    = str(r.get("posterId", ""))
                poster_title = str(r.get("posterTitle", ""))
                score        = int(r.get("score", 0))
                comment      = str(r.get("comment", ""))

                if not poster_id or score < 1 or score > 5:
                    continue

                db.execute("""
                    INSERT INTO ratings
                        (participant_id, participant_name, participant_topic,
                         poster_id, poster_title, score, comment, submitted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(participant_id, poster_id)
                    DO UPDATE SET score=excluded.score,
                                  comment=excluded.comment,
                                  submitted_at=excluded.submitted_at
                """, (pid, name, topic, poster_id, poster_title, score, comment, now))

            db.execute("""
                INSERT OR REPLACE INTO submissions (participant_id, submitted_at)
                VALUES (?, ?)
            """, (pid, now))

            db.commit()

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True, "message": "Notes enregistrées avec succès"}), 200


# ── API : vérifier si déjà soumis ──────────────────────────────
@app.route("/api/status/<participant_id>", methods=["GET"])
def get_status(participant_id):
    with get_db() as db:
        row = db.execute(
            "SELECT submitted_at FROM submissions WHERE participant_id = ?",
            (participant_id,)
        ).fetchone()
    if row:
        return jsonify({"submitted": True, "at": row["submitted_at"]})
    return jsonify({"submitted": False})


# ── ADMIN : tableau de bord ─────────────────────────────────────
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Admin — Évaluations Posters</title>
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #f5f4f0; --surface: #ffffff; --accent: #1a1a2e;
      --green: #16a34a; --muted: #6b7280; --radius: 12px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--accent); padding: 32px 16px; }
    header { max-width: 900px; margin: 0 auto 32px; display: flex; align-items: center; justify-content: space-between; flex-wrap: gap; }
    h1 { font-family: 'Syne', sans-serif; font-size: 28px; font-weight: 800; }
    .subtitle { color: var(--muted); font-size: 14px; margin-top: 4px; }
    .export-btn {
      display: inline-block; padding: 12px 24px; background: var(--accent);
      color: white; border-radius: var(--radius); font-family: 'Syne', sans-serif;
      font-weight: 700; text-decoration: none; font-size: 14px;
    }
    .stats { max-width: 900px; margin: 0 auto 28px; display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }
    .stat-card { background: var(--surface); border-radius: var(--radius); padding: 20px 24px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
    .stat-num { font-family: 'Syne', sans-serif; font-size: 36px; font-weight: 800; }
    .stat-label { color: var(--muted); font-size: 13px; margin-top: 4px; }
    .section { max-width: 900px; margin: 0 auto 32px; }
    .section-title { font-family: 'Syne', sans-serif; font-size: 16px; font-weight: 700; margin-bottom: 14px; }
    table { width: 100%; border-collapse: collapse; background: var(--surface); border-radius: var(--radius); overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
    th { background: var(--accent); color: white; padding: 12px 16px; text-align: left; font-size: 12px; letter-spacing: .06em; text-transform: uppercase; font-weight: 600; }
    td { padding: 11px 16px; font-size: 14px; border-bottom: 1px solid #f0f0f0; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #fafaf8; }
    .score-badge { display: inline-block; width: 28px; height: 28px; border-radius: 50%; background: var(--accent); color: white; font-family: 'Syne', sans-serif; font-weight: 700; font-size: 13px; text-align: center; line-height: 28px; }
    .score-5 { background: #16a34a; }
    .score-4 { background: #65a30d; }
    .score-3 { background: #d97706; }
    .score-2 { background: #dc2626; }
    .score-1 { background: #7f1d1d; }
    .progress { background: #e5e7eb; border-radius: 100px; height: 8px; margin-top: 4px; }
    .progress-fill { background: var(--green); border-radius: 100px; height: 8px; }
    .empty { color: var(--muted); font-size: 14px; padding: 32px; text-align: center; }
  </style>
</head>
<body>
<header>
  <div>
    <h1>📊 Tableau de bord admin</h1>
    <p class="subtitle">Évaluations en temps réel — actualisez la page pour mettre à jour</p>
  </div>
  <a href="/admin/export?password={{ password }}" class="export-btn">⬇ Exporter CSV</a>
</header>

<div class="stats">
  <div class="stat-card">
    <div class="stat-num">{{ stats.total_submissions }}</div>
    <div class="stat-label">Participants ayant soumis</div>
  </div>
  <div class="stat-card">
    <div class="stat-num">{{ stats.total_ratings }}</div>
    <div class="stat-label">Notes reçues</div>
  </div>
  <div class="stat-card">
    <div class="stat-num">{{ "%.1f"|format(stats.avg_score) if stats.avg_score else "—" }}</div>
    <div class="stat-label">Note moyenne / 5</div>
  </div>
  <div class="stat-card">
    <div class="stat-num">{{ stats.posters_with_ratings }}/{{ stats.total_posters }}</div>
    <div class="stat-label">Posters notés</div>
  </div>
</div>

<div class="section">
  <div class="section-title">Classement des posters</div>
  {% if poster_ranking %}
  <table>
    <thead>
      <tr>
        <th>#</th><th>Poster</th><th>Topic</th><th>Notes reçues</th><th>Moyenne</th>
      </tr>
    </thead>
    <tbody>
    {% for p in poster_ranking %}
      <tr>
        <td><strong>{{ loop.index }}</strong></td>
        <td>{{ p.poster_title or p.poster_id }}</td>
        <td>Topic {{ p.poster_topic or "?" }}</td>
        <td>
          {{ p.count }}
          <div class="progress"><div class="progress-fill" style="width:{{ (p.count / stats.max_ratings * 100)|int }}%"></div></div>
        </td>
        <td><span class="score-badge score-{{ p.avg|round|int }}">{{ "%.1f"|format(p.avg) }}</span></td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">Aucune note reçue pour l'instant.</div>
  {% endif %}
</div>

<div class="section">
  <div class="section-title">Dernières soumissions</div>
  {% if recent %}
  <table>
    <thead><tr><th>Participant</th><th>Topic</th><th>Poster noté</th><th>Note</th><th>Heure</th></tr></thead>
    <tbody>
    {% for r in recent %}
      <tr>
        <td>{{ r.participant_name or r.participant_id }}</td>
        <td>{{ r.participant_topic }}</td>
        <td>{{ r.poster_title or r.poster_id }}</td>
        <td><span class="score-badge score-{{ r.score }}">{{ r.score }}</span></td>
        <td style="color:var(--muted);font-size:12px">{{ r.submitted_at[:16].replace("T"," ") }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}
  <div class="empty">Aucune note reçue pour l'instant.</div>
  {% endif %}
</div>
</body>
</html>
"""

@app.route("/admin", methods=["GET"])
def admin():
    password = request.args.get("password", "")
    if not check_password(password):
        return """
        <html><body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f5f4f0">
        <form style="background:white;padding:40px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,.1);min-width:300px">
          <h2 style="font-size:22px;margin-bottom:20px;font-weight:700">🔒 Admin</h2>
          <input name="password" type="password" placeholder="Mot de passe"
            style="width:100%;padding:12px;border:1px solid #e0e0e0;border-radius:8px;font-size:15px;margin-bottom:12px">
          <button type="submit"
            style="width:100%;padding:12px;background:#1a1a2e;color:white;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer">
            Connexion
          </button>
        </form></body></html>
        """, 401

    with get_db() as db:
        total_submissions = db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        total_ratings     = db.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
        avg_score_row     = db.execute("SELECT AVG(score) FROM ratings").fetchone()[0]
        posters_rated     = db.execute("SELECT COUNT(DISTINCT poster_id) FROM ratings").fetchone()[0]
        max_r             = db.execute("SELECT MAX(cnt) FROM (SELECT COUNT(*) cnt FROM ratings GROUP BY poster_id)").fetchone()[0] or 1

        poster_ranking = db.execute("""
            SELECT poster_id, poster_title,
                   COUNT(*) as count,
                   AVG(score) as avg,
                   NULL as poster_topic
            FROM ratings
            GROUP BY poster_id
            ORDER BY avg DESC
        """).fetchall()

        recent = db.execute("""
            SELECT * FROM ratings ORDER BY submitted_at DESC LIMIT 30
        """).fetchall()

    stats = {
        "total_submissions": total_submissions,
        "total_ratings": total_ratings,
        "avg_score": avg_score_row or 0,
        "posters_with_ratings": posters_rated,
        "total_posters": db.execute("SELECT COUNT(DISTINCT poster_id) FROM ratings").fetchone()[0] or 0,
        "max_ratings": max_r,
    }

    return render_template_string(ADMIN_HTML,
        stats=stats,
        poster_ranking=[dict(r) for r in poster_ranking],
        recent=[dict(r) for r in recent],
        password=password
    )


# ── ADMIN : export CSV ──────────────────────────────────────────
@app.route("/admin/export", methods=["GET"])
def export_csv():
    password = request.args.get("password", "")
    if not check_password(password):
        return jsonify({"error": "Non autorisé"}), 401

    with get_db() as db:
        rows = db.execute("""
            SELECT participant_id, participant_name, participant_topic,
                   poster_id, poster_title, score, comment, submitted_at
            FROM ratings
            ORDER BY participant_id, poster_id
        """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["participant_id","participant_name","participant_topic",
                     "poster_id","poster_title","score","comment","submitted_at"])
    for row in rows:
        writer.writerow(list(row))

    filename = f"ratings_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── Utilitaires ─────────────────────────────────────────────────
def check_password(pwd):
    expected = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
    provided = hashlib.sha256(pwd.encode()).hexdigest()
    return expected == provided

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "conference2024")

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "poster-ratings-api"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
