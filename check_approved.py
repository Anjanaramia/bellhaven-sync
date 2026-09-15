import sqlite3
conn = sqlite3.connect("state.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT classification, account_id, evidence, fields_json FROM proposals WHERE status = 'approved'").fetchall()
for r in rows:
    print(dict(r))