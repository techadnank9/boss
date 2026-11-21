"""Live check of every sponsor Boss connects to. Prints one line per sponsor.

Run:  python check_sponsors.py

Reads keys from .env exactly like main.py. Never prints a secret.
"""
import datetime
import html
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).parent
for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

env = os.getenv


def timed(fn):
    t = time.time()
    try:
        ok, detail = fn()
    except Exception as exc:  # a failed check is a result, not a crash
        ok, detail = False, f"{type(exc).__name__}: {str(exc)[:200]}"
    return ok, detail, round(time.time() - t, 2)


def check_singlestore():
    if not env("SINGLESTORE_URL"):
        return False, "SINGLESTORE_URL not set"
    import singlestoredb as s2
    conn = s2.connect(env("SINGLESTORE_URL"))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT run_id) FROM events")
    rows, runs = cur.fetchone()
    cur.execute("SELECT actor, COUNT(*) FROM events WHERE step = 'bid_submitted' GROUP BY actor")
    bids = dict(cur.fetchall())
    conn.close()
    return True, f"events table live: {rows} rows across {runs} runs; bids by agent {bids or '{}'}"


def check_amplitude():
    if not env("AMPLITUDE_API_KEY"):
        return False, "AMPLITUDE_API_KEY not set"
    r = httpx.post("https://api2.amplitude.com/2/httpapi", timeout=10, json={
        "api_key": env("AMPLITUDE_API_KEY"),
        "events": [{"event_type": "sponsor_check", "user_id": "boss-demo-user", "insert_id": uuid.uuid4().hex}]})
    return r.status_code == 200, f"HTTP {r.status_code}, events_ingested={r.json().get('events_ingested') if r.status_code == 200 else r.text[:120]}"


def check_sie():
    if not env("SIE_API_KEY"):
        return False, "SIE_API_KEY not set"
    from sie_sdk import SIEClient
    from sie_sdk.types import Item
    model = env("SIE_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    res = SIEClient(api_key=env("SIE_API_KEY")).score(
        model, Item(text="wireless earbuds under $50"),
        [Item(id="0", text="Sony WF-C500 earbuds $48"), Item(id="1", text="Bose QC Ultra headphones $429")])
    scores = {int(e["item_id"]): round(float(e["score"]), 3) for e in res["scores"]}
    return scores[0] > scores[1], f"rerank via {model}: on-budget bid {scores[0]} vs over-budget {scores[1]}"


def check_cognee():
    url, key = env("COGNEE_SERVICE_URL"), env("COGNEE_API_KEY")
    if not (url and key):
        return False, "COGNEE_SERVICE_URL / COGNEE_API_KEY not set"
    r = httpx.get(f"{url.rstrip('/')}/api/v1/datasets/", headers={"X-Api-Key": key}, timeout=15)
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    names = [d.get("name") for d in r.json()]
    on = env("COGNEE_ENABLED", "0") == "1"
    return True, f"Cognee Cloud reachable, datasets {names}; app memory {'ON' if on else 'OFF (COGNEE_ENABLED=0)'}"


def check_firedrill():
    try:
        out = subprocess.run(["npx", "-y", "firedrill-run@latest", "status", "--json"], cwd=ROOT,
                             capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return False, "npx not found"
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return False, (out.stderr or out.stdout)[:200]
    data = data.get("data", data)
    ws = data.get("workspace") or {}
    name = ws.get("name") if isinstance(ws, dict) else ws
    signed_in = bool(data.get("signed_in"))
    return signed_in, f"CLI signed in, workspace {name!r}" if signed_in else "CLI not signed in: run npx firedrill-run init"


SPONSORS = [
    {"name": "SingleStore", "prize": "$1,000 / $750 / $500 gift cards of your choice",
     "role": "The audit trail. Every agent step, bid, verdict, approval and overrule is a row in `events`. "
             "The scoreboard, lessons and /analytics are SQL over that table.",
     "where": "main.py: log(), events(), scoreboard(), lessons(), _analytics_sql()", "env": "SINGLESTORE_URL",
     "check": check_singlestore},
    {"name": "Amplitude", "prize": "$1,000 / $500 cash (with Statsig)",
     "role": "Decision analytics. Boss sends bid_won, bid_rejected, user_rejected and order_approved events.",
     "where": "main.py: track()", "env": "AMPLITUDE_API_KEY", "check": check_amplitude},
    {"name": "Superlinked SIE Serverless", "prize": "$500 cash + $500 credits (x2 categories)",
     "role": "Reranks every real bid against the request and rules before the judge sees it; logged as bids_reranked.",
     "where": "main.py: rerank_bids(), _sie_scores()", "env": "SIE_API_KEY, SIE_RERANK_MODEL", "check": check_sie},
    {"name": "Cognee", "prize": "$500 / $250 cash + credits",
     "role": "Long-term memory. Overrule lessons are remembered; each new request recalls relevant memories "
             "for the agents and the judge, logged as memory_recalled.",
     "where": "main.py: memory_recall(), memory_remember()", "env": "COGNEE_ENABLED, COGNEE_SERVICE_URL, COGNEE_API_KEY",
     "check": check_cognee},
    {"name": "Firedrill", "prize": "$500 / $300 / $200 prepaid Visa + credits",
     "role": "Drills that prove Boss cannot be fooled: price jump, wrong size, out of stock, vague request.",
     "where": "drills.py, Firedrill CLI + MCP (.mcp.json)", "env": "browser sign-in (no key)", "check": check_firedrill},
    {"name": "Airbyte", "prize": "$1,000 / $500 / $250 Visa gift cards",
     "role": "Not connected. The context layer needs an org admin to enable agent access.",
     "where": "-", "env": "-", "check": None},
]


def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    results = []
    for s in SPONSORS:
        if s["check"] is None:
            ok, detail, secs = None, "not integrated", 0
        else:
            ok, detail, secs = timed(s["check"])
        results.append({**s, "ok": ok, "detail": detail, "secs": secs})
        mark = "SKIP" if ok is None else ("OK  " if ok else "FAIL")
        print(f"[{mark}] {s['name']:<28} {detail} ({secs}s)")

    rows = []
    for r in results:
        state = "off" if r["ok"] is None else ("ok" if r["ok"] else "fail")
        label = {"ok": "Connected", "fail": "Failing", "off": "Not used"}[state]
        rows.append(f"""
      <article class="card {state}">
        <header><h2>{html.escape(r['name'])}</h2><span class="pill {state}">{label}</span></header>
        <p class="prize">{html.escape(r['prize'])}</p>
        <p>{html.escape(r['role'])}</p>
        <dl>
          <dt>Code</dt><dd><code>{html.escape(r['where'])}</code></dd>
          <dt>Config</dt><dd><code>{html.escape(r['env'])}</code></dd>
          <dt>Live check</dt><dd>{html.escape(r['detail'])}{f" &middot; {r['secs']}s" if r['secs'] else ''}</dd>
        </dl>
      </article>""")
    connected = sum(1 for r in results if r["ok"])
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Boss: sponsor integrations</title>
<style>
  :root {{ --ink:#16181d; --muted:#5d6472; --line:#e4e6eb; --ok:#1f7a4d; --fail:#b42318; --off:#8a8f98; }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:#f7f7f8 }}
  main {{ max-width:960px; margin:0 auto; padding:48px 20px }}
  h1 {{ font-size:28px; margin:0 0 6px }}
  .sub {{ color:var(--muted); margin:0 0 28px }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(290px,1fr)); gap:14px }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:18px }}
  .card.off {{ opacity:.65 }}
  .card header {{ display:flex; justify-content:space-between; align-items:center; gap:8px }}
  h2 {{ font-size:17px; margin:0 }}
  .pill {{ font-size:12px; font-weight:600; padding:2px 9px; border-radius:999px; color:#fff; white-space:nowrap }}
  .pill.ok {{ background:var(--ok) }} .pill.fail {{ background:var(--fail) }} .pill.off {{ background:var(--off) }}
  .prize {{ font-weight:600; color:var(--muted); margin:6px 0 10px; font-size:13px }}
  dl {{ margin:12px 0 0; display:grid; grid-template-columns:78px 1fr; gap:4px 8px; font-size:13px }}
  dt {{ color:var(--muted) }} dd {{ margin:0; word-break:break-word }}
  code {{ font-size:12px; background:#f1f2f4; padding:1px 5px; border-radius:4px }}
  footer {{ color:var(--muted); font-size:13px; margin-top:28px }}
</style></head>
<body><main>
  <h1>Boss: sponsor integrations</h1>
  <p class="sub">Cash and Visa prize sponsors only. {connected} of {len(results)} connected, checked live on {now}
  by <code>python check_sponsors.py</code>, which regenerates this page.</p>
  <section class="grid">{''.join(rows)}
  </section>
  <footer>Every status above comes from a real call to that service with the app's own config. No keys are shown.</footer>
</main></body></html>
"""
    print(f"\n{connected}/{len(results)} connected")


if __name__ == "__main__":
    main()
