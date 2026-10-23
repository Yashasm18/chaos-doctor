// Chaos Doctor battle replay: plays a battle.json log event by event.
(() => {
  const $ = (sel) => document.querySelector(sel);
  const feed = $("#feed");
  const empty = $("#empty");
  const playBtn = $("#play");
  const FUNCS = ["get_order", "ask_llm"];

  let log = null;
  let idx = 0;
  let timer = null;
  let points = [];
  let guards = {};
  let source = "battles/qwen3-4b.json";

  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const el = (html) => {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  };
  const attackName = (a) => (a.target && a.target !== "llm" ? `${a.kind} on ${a.target}()` : `${a.kind} on the model`);
  const color = (s) => (s >= 90 ? "var(--doc)" : s >= 60 ? "var(--warn)" : "var(--atk)");

  const ATTACK_TEXT = {
    token_timeout: "the model hangs, then times out",
    rate_limit_storm: "a burst of HTTP 429 rate-limit errors",
    tool_failure: "the tool crashes",
    silent_degradation: "the reply comes back garbled, no error",
    context_length: "the model rejects the prompt as too long",
    prompt_injection: "hidden instructions planted in the tool's data",
  };

  // ---------- side panel ----------
  function setScore(score, note) {
    const s = $("#score");
    s.textContent = score;
    s.style.color = color(score);
    $("#score-note").textContent = note;
  }

  function drawChart() {
    const svg = $("#chart");
    const W = 320, H = 150, L = 30, R = 12, T = 12, B = 24;
    const n = Math.max(points.length, 2);
    const x = (i) => L + (i * (W - L - R)) / (n - 1);
    const y = (v) => T + ((100 - v) * (H - T - B)) / 100;
    let g = "";
    for (const v of [0, 50, 100]) {
      g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#243041" stroke-dasharray="${v ? "3 4" : ""}"/>`;
      g += `<text x="${L - 6}" y="${y(v) + 4}" fill="#8b98a9" font-size="10" text-anchor="end">${v}</text>`;
    }
    if (points.length) {
      const path = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.score)}`).join(" ");
      g += `<path d="${path}" fill="none" stroke="#e6edf5" stroke-width="2" stroke-linejoin="round"/>`;
      points.forEach((p, i) => {
        const c = p.phase === "healed" ? "#10b981" : "#f43f5e";
        g += `<circle cx="${x(i)}" cy="${y(p.score)}" r="4.5" fill="${c}" stroke="#121821" stroke-width="2"><title>Round ${p.round} ${p.phase}: ${p.score}</title></circle>`;
      });
      const last = points[points.length - 1];
      g += `<text x="${x(points.length - 1)}" y="${y(last.score) - 9}" fill="#e6edf5" font-size="11" font-weight="700" text-anchor="middle">${last.score}</text>`;
    }
    g += `<text x="${L}" y="${H - 6}" fill="#8b98a9" font-size="10"><tspan fill="#f43f5e">●</tspan> after attack   <tspan fill="#10b981">●</tspan> after healing</text>`;
    svg.innerHTML = g;
  }

  function drawGuards(fresh) {
    const box = $("#guards");
    box.innerHTML = FUNCS.map((fn) => {
      const list = guards[fn] || [];
      const chips = list.length
        ? list.map((g) => `<span class="chip${fresh === fn + g ? " new" : ""}">@${esc(g)}</span>`).join("")
        : `<span class="chip none">no protection</span>`;
      return `<div class="fn"><div class="fn-name">${fn}()</div><div class="fn-guards">${chips}</div></div>`;
    }).join("");
  }

  // Read the guard stack for a function from a patch diff (+@guards.x / -@guards.x lines).
  function applyDiffToGuards(ev) {
    let fresh = null;
    const fn = ev.function;
    const list = (guards[fn] = guards[fn] || []);
    for (const line of ev.diff.split("\n")) {
      const m = line.match(/^([+-])\s*@guards\.(\w+)/);
      if (!m) continue;
      const name = m[2];
      if (m[1] === "+" && !list.includes(name)) {
        list.push(name);
        fresh = fn + name;
      }
      if (m[1] === "-" && !ev.diff.includes(`+@guards.${name}`)) list.splice(list.indexOf(name), 1);
    }
    return fresh;
  }

  // ---------- feed cards ----------
  function diffHtml(diff) {
    const rows = diff
      .split("\n")
      .filter((l) => l && !l.startsWith("---") && !l.startsWith("+++"))
      .map((l) => {
        const cls = l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hunk" : "";
        return `<div class="${cls}">${esc(l)}</div>`;
      });
    return `<div class="diff">${rows.join("")}</div>`;
  }

  function card(ev) {
    switch (ev.kind) {
      case "round": {
        const head = `<div class="round">Round ${ev.round}</div>`;
        if (ev.attacks) {
          const chips = ev.attacks.map((a) => `<span class="res fail">${esc(a.kind)}</span>`).join("");
          return el(`<div class="ev">${head}<div class="box atk-box"><div class="who"><span class="avatar atk">!</span>Chaos begins<span class="badge">5 classic faults</span></div>
            <div class="why">The five most common ways agents break in production, injected with agentic-chaos.</div><div class="results">${chips}</div></div></div>`);
        }
        const a = ev.new_attack;
        const ai = log.model.startsWith("rules") ? "rules" : log.model;
        const payload = a.kind === "prompt_injection" && a.params.payload ? `<div class="payload">${esc(a.params.payload)}</div>` : "";
        return el(`<div class="ev">${head}<div class="box atk-box"><div class="who"><span class="avatar atk">!</span>Attacker AI<span class="badge ${ai === "rules" ? "" : "ai"}">${esc(ai)}</span></div>
          <div class="title-line">${esc(attackName(a))}</div><div class="why">${esc(ATTACK_TEXT[a.kind] || "")}${a.rationale ? ` · "${esc(a.rationale)}"` : ""}</div>${payload}</div></div>`);
      }
      case "scan": {
        const res = ev.results
          .map((r) => `<span class="res ${r.passes === r.trials ? "pass" : "fail"}">${esc(r.label)} ${r.passes}/${r.trials}</span>`)
          .join("");
        const firstFail = ev.results.find((r) => r.passes < r.trials);
        const why = firstFail && ev.phase === "attacked" ? `<div class="fail-why">${esc(firstFail.failures[0]).slice(0, 140)}</div>` : "";
        const label = ev.phase === "attacked" ? "Under attack" : "After healing";
        return el(`<div class="ev"><div class="box"><div class="who"><span class="avatar scan">#</span>${label}<span class="scan-score" style="margin-left:auto;color:${color(ev.score)}">${ev.score}/100</span></div>
          <div class="results">${res}</div>${why}</div></div>`);
      }
      case "diagnosis": {
        const ai = ev.source === "llm";
        const corrected = (ev.explanation || "").startsWith("(placement corrected");
        const expl = (ev.explanation || "").replace(/^\([^)]*\)\s*/, "");
        const params = Object.entries(ev.params || {}).map(([k, v]) => `${k}=${v}`).join(", ");
        return el(`<div class="ev"><div class="box doc-box"><div class="who"><span class="avatar doc">+</span>Doctor AI<span class="badge ${ai ? "ai" : ""}">${ai ? esc(log.model) : "rules"}</span></div>
          <dl class="rx"><dt>Failure</dt><dd><code>${esc(ev.attack)}</code></dd>
          <dt>Root cause</dt><dd>${esc(ev.root_cause)}</dd>
          <dt>Prescription</dt><dd><code>@guards.${esc(ev.recipe)}${params ? `(${esc(params)})` : ""}</code>${params ? "" : ' <span class="muted small">(default settings)</span>'} on <code>${esc(ev.target_function)}()</code>${corrected ? ' <span class="muted small">(placement corrected)</span>' : ""}</dd>
          <dt>Confidence</dt><dd>${Math.round((ev.confidence || 0) * 100)}%<div class="conf"><i style="width:${Math.round((ev.confidence || 0) * 100)}%"></i></div></dd></dl>
          ${expl && expl !== ev.root_cause ? `<div class="why">${esc(expl)}</div>` : ""}</div></div>`);
      }
      case "patch": {
        const v = ev.kept
          ? `<span class="kept">Kept</span> <span class="muted">score ${ev.before} → ${ev.after}</span>`
          : `<span class="rolled">Rolled back</span> <span class="muted">score ${ev.before} → ${ev.after}, didn't help</span>`;
        return el(`<div class="ev"><div class="box"><div class="who"><span class="avatar scan">✎</span>Patch on ${esc(ev.function)}()</div>${diffHtml(ev.diff)}<div class="verdict">${v}</div></div></div>`);
      }
      case "patch_noop":
        return el(`<div class="ev"><div class="box"><span class="muted">The prescribed fix was already in place for ${esc(ev.attack)}; the Doctor moves on.</span></div></div>`);
      case "patch_error":
        return el(`<div class="ev"><div class="box"><span class="muted">Patch could not be applied: ${esc(ev.error)}</span></div></div>`);
      case "done": {
        const first = points.length ? points[0].score : 0;
        return el(`<div class="ev"><div class="box doc-box done"><div class="muted">Battle over</div><div class="big" style="color:${color(ev.final_score)}">${first} → ${ev.final_score}/100</div>
          <div class="why">The agent went from no protection to battle-tested. Every patch above is a real, reviewable diff.</div></div></div>`);
      }
      default:
        return null;
    }
  }

  // ---------- player ----------
  function stepOnce() {
    if (!log || idx >= log.events.length) return stop(true);
    const ev = log.events[idx++];
    let fresh = null;
    if (ev.kind === "scan") {
      points.push({ round: ev.round, phase: ev.phase, score: ev.score });
      setScore(ev.score, ev.phase === "attacked" ? `Round ${ev.round}: under attack` : `Round ${ev.round}: after healing`);
      drawChart();
    }
    if (ev.kind === "patch" && ev.kept) fresh = applyDiffToGuards(ev);
    if (ev.kind === "patch") drawGuards(fresh);
    const node = card(ev);
    if (node) {
      empty.hidden = true;
      feed.appendChild(node);
      if (timer) node.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    if (idx >= log.events.length) stop(true);
  }

  function play() {
    if (!log) return;
    if (idx >= log.events.length) reset();
    playBtn.textContent = "Pause";
    const tick = () => {
      stepOnce();
      if (timer) timer = setTimeout(tick, Number($("#speed").value));
    };
    timer = setTimeout(tick, 50);
  }

  function stop(finished) {
    clearTimeout(timer);
    timer = null;
    playBtn.textContent = finished && log && idx >= log.events.length ? "Replay" : "Play";
  }

  function reset() {
    stop();
    idx = 0;
    points = [];
    guards = {};
    feed.innerHTML = "";
    empty.hidden = false;
    setScore("--", "Waiting for the first scan");
    $("#score").style.color = "";
    drawChart();
    drawGuards();
  }

  function setMeta() {
    $("#meta-model").textContent = log.model.startsWith("rules") ? "rules (no model)" : log.model;
    $("#meta-date").textContent = new Date(log.started_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    const diags = log.events.filter((e) => e.kind === "diagnosis");
    const patches = log.events.filter((e) => e.kind === "patch");
    const byModel = diags.filter((e) => e.source === "llm").length;
    const fixed = diags.filter((e) => (e.explanation || "").startsWith("(placement corrected")).length;
    $("#meta-fixes").textContent = log.model.startsWith("rules")
      ? `${patches.filter((p) => p.kept).length}/${patches.length} kept`
      : `${byModel}/${diags.length} by AI · ${patches.filter((p) => p.kept).length}/${patches.length} kept${fixed ? ` · ${fixed} re-placed` : ""}`;
  }

  // GitHub Pages only serves static files, so there is no /api/battle to call there.
  const HAS_API = !location.hostname.endsWith("github.io");
  const RUN_LOCALLY =
    "Live battles need a server, and this page is static. Run a fresh one on your laptop in seconds:" +
    '<pre class="try" style="text-align:left;margin-top:12px">pip install -e ".[dev]"\nchaos-doctor battle examples/shop_agent/agent.py --offline</pre>' +
    '<span class="muted small">The two recorded battles above replay real runs, including the qwen3:4b one.</span>';

  async function load(src) {
    source = src;
    reset();
    log = null;
    if (src === "live" && !HAS_API) {
      empty.innerHTML = RUN_LOCALLY;
      return;
    }
    empty.innerHTML = '<span class="spinner"></span>' + (src === "live" ? "Running a fresh battle on the server (about 15 seconds)..." : "Loading battle...");
    try {
      const resp = src === "live" ? await fetch("/api/battle", { method: "POST" }) : await fetch(src, { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      log = await resp.json();
      setMeta();
      empty.innerHTML = "Press <b>Play</b> to start the battle.";
      if (src === "live") play();
    } catch (err) {
      empty.innerHTML =
        src === "live"
          ? `The live runner isn't reachable here (${esc(err.message)}). Try a recorded battle, or run <code>chaos-doctor battle --offline</code> locally.`
          : `Could not load this battle (${esc(err.message)}).`;
    }
  }

  playBtn.addEventListener("click", () => (timer ? stop() : play()));
  $("#step").addEventListener("click", () => { stop(); stepOnce(); });
  $("#restart").addEventListener("click", () => { reset(); play(); });
  $("#all").addEventListener("click", () => { stop(); while (log && idx < log.events.length) stepOnce(); });
  document.querySelectorAll(".tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      load(tab.dataset.src);
    }),
  );

  if (!HAS_API) {
    const live = document.querySelector(".tab.live");
    live.innerHTML = "Run it yourself <small>one command, offline</small>";
  }
  drawGuards();
  drawChart();
  load(source);
})();
