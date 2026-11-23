// UI of the duplicate merger. Every vault value is rendered with textContent, never as HTML.

const MATCH = [
  [null, "Default"], [0, "Base domain"], [1, "Host"], [2, "Starts with"], [3, "Exact"], [4, "Regular expression"], [5, "Never"],
];
const KIND_LABEL = { rule: "rule", conflict: "conflict", skipped: "skipped by the rule", manual: "your group", rename: "rename" };
const STATUS_LABEL = { todo: "to review", validated: "validated", stale: "changed in vault", failed: "failed", applied: "applied" };
const OPEN = new Set(["todo", "validated", "stale", "failed"]);
const FILTERS = [
  ["review", "To review", (g) => ["todo", "stale", "failed"].includes(g.status)],
  ["undecided", "Undecided", (g) => OPEN.has(g.status) && g.suggestion.action === null && g.decision.action === null],
  ["validated", "Validated", (g) => g.status === "validated"],
  ["applied", "Applied", (g) => g.status === "applied"],
  ["all", "All", () => true],
];

const ui = {
  token: "", state: null, view: "review", filter: "review", query: "", selected: null,
  drafts: {}, saveTimers: {}, revealed: {}, loginQuery: "", loginScope: "free", picked: new Set(), polling: null,
};

// Helpers

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected") el[k] = Boolean(v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "X-Token": ui.token, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const type = res.headers.get("Content-Type") || "";
  const data = type.startsWith("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || res.statusText);
  return data;
}

function toast(message) {
  document.querySelector(".toast")?.remove();
  const el = h("div", { class: "toast" }, message);
  document.body.append(el);
  setTimeout(() => el.remove(), 3500);
}

const clone = (v) => JSON.parse(JSON.stringify(v));
const item = (id) => ui.state.items[id] || { id, name: "(not in vault)", username: "", uris: [], missing: true, fields: [] };
const groupById = (id) => ui.state.groups.find((g) => g.id === id);
const decisionOf = (g) => ui.drafts[g.id] || g.decision;
const date = (iso) => (iso ? iso.slice(0, 16).replace("T", " ") : "");

function labelChip(letter) {
  if (!letter) return h("span", { class: "small" }, "none");
  const idx = letter.charCodeAt(0) - 65;
  return h("span", { class: `lbl c${idx % 5}` }, letter);
}

// Data loading

async function load() {
  try {
    ui.state = await api("/api/state");
  } catch (err) {
    renderFatal(err.message);
    return;
  }
  const running = ui.state.progress && ui.state.progress.running;
  const locked = !ui.state.unlocked;
  if ((running || locked) && !ui.polling) ui.polling = setInterval(load, 1200);
  if (!running && !locked && ui.polling) { clearInterval(ui.polling); ui.polling = null; }
  render();
}

function groupsFiltered() {
  const test = FILTERS.find((f) => f[0] === ui.filter)[2];
  const q = ui.query.trim().toLowerCase();
  const order = { stale: 0, failed: 1, todo: 2, validated: 3, applied: 4 };
  return ui.state.groups
    .filter(test)
    .filter((g) => !q || [g.domain, g.decision.name, ...g.items.flatMap((i) => [item(i).name, item(i).username])]
      .some((v) => (v || "").toLowerCase().includes(q)))
    .sort((a, b) => order[a.status] - order[b.status]
      || (a.suggestion.action === null ? 0 : 1) - (b.suggestion.action === null ? 0 : 1)
      || (a.domain || "").localeCompare(b.domain || ""));
}

// Rendering

function renderFatal(message) {
  const app = document.getElementById("app");
  app.replaceChildren(h("div", { class: "splash" }, h("h1", {}, "Connection lost"),
    h("p", {}, message), h("p", {}, "Restart the tool, then use the link it prints.")));
}

function render() {
  const app = document.getElementById("app");
  const s = ui.state;
  if (!s.unlocked) {
    app.replaceChildren(renderLocked());
    return;
  }
  const scroll = document.querySelector(".detail, .page")?.scrollTop || 0;
  const listScroll = document.querySelector(".rows")?.scrollTop || 0;
  const body = ui.view === "review" ? renderReview() : ui.view === "logins" ? renderLogins() : renderHistory();
  app.replaceChildren(renderTop(), body);
  if (s.progress && (s.progress.running || s.progress.phase === "finished")) app.append(renderProgress());
  const d = document.querySelector(".detail, .page");
  if (d) d.scrollTop = scroll;
  const r = document.querySelector(".rows");
  if (r) r.scrollTop = listScroll;
}

function renderLocked() {
  const s = ui.state;
  return h("div", { class: "splash" },
    h("h1", {}, "Vault locked"),
    h("p", {}, "A terminal window runs the Bitwarden CLI, which asks for your master password. "
      + "This tool only receives the session key, kept in memory."),
    s.unlockPending ? h("p", {}, "Waiting for the terminal window…") : null,
    s.unlockError ? h("p", { class: "note err" }, s.unlockError) : null,
    h("button", {
      class: "btn primary", onclick: async () => {
        try { await api("/api/unlock", {}); } catch (err) { toast(err.message); }
        load();
      },
    }, s.unlockPending ? "Open the terminal again" : "Unlock in a terminal window"));
}

function renderTop() {
  const s = ui.state;
  const open = s.groups.filter((g) => g.status !== "applied");
  const validated = s.groups.filter((g) => g.status === "validated");
  const applied = s.groups.filter((g) => g.status === "applied").length;
  const total = s.groups.length || 1;
  const tab = (id, label) => h("button", { class: ui.view === id ? "on" : "", onclick: () => { ui.view = id; render(); } }, label);
  return h("header", { class: "top" },
    h("span", { class: "brand" }, "Duplicate merger"),
    s.demo && h("span", { class: "tag demo", title: "Changes stay in memory and are lost when you quit" }, "Demo vault, made-up data"),
    h("nav", { class: "tabs" }, tab("review", `Review (${open.length})`), tab("logins", `All logins (${Object.keys(s.items).length})`),
      tab("history", `History (${s.runs.length})`)),
    h("div", { class: "progress", title: "applied / validated / total groups" },
      h("div", { class: "bar" }, h("i", { class: "a", style: `width:${(applied / total) * 100}%` }),
        h("i", { class: "v", style: `width:${(validated.length / total) * 100}%` })),
      `${applied} applied · ${validated.length} validated · ${s.groups.length}`),
    h("span", { class: "spacer" }),
    h("button", { class: "btn", title: "Sync with Bitwarden and look for changes", onclick: refresh }, "Sync"),
    h("button", { class: "btn primary", disabled: !validated.length, onclick: openApplyDialog }, `Apply validated (${validated.length})`),
    h("button", { class: "btn ghost", onclick: quit }, "Quit"));
}

function renderReview() {
  const groups = groupsFiltered();
  if (!groups.some((g) => g.id === ui.selected)) ui.selected = groups[0]?.id || null;
  const counts = Object.fromEntries(FILTERS.map(([id, , test]) => [id, ui.state.groups.filter(test).length]));
  const list = h("aside", { class: "list" },
    h("div", { class: "filters" },
      h("input", {
        class: "search", type: "search", placeholder: "Search domain, name, username", value: ui.query, id: "q",
        oninput: (e) => { ui.query = e.target.value; rerenderList(); },
      }),
      h("div", { class: "chips" }, FILTERS.map(([id, label]) => h("button", {
        class: `chip ${ui.filter === id ? "on" : ""}`, onclick: () => { ui.filter = id; render(); },
      }, `${label} ${counts[id]}`)))),
    h("div", { class: "rows" }, renderRows(groups)));
  const g = ui.selected && groupById(ui.selected);
  return h("div", { class: "main" }, list, h("section", { class: "detail" }, g ? renderGroup(g) : h("div", { class: "empty" },
    ui.state.groups.length ? "Nothing in this filter." : "No duplicates found. Use All logins to group items by hand.")));
}

function renderRows(groups) {
  if (!groups.length) return h("div", { class: "empty" }, "No group.");
  return groups.map((g) => {
    const d = decisionOf(g);
    const users = [...new Set(g.items.map((i) => item(i).username).filter(Boolean))];
    return h("div", {
      class: `row ${g.id === ui.selected ? "sel" : ""}`, onclick: () => { ui.selected = g.id; render(); },
    },
    h("span", { class: `dot ${g.status}`, title: STATUS_LABEL[g.status] }),
    h("span", { class: "t" }, d.name || g.domain),
    h("span", { class: `tag ${g.kind}` }, g.items.length > 1 ? `${KIND_LABEL[g.kind]} · ${g.items.length}` : KIND_LABEL[g.kind]),
    h("span", { class: "s" }, [users.join(", ") || "(no username)", g.reason ? ` · ${g.reason}` : "",
      d.action === "ignore" ? " · leave untouched" : ""].join("")));
  });
}

function rerenderList() {
  const rows = document.querySelector(".rows");
  if (rows) rows.replaceChildren(...[renderRows(groupsFiltered())].flat());
}

// Group detail

function editable(g) { return OPEN.has(g.status) && !ui.state.progress?.running; }

function renderGroup(g) {
  const d = decisionOf(g);
  const canEdit = editable(g);
  const head = h("div", { class: "head" },
    h("h2", {}, g.domain || d.name),
    h("span", { class: `tag ${g.kind}` }, KIND_LABEL[g.kind]),
    h("span", { class: `tag ${g.status}` }, STATUS_LABEL[g.status]),
    g.reason ? h("span", { class: "small" }, g.reason) : null);
  const notes = [];
  if (g.note) notes.push(h("div", { class: g.status === "failed" ? "note err" : "note" }, g.note));
  if (g.status === "applied") {
    notes.push(h("div", { class: "note info" }, "Applied. ",
      g.runId ? h("a", { class: "link", onclick: () => openReport(g.runId) }, "Open the report of this run") : null));
    return h("div", {}, head, notes);
  }
  if (g.suggestion.action === null && g.decision.action === null && g.kind !== "manual") {
    notes.push(h("div", { class: "note" }, "The rule cannot decide this group: compare the items, "
      + "pick what the result should keep, then merge or leave untouched."));
  }

  const actionSeg = h("div", { class: "seg" },
    h("button", { class: d.action === "merge" ? "on" : "", disabled: !canEdit, onclick: () => edit(g, (x) => { x.action = "merge"; }) },
      g.items.length > 1 ? "Merge" : "Update"),
    h("button", { class: d.action === "ignore" ? "on" : "", disabled: !canEdit, onclick: () => edit(g, (x) => { x.action = "ignore"; }) },
      "Leave untouched"));

  const parts = [head, ...notes, h("div", {}, actionSeg), renderItems(g, d, canEdit)];
  if (d.action === "merge") parts.push(renderResult(g, d, canEdit), renderImpact(g, d));
  if (d.action === "ignore") parts.push(h("div", { class: "card" }, h("div", { class: "pad small" },
    "No item of this group will be changed. Once applied, these items are no longer suggested by the rule.")));
  parts.push(renderActions(g, d, canEdit));
  return h("div", {}, parts);
}

function secretCell(g, id, kind, letter) {
  const key = `${id}:${kind}`;
  const shown = ui.revealed[key];
  if (!letter) return h("span", { class: "small" }, "none");
  return h("span", { class: "secret" }, labelChip(letter),
    shown !== undefined ? h("span", { class: "revealed" }, shown) : null,
    h("button", {
      class: "btn icon", title: shown !== undefined ? "Hide" : "Reveal",
      onclick: async () => {
        if (shown !== undefined) { delete ui.revealed[key]; render(); return; }
        try {
          ui.revealed[key] = (await api(`/api/secret?item=${encodeURIComponent(id)}&kind=${kind}`)).value;
          render();
        } catch (err) { toast(err.message); }
      },
    }, shown !== undefined ? "hide" : "show"));
}

function renderItems(g, d, canEdit) {
  const rows = g.items.map((id) => {
    const it = item(id);
    const inMerge = d.action === "merge" && d.include.includes(id);
    const role = d.action !== "merge" ? "untouched" : !inMerge ? "untouched" : id === d.keep ? "kept" : "trash";
    const roleText = { kept: "kept", trash: "to trash", untouched: "untouched" }[role];
    const badges = [
      it.folder ? h("span", { class: "tag" }, `folder: ${it.folder}`) : null,
      it.favorite ? h("span", { class: "tag" }, "favorite") : null,
      it.reprompt ? h("span", { class: "tag" }, "re-prompt") : null,
      it.attachments ? h("span", { class: `tag ${role === "trash" ? "failed" : ""}` }, `${it.attachments} attachment(s)`) : null,
      it.passkeys ? h("span", { class: "tag skipped" }, "passkey") : null,
      ...(it.fields || []).map((f) => h("span", { class: "tag" }, `field: ${f}`)),
    ];
    return h("tr", { class: inMerge || d.action !== "merge" ? "" : "out" },
      h("td", { class: "ctl" }, h("input", {
        type: "radio", name: `keep-${g.id}`, title: "Keep this item", checked: d.keep === id,
        disabled: !canEdit || d.action !== "merge" || it.missing,
        onchange: () => edit(g, (x) => { x.keep = id; if (!x.include.includes(id)) x.include.push(id); }),
      })),
      h("td", { class: "ctl" }, h("input", {
        type: "checkbox", title: "Part of the merge (unchecked: left untouched)", checked: inMerge,
        disabled: !canEdit || d.action !== "merge" || id === d.keep || it.missing,
        onchange: (e) => edit(g, (x) => setIncluded(g, x, id, e.target.checked)),
      })),
      h("td", {}, h("div", { class: `role ${role}` }, roleText), h("div", {}, it.name), h("div", { class: "small" }, `modified ${date(it.revision)}`)),
      h("td", {}, it.username || h("span", { class: "small" }, "(none)")),
      h("td", { class: "uris" }, it.uris.length ? it.uris.map((u) => h("div", {}, u.uri)) : h("span", { class: "small" }, "(none)")),
      h("td", {}, secretCell(g, id, "password", g.passwordLabels[id])),
      h("td", {}, secretCell(g, id, "totp", g.totpLabels[id])),
      h("td", {}, it.notesLength ? secretCell(g, id, "notes", g.notesLabels[id]) : h("span", { class: "small" }, "none")),
      h("td", {}, h("div", { class: "badges" }, badges)),
      h("td", { class: "ctl" }, canEdit ? h("button", {
        class: "btn icon", title: "Take out of this group (never grouped automatically again)",
        onclick: () => removeItem(g, id),
      }, "✕") : null));
  });
  return h("div", { class: "card" },
    h("h3", {}, "Items", h("span", { class: "small" }, "Same letter = same secret. Letters never reveal the value.")),
    h("div", { class: "items-wrap" }, h("table", {},
      h("tr", {}, h("th", {}, "Keep"), h("th", {}, "Merge"), h("th", {}, "Item"), h("th", {}, "Username"), h("th", {}, "URIs"),
        h("th", {}, "Password"), h("th", {}, "TOTP"), h("th", {}, "Notes"), h("th", {}, "Other"), h("th", {}, "")),
      rows)));
}

function setIncluded(g, x, id, on) {
  x.include = on ? [...new Set([...x.include, id])] : x.include.filter((i) => i !== id);
  for (const key of ["usernameFrom", "passwordFrom"]) if (!x.include.includes(x[key])) x[key] = x.keep;
  if (x.totpFrom && !x.include.includes(x.totpFrom)) x.totpFrom = null;
  x.notesFrom = x.notesFrom.filter((i) => x.include.includes(i));
  if (on && item(id).notesLength && !x.notesFrom.includes(id)) x.notesFrom.push(id);
}

function ruleUris(g, include) {
  const items = include.map(item);
  const schemes = new Set(items.flatMap((i) => i.uris.filter((u) => u.domain).map((u) => u.scheme)));
  const scheme = schemes.size === 1 && schemes.has("http") ? "http" : "https";
  const others = [...new Set(items.flatMap((i) => i.uris.map((u) => u.domain)).filter((d) => d && d !== g.domain))].sort();
  const uris = [g.domain, ...others].filter(Boolean).map((d) => ({ uri: `${scheme}://${d}`, match: 0 }));
  const seen = new Set();
  for (const i of items) for (const u of i.uris) {
    if (!u.domain && !seen.has(u.uri)) { seen.add(u.uri); uris.push({ uri: u.uri, match: u.match }); }
  }
  return uris;
}

function sourceSelect(g, d, key, kind, canEdit, allowNone) {
  const options = d.include.filter((id) => kind !== "totp" || g.totpLabels[id]);
  const labels = kind === "password" ? g.passwordLabels : kind === "totp" ? g.totpLabels : null;
  return h("select", {
    class: "select", disabled: !canEdit,
    onchange: (e) => edit(g, (x) => { x[key] = e.target.value || null; }),
  },
  allowNone ? h("option", { value: "", selected: !d[key] }, "none") : null,
  options.map((id) => {
    const it = item(id);
    const what = kind === "username" ? (it.username || "(empty)") : `${kind} ${labels[id] || "(empty)"}`;
    return h("option", { value: id, selected: d[key] === id }, `${what}, from "${it.name}"`);
  }));
}

function renderResult(g, d, canEdit) {
  const nameSugg = [...new Set([g.domain, ...g.items.map((i) => item(i).name)].filter(Boolean))].filter((n) => n !== d.name);
  const uriRows = d.uris.map((u, idx) => h("div", { class: "uri-row" },
    h("input", {
      class: "input", value: u.uri, disabled: !canEdit,
      onchange: (e) => edit(g, (x) => { x.uris[idx].uri = e.target.value.trim(); }),
    }),
    h("select", {
      class: "select", disabled: !canEdit,
      onchange: (e) => edit(g, (x) => { x.uris[idx].match = e.target.value === "" ? null : Number(e.target.value); }),
    }, MATCH.map(([v, label]) => h("option", { value: v === null ? "" : v, selected: (u.match ?? null) === v }, label))),
    h("button", { class: "btn icon", disabled: !canEdit, title: "Remove", onclick: () => edit(g, (x) => { x.uris.splice(idx, 1); }) }, "✕")));
  const withNotes = d.include.filter((id) => item(id).notesLength);
  return h("div", { class: "card" }, h("h3", {}, "Result"), h("div", { class: "pad form" },
    h("label", {}, "Name"),
    h("div", {}, h("input", {
      class: "input", value: d.name, disabled: !canEdit,
      onchange: (e) => edit(g, (x) => { x.name = e.target.value; }),
    }), canEdit && nameSugg.length ? h("div", { class: "sugg" }, nameSugg.slice(0, 6).map((n) => h("button", {
      class: "chip", onclick: () => edit(g, (x) => { x.name = n; }),
    }, n))) : null),
    h("label", {}, "Username"), h("div", {}, sourceSelect(g, d, "usernameFrom", "username", canEdit, false)),
    h("label", {}, "Password"), h("div", {}, sourceSelect(g, d, "passwordFrom", "password", canEdit, false)),
    h("label", {}, "TOTP key"), h("div", {}, sourceSelect(g, d, "totpFrom", "totp", canEdit, true)),
    h("label", {}, "Notes"), h("div", { class: "checks" }, withNotes.length ? withNotes.map((id) => h("label", {},
      h("input", {
        type: "checkbox", checked: d.notesFrom.includes(id), disabled: !canEdit,
        onchange: (e) => edit(g, (x) => {
          x.notesFrom = e.target.checked ? [...x.notesFrom, id] : x.notesFrom.filter((i) => i !== id);
        }),
      }), ` notes ${g.notesLabels[id]} from "${item(id).name}" (${item(id).notesLength} characters)`)) : h("span", { class: "small" }, "none")),
    h("label", {}, "URIs"),
    h("div", {}, uriRows, canEdit ? h("div", { class: "sugg" },
      h("button", { class: "btn small", onclick: () => edit(g, (x) => { x.uris.push({ uri: "", match: null }); }) }, "Add URI"),
      h("button", { class: "btn small", onclick: () => edit(g, (x) => { x.uris = ruleUris(g, x.include); }) }, "Use the rule (base domain)"),
      h("button", {
        class: "btn small",
        onclick: () => edit(g, (x) => {
          const seen = new Set();
          x.uris = x.include.flatMap((id) => item(id).uris).filter((u) => !seen.has(u.uri) && seen.add(u.uri))
            .map((u) => ({ uri: u.uri, match: u.match }));
        }),
      }, "Keep all original URIs")) : null),
    h("label", {}, "Also merged"),
    h("div", { class: "small", style: "padding-top:6px" },
      "Custom fields of all merged items, favorite, folder, master password re-prompt.")));
}

function renderImpact(g, d) {
  const trash = d.include.filter((i) => i !== d.keep);
  const untouched = g.items.filter((i) => !d.include.includes(i));
  const warnings = [];
  if (trash.some((i) => item(i).attachments)) warnings.push("An item sent to the trash has attachments: they go to the trash with it.");
  if (trash.some((i) => item(i).passkeys)) warnings.push("An item sent to the trash holds a passkey: it goes to the trash with it.");
  if (item(d.keep).passkeys) warnings.push("The kept item holds a passkey. The tool checks it is still there after the edit, "
    + "and deletes nothing if it is lost.");
  if (g.passwordLabels && new Set(d.include.map((i) => g.passwordLabels[i])).size > 1) {
    warnings.push(`The other passwords are not kept on the result (they stay in the trashed items for 30 days).`);
  }
  return h("div", { class: "card" }, h("h3", {}, "Impact on the vault"), h("div", { class: "pad" },
    h("div", { class: "summary" },
      h("span", { class: "k" }, "1 item edited"),
      h("span", { class: "d" }, `${trash.length} to trash`),
      h("span", { class: "u" }, `${untouched.length} untouched`)),
    warnings.map((w) => h("div", { class: "note" }, w))));
}

function renderActions(g, d, canEdit) {
  if (!canEdit) return null;
  return h("div", { class: "actions" },
    h("button", { class: "btn primary", disabled: !d.action, onclick: () => validate(g, true) }, "Validate and next ", h("span", { class: "kbd" }, "V")),
    h("button", { class: "btn", disabled: !d.action, onclick: () => validate(g, false) }, "Validate"),
    g.status === "validated" ? h("button", { class: "btn", onclick: () => save(g, "todo") }, "Unvalidate") : null,
    h("button", { class: "btn ghost", onclick: () => resetGroup(g) }, "Reset to suggestion"),
    h("span", { class: "spacer" }),
    h("span", { class: "small" }, h("span", { class: "kbd" }, "J"), " / ", h("span", { class: "kbd" }, "K"), " next / previous"));
}

// Group actions

function edit(g, change) {
  const d = clone(decisionOf(g));
  change(d);
  ui.drafts[g.id] = d;
  if (g.status === "validated") g.status = "todo";
  render();
  clearTimeout(ui.saveTimers[g.id]);
  ui.saveTimers[g.id] = setTimeout(() => save(g, "todo", true), 400);
}

async function save(g, status, quiet = false) {
  clearTimeout(ui.saveTimers[g.id]);
  const d = decisionOf(g);
  try {
    await api("/api/group/update", { id: g.id, decision: d, status });
    g.decision = d;
    g.status = status;
    if (ui.drafts[g.id] === d) delete ui.drafts[g.id];
  } catch (err) {
    toast(err.message);
    if (!quiet) throw err;
  }
  if (!quiet) await load();
}

async function validate(g, next) {
  try { await save(g, "validated"); } catch { return; }
  if (next) move(1, g.id);
}

function move(step, fromId = ui.selected) {
  const groups = groupsFiltered();
  if (!groups.length) return;
  const idx = groups.findIndex((g) => g.id === fromId);
  let target = groups[Math.min(Math.max(idx + step, 0), groups.length - 1)];
  if (idx < 0) target = groups[0];
  ui.selected = target.id;
  render();
}

async function resetGroup(g) {
  delete ui.drafts[g.id];
  try { await api("/api/group/reset", { id: g.id }); } catch (err) { toast(err.message); }
  load();
}

async function removeItem(g, id) {
  try { await api("/api/group/remove-item", { id: g.id, item: id }); } catch (err) { toast(err.message); }
  delete ui.drafts[g.id];
  load();
}

async function refresh() {
  try { await api("/api/refresh", {}); toast("Synced with Bitwarden."); } catch (err) { toast(err.message); }
  load();
}

async function quit() {
  if (!confirm("Quit the tool? Your decisions are saved and you can resume later.")) return;
  try { await api("/api/quit", {}); } catch { /* server already gone */ }
  document.getElementById("app").replaceChildren(h("div", { class: "splash" }, h("h1", {}, "Stopped"),
    h("p", {}, "Your decisions are saved in the work file. Run the tool again to resume.")));
  if (ui.polling) clearInterval(ui.polling);
}

// Apply

function openApplyDialog() {
  const validated = ui.state.groups.filter((g) => g.status === "validated");
  const merges = validated.filter((g) => g.decision.action === "merge");
  const trash = merges.reduce((n, g) => n + g.decision.include.length - 1, 0);
  const untouched = validated.length - merges.length;
  const backup = h("input", { type: "checkbox", checked: true });
  const bg = h("div", { class: "modal-bg", onclick: (e) => { if (e.target === bg) bg.remove(); } },
    h("div", { class: "modal" },
      h("h3", {}, "Apply the validated groups"),
      h("p", {}, `${merges.length} item(s) edited, ${trash} sent to the trash, ${untouched} group(s) marked as left untouched. `
        + "Groups still to review are not touched."),
      h("p", { class: "small" }, "Before each group, the tool checks with Bitwarden that no item changed since your review. "
        + "Changed groups are skipped and listed in the report."),
      h("label", {}, backup, " Make an encrypted backup first (bw may ask for your master password in the terminal)"),
      h("div", { class: "foot" },
        h("button", { class: "btn", onclick: () => bg.remove() }, "Cancel"),
        h("button", {
          class: "btn primary", onclick: async () => {
            bg.remove();
            try {
              await api("/api/apply", { groups: validated.map((g) => g.id), backup: backup.checked });
            } catch (err) { toast(err.message); }
            load();
          },
        }, "Apply"))));
  document.body.append(bg);
}

function renderProgress() {
  const p = ui.state.progress;
  const done = p.phase === "finished";
  return h("div", { class: "modal-bg" }, h("div", { class: "modal" },
    h("h3", {}, done ? "Finished" : "Applying changes…"),
    h("div", { class: "bar", style: "height:8px;margin:12px 0" }, h("i", { class: "a", style: `width:${(p.done / (p.total || 1)) * 100}%` })),
    h("div", { class: "small" }, `${p.done} / ${p.total} · ${p.phase}`),
    p.error ? h("div", { class: "note err" }, p.error) : null,
    done ? h("div", { class: "foot" },
      h("button", { class: "btn", onclick: () => { ui.state.progress = {}; render(); } }, "Close"),
      p.runId ? h("button", { class: "btn primary", onclick: () => { ui.state.progress = {}; render(); openReport(p.runId); } }, "Open the report") : null)
      : h("p", { class: "small" }, "Keep this page and the tool open until the end.")));
}

async function openReport(runId) {
  const tab = window.open("", "_blank");
  try {
    const html = await api(`/api/report?run=${encodeURIComponent(runId)}`);
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    if (tab) tab.location = url; else window.location = url;
  } catch (err) {
    if (tab) tab.close();
    toast(err.message);
  }
}

// All logins

function renderLogins() {
  const s = ui.state;
  const q = ui.loginQuery.trim().toLowerCase();
  const all = Object.values(s.items).sort((a, b) => (a.domain || a.name).localeCompare(b.domain || b.name));
  const scoped = all.filter((i) => ui.loginScope === "all" || (ui.loginScope === "free" ? !i.groupId : !!i.groupId));
  const shown = scoped.filter((i) => !q || [i.name, i.username, i.domain, ...i.uris.map((u) => u.uri)]
    .some((v) => (v || "").toLowerCase().includes(q)));
  const limit = 400;
  for (const id of [...ui.picked]) if (!s.items[id]) ui.picked.delete(id);
  const picked = [...ui.picked];
  const scope = (id, label) => h("button", { class: `chip ${ui.loginScope === id ? "on" : ""}`, onclick: () => { ui.loginScope = id; render(); } }, label);
  const rows = shown.slice(0, limit).map((i) => {
    const g = i.groupId && groupById(i.groupId);
    return h("tr", {},
      h("td", {}, h("input", {
        type: "checkbox", checked: ui.picked.has(i.id),
        onchange: (e) => { if (e.target.checked) ui.picked.add(i.id); else ui.picked.delete(i.id); render(); },
      })),
      h("td", {}, i.name), h("td", {}, i.username), h("td", {}, i.domains.join(", ") || h("span", { class: "small" }, "(none)")),
      h("td", { class: "uris" }, i.uris.map((u) => h("div", {}, u.uri))),
      h("td", {}, g ? h("a", { class: "link", onclick: () => { ui.view = "review"; ui.filter = "all"; ui.selected = g.id; render(); } },
        `${g.decision.name || g.domain} (${STATUS_LABEL[g.status]})`) : i.released ? h("span", { class: "small" }, "taken out by you") : ""));
  });
  return h("main", { class: "page" },
    h("div", { class: "toolbar" },
      h("input", {
        class: "search", type: "search", placeholder: "Search name, username, URI", value: ui.loginQuery,
        oninput: (e) => { ui.loginQuery = e.target.value; render(); document.querySelector(".toolbar .search")?.focus(); },
      }),
      h("div", { class: "chips" }, scope("free", "Not in a group"), scope("grouped", "In a group"), scope("all", "All")),
      h("span", { class: "spacer" }),
      h("span", { class: "small" }, `${picked.length} selected`),
      h("button", {
        class: "btn", disabled: picked.length < 2, title: "Group the selected logins by hand (e.g. amazon.fr and amazon.com)",
        onclick: async () => {
          try {
            const res = await api("/api/group/create", { items: picked });
            ui.picked.clear(); ui.view = "review"; ui.filter = "all"; ui.selected = res.id;
          } catch (err) { toast(err.message); }
          load();
        },
      }, "Group selected"),
      h("button", {
        class: "btn", disabled: !picked.length, title: "Rename the selected logins after their domain (not in a group only)",
        onclick: async () => {
          try {
            const res = await api("/api/rename", { items: picked });
            ui.picked.clear();
            toast(`${res.count} rename(s) added and validated. Review them in Review > Validated.`);
          } catch (err) { toast(err.message); }
          load();
        },
      }, "Rename after domain"),
      picked.length ? h("button", { class: "btn ghost", onclick: () => { ui.picked.clear(); render(); } }, "Clear") : null),
    h("table", {}, h("tr", {}, h("th", {}, ""), h("th", {}, "Name"), h("th", {}, "Username"), h("th", {}, "Domain"),
      h("th", {}, "URIs"), h("th", {}, "Group")), rows),
    shown.length > limit ? h("p", { class: "small" }, `${shown.length - limit} more: refine the search.`) : null,
    !shown.length ? h("div", { class: "empty" }, "No login.") : null);
}

// History

function renderHistory() {
  const runs = ui.state.runs;
  return h("main", { class: "page" },
    h("p", { class: "small" }, "Reports are also saved as HTML files and can be opened without the tool. Work file: ",
      h("code", {}, ui.state.workfile)),
    runs.length ? h("table", {}, h("tr", {}, h("th", {}, "Run"), h("th", {}, "Edited"), h("th", {}, "Trashed"),
      h("th", {}, "Decided by you"), h("th", {}, "Not applied"), h("th", {}, "Report file"), h("th", {}, "")),
    runs.map((r) => h("tr", {},
      h("td", {}, date(r.started)), h("td", {}, r.counts.edited ?? 0), h("td", {}, r.counts.trashed ?? 0),
      h("td", {}, r.counts.byYou ?? 0), h("td", {}, (r.counts.stale ?? 0) + (r.counts.failed ?? 0)),
      h("td", { class: "uris" }, r.report || ""),
      h("td", {}, h("button", { class: "btn small", onclick: () => openReport(r.id) }, "Open")))))
      : h("div", { class: "empty" }, "No run yet."));
}

// Keyboard

document.addEventListener("keydown", (e) => {
  if (!ui.state?.unlocked || ui.view !== "review" || document.querySelector(".modal-bg")) return;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
  const g = ui.selected && groupById(ui.selected);
  if (e.key === "j") move(1);
  else if (e.key === "k") move(-1);
  else if (e.key === "v" && g && editable(g) && decisionOf(g).action) validate(g, true);
  else if (e.key === "/") { e.preventDefault(); document.getElementById("q")?.focus(); }
});

// Start

const fromHash = new URLSearchParams(location.hash.slice(1)).get("t");
if (fromHash) {
  sessionStorage.setItem("bwdedupe-token", fromHash);
  history.replaceState(null, "", location.pathname);
}
ui.token = fromHash || sessionStorage.getItem("bwdedupe-token") || "";
load();
