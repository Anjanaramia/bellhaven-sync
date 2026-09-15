"""
Minimal local review app. Run with: python -m src.review_app
Opens on http://127.0.0.1:5000

This is the ONLY place in the codebase that writes to the CRM.
Every write is gated on an explicit approve click.
"""
from flask import Flask, render_template_string, request, redirect
from .state_store import StateStore
from .crm_client import CRMClient

app = Flask(__name__)
store = StateStore()
crm = CRMClient()

TEMPLATE = """
<!doctype html><html><head><title>Bellhaven sync — review queue</title>
<style>
body{font-family:sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}
.card{border:1px solid #ccc;border-radius:8px;padding:1rem;margin-bottom:1rem}
.evidence{color:#555;font-size:.9rem}
.fields{background:#f6f6f6;padding:.5rem;border-radius:4px;font-family:monospace;font-size:.85rem}
button{padding:.4rem .8rem;margin-right:.5rem;cursor:pointer}
.approve{background:#2a7;color:white;border:none;border-radius:4px}
.reject{background:#c44;color:white;border:none;border-radius:4px}
</style></head><body>
<h1>Bellhaven sync — review queue ({{ proposals|length }} pending)</h1>
{% for p in proposals %}
<div class="card">
  <b>{{ p.classification }}</b> — account: {{ p.account_id or "NEW" }}
  <div class="evidence">{{ p.evidence }}</div>
  <div class="fields">{{ p.fields_json }}</div>
  <form method="post" action="/decide" style="margin-top:.5rem">
    <input type="hidden" name="dedupe_key" value="{{ p.dedupe_key }}">
    <button class="approve" name="action" value="approved">Approve</button>
    <button class="reject" name="action" value="rejected">Reject</button>
  </form>
</div>
{% else %}
<p>No pending proposals. Run the pipeline: <code>python -m src.pipeline</code></p>
{% endfor %}
</body></html>
"""


@app.route("/")
def index():
    return render_template_string(TEMPLATE, proposals=store.list_pending())


@app.route("/decide", methods=["POST"])
def decide():
    dedupe_key = request.form["dedupe_key"]
    action = request.form["action"]  # approved | rejected

    if action == "approved":
        _apply_to_crm(dedupe_key)

    store.decide(dedupe_key, action)
    return redirect("/")


def _apply_to_crm(dedupe_key: str):
    """The only function in the codebase that performs a CRM write."""
    import json
    with store._conn() as c:
        c.row_factory = None
        row = c.execute(
            "SELECT account_id, classification, fields_json FROM proposals WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
    if not row:
        return
    account_id, classification, fields_json = row
    fields = json.loads(fields_json)

    if "_chow_split" in fields:
        action = fields["_chow_split"]
        new_acc = crm.create_account(action["new_account_create"]["payload"])
        crm.update_account(account_id, {
            **action["old_account_update"]["payload"],
            "chow_current_account": new_acc["account_id"],
        })
        return

    if classification == "no_account_yet":
        crm.create_account(fields)
        return

    crm.update_account(account_id, fields)


if __name__ == "__main__":
    app.run(debug=True)
