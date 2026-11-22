"""Final report of an apply run. It contains no password, TOTP key, field value or note content."""

from __future__ import annotations

import html

OUTCOME_LABELS = {
    "applied": ("applied", "ok"),
    "untouched": ("left untouched", "muted"),
    "stale": ("not applied: changed in the vault", "warn"),
    "failed": ("failed", "err"),
    "partial": ("partially applied", "err"),
}

STYLE = """
:root{--bg:#f6f7f9;--fg:#16181d;--muted:#667085;--card:#fff;--line:#e4e7ec;--ok:#067647;--warn:#b54708;
--err:#b42318;--accent:#3e4fe0;--chip:#eef0f4}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111317;--fg:#e9ebef;--muted:#98a2b3;
--card:#1a1d23;--line:#2a2f38;--ok:#47cd89;--warn:#fdb022;--err:#f97066;--accent:#8b9aff;--chip:#252a33}}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
margin:0;padding:32px 16px}
main{max-width:1040px;margin:auto}
h1{margin:0;font-size:24px}h2{margin:36px 0 10px;font-size:17px}
.muted{color:var(--muted)}
.banner{padding:10px 14px;border-radius:10px;margin:14px 0;border:1px solid var(--line);background:var(--card)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:16px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.kpi b{display:block;font-size:24px;font-variant-numeric:tabular-nums}
.kpi.err b{color:var(--err)}.kpi.warn b{color:var(--warn)}.kpi.accent b{color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:8px 0;padding:12px 14px}
details.card summary{cursor:pointer}summary .head{display:inline-flex}
.head{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.tag{font-size:12px;padding:1px 8px;border-radius:99px;background:var(--chip)}
.tag.ok{color:var(--ok)}.tag.warn{color:var(--warn)}.tag.err{color:var(--err)}.tag.muted{color:var(--muted)}
ul.diff{margin:6px 0 8px;padding-left:18px}ul.diff li{color:var(--accent)}
table{border-collapse:collapse;width:100%;margin-top:6px}
td,th{text-align:left;padding:5px 8px;border-top:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}
th{font-weight:500;color:var(--muted);font-size:12px}
.kept{color:var(--ok);font-weight:600}.trashed{color:var(--err);font-weight:600}.untouched{color:var(--muted)}
.after td{background:color-mix(in srgb,var(--ok) 8%,transparent)}
code,pre{font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
pre{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;overflow-x:auto}
"""


def _when(iso: str | None) -> str:
    return iso[:19].replace("T", " ") if iso else "?"


def _group(r: dict, open_: bool) -> str:
    e = html.escape
    label, cls = OUTCOME_LABELS.get(r["outcome"], (r["outcome"], "muted"))
    title = r["after"]["name"] if r.get("after") else (r["domain"] or r["before"][0]["name"])
    rows = []
    for b in r["before"]:
        rows.append(f"<tr><td class='{b['role']}'>{e(b['role'])}</td><td>{e(b['name'])}</td>"
                    f"<td>{e(b['username'])}</td><td>{'<br>'.join(e(u) for u in b['uris'])}</td>"
                    f"<td><code>{e(b['id'])}</code></td></tr>")
    if r.get("after") and r["outcome"] in ("applied", "partial"):
        a = r["after"]
        rows.append(f"<tr class='after'><td class='kept'>result</td><td>{e(a['name'])}</td><td>{e(a['username'])}</td>"
                    f"<td>{'<br>'.join(e(u) for u in a['uris'])}</td><td></td></tr>")
    diff = "".join(f"<li>{e(d)}</li>" for d in r["differences"])
    msg = f"<div class='muted'>{e(r['message'])}</div>" if r["message"] and r["outcome"] != "untouched" else ""
    body = (f"{f'<ul class=diff>{diff}</ul>' if diff else ''}{msg}"
            f"<table><tr><th></th><th>Name</th><th>Username</th><th>URIs</th><th>ID</th></tr>{''.join(rows)}</table>")
    head = (f"<span class='head'><b>{e(title)}</b><span class='tag {cls}'>{e(label)}</span>"
            f"<span class='muted'>{len(r['before'])} item(s)</span></span>")
    if open_:
        return f"<div class='card'>{head}{body}</div>"
    return f"<details class='card'><summary>{head}</summary>{body}</details>"


def render(run: dict) -> str:
    e = html.escape
    c = run["counts"]
    results = run["results"]
    by_you = [r for r in results if r["differences"] and r["outcome"] in ("applied", "untouched", "partial")]
    problems = [r for r in results if r["outcome"] in ("stale", "failed", "partial")]
    as_rule = [r for r in results if not r["differences"] and r["outcome"] == "applied"]
    trashed = [i for r in results for i in r["trashed"]]

    out = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Merge report</title>
<style>{STYLE}</style></head><body><main>
<h1>Merge report</h1>
<div class="muted">Run of {e(_when(run['started']))}, finished {e(_when(run['finished']))}</div>
<div class="banner">No password, TOTP key, custom field value or note content is stored in this report.
{'Encrypted backup: <code>' + e(run['backup']) + '</code>.' if run.get('backup') else 'No backup made for this run.'}
Trashed items stay in the Bitwarden trash for 30 days.</div>
<div class="grid">
<div class="kpi"><span class="muted">Logins before</span><b>{c.get('loginsBefore', '?')}</b></div>
<div class="kpi"><span class="muted">Logins after</span><b>{c.get('loginsAfter', '?')}</b></div>
<div class="kpi accent"><span class="muted">Decided by you</span><b>{len(by_you)}</b></div>
<div class="kpi"><span class="muted">Items edited</span><b>{c.get('edited', 0)}</b></div>
<div class="kpi err"><span class="muted">Items trashed</span><b>{c.get('trashed', 0)}</b></div>
<div class="kpi warn"><span class="muted">Not applied</span><b>{len(problems)}</b></div>
</div>"""]

    out.append(f"<h2>Different from the rule ({len(by_you)})</h2>")
    out.append("<p class='muted'>Groups you created, resolved or changed. Blue lines are your decisions.</p>"
               if by_you else "<p class='muted'>Every change followed the rule.</p>")
    out.extend(_group(r, True) for r in by_you)

    if problems:
        out.append(f"<h2>Not applied or incomplete ({len(problems)})</h2>")
        out.extend(_group(r, True) for r in problems)

    out.append(f"<h2>Applied as suggested by the rule ({len(as_rule)})</h2>")
    out.extend(_group(r, False) for r in as_rule)

    if trashed:
        out.append("<h2>Undo</h2><p class='muted'>Restore trashed items (kept items keep their changes; "
                   "the encrypted backup allows a full rollback):</p><pre>")
        out.append("\n".join(f"bw restore item {e(i)}" for i in trashed))
        out.append("</pre>")
    if run.get("error"):
        out.append(f"<div class='banner'>Run stopped: {e(run['error'])}</div>")
    out.append("</main></body></html>")
    return "\n".join(out)
