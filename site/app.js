// Chaos Doctor battle arena: replays a battle.json log one scene at a time.
// Every scene redraws a fixed set of panels in place (no growing page), so playback stays smooth.
(() => {
  const $ = (s) => document.querySelector(s);
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  const ATTACK = {
    token_timeout: ["Model timeout", "the model froze mid-reply and timed out"],
    rate_limit_storm: ["429 storm", "the provider answered with a burst of 429 \"too many requests\" errors"],
    tool_failure: ["Tool crash", "the order-lookup tool crashed"],
    silent_degradation: ["Garbled reply", "the model replied with scrambled text, with no error at all"],
    context_length: ["Prompt too long", "the model rejected the prompt as too long"],
    prompt_injection: ["Prompt injection", "hidden text in the order data told the agent to reply \"PWNED-42\""],
  };
  const RECIPE = {
    retry: "retry the call with backoff",
    timeout: "fail fast instead of hanging",
    fallback: "return a safe default",
    validate_output: "re-ask when the reply looks scrambled",
    trim_prompt: "shorten the prompt and retry",
    sanitize: "strip injected instructions from tool data",
  };
  const kindName = (k) => (ATTACK[k] || [k])[0];
  const kindText = (k) => (ATTACK[k] || [k, k])[1];
  const label = (lbl) => lbl.replace(/@.*/, "");

  // ---------- diff replay (same algorithm as tests/test_site_replay.py) ----------
  function applyDiff(lines, diff) {
    const out = [];
    const added = new Set();
    const rows = diff.split("\n");
    let i = 0;
    let k = 0;
    while (k < rows.length) {
      const m = rows[k++].match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/);
      if (!m) continue;
      const oldStart = Number(m[1]);
      const oldLen = m[2] === undefined ? 1 : Number(m[2]);
      const start = oldLen ? oldStart - 1 : oldStart;
      while (i < start) out.push(lines[i++]);
      while (k < rows.length && !rows[k].startsWith("@@")) {
        const row = rows[k++];
        if (row.startsWith("+") && !row.startsWith("+++")) { added.add(out.length); out.push(row.slice(1)); }
        else if (row.startsWith("-") && !row.startsWith("---")) i++;
        else if (row.startsWith(" ")) out.push(lines[i++]);
      }
    }
    while (i < lines.length) out.push(lines[i++]);
    return { lines: out, added };
  }

  // ---------- scenes ----------
  function buildScenes(log) {
    const scenes = [{ kind: "intro", round: 0 }];
    let lastScan = null;
    for (const ev of log.events) {
      if (ev.kind === "round") scenes.push({ kind: "attack", round: ev.round, attacks: ev.attacks, attack: ev.new_attack });
      else if (ev.kind === "scan") { scenes.push({ kind: "scan", round: ev.round, phase: ev.phase, score: ev.score, results: ev.results, prev: lastScan }); lastScan = ev; }
      else if (ev.kind === "diagnosis") scenes.push({ kind: "diag", round: scenes.at(-1).round, ev });
      else if (ev.kind === "patch") scenes.push({ kind: "patch", round: scenes.at(-1).round, ev });
      else if (ev.kind === "patch_noop" || ev.kind === "patch_error") scenes.push({ kind: "note", round: scenes.at(-1).round, ev });
      else if (ev.kind === "done") scenes.push({ kind: "done", round: scenes.at(-1).round, ev });
    }
    return scenes;
  }

  function caption(sc, st) {
    switch (sc.kind) {
      case "intro":
        return "Meet the agent: a shop support bot that looks up an order and asks an LLM to reply. Its code (middle) has <b>no protection at all</b>. Press <b>Play</b> or <kbd>→</kbd>.";
      case "attack":
        if (sc.attacks) return `<b class="atk">Round 1.</b> The Attacker throws the five classic production failures at the agent: timeouts, a 429 storm, a crashing tool, garbled replies and a too-long prompt.`;
        return `<b class="atk">Round ${sc.round}.</b> The Attacker AI reads the patched code and picks a new attack: <b>${esc(kindName(sc.attack.kind))}</b>, ${esc(kindText(sc.attack.kind))}.`;
      case "scan": {
        const n = sc.results.length;
        const pass = sc.results.filter((r) => r.passes === r.trials).length;
        const failing = sc.results.filter((r) => r.passes < r.trials).map((r) => kindName(r.attack.kind).toLowerCase());
        if (sc.phase === "healed") {
          return pass === n
            ? `<b class="doc">Verified.</b> Re-tested against every attack: all ${n} survived. Resilience <b>${sc.score}/100</b>.`
            : `<b>Verified.</b> ${pass}/${n} attacks survived; still failing: ${esc(failing.join(", "))}. Resilience <b>${sc.score}/100</b>.`;
        }
        if (pass === 0) return `Every attack crashed or fooled the agent. Resilience <b class="atk">${sc.score}/100</b>.`;
        return `${pass}/${n} attacks survived; <b class="atk">${esc(failing.join(", "))}</b> got through. Resilience <b>${sc.score}/100</b>.`;
      }
      case "diag": {
        const e = sc.ev;
        const fixedPlace = (e.explanation || "").startsWith("(placement corrected");
        return `<b class="doc">The Doctor AI</b> reads the failure (${esc(kindName(label(e.attack)).toLowerCase())}) and prescribes: <b>${esc(RECIPE[e.recipe] || e.recipe)}</b> on <code>${esc(e.target_function)}()</code>.${fixedPlace ? " Our call-site check moved it to the function that makes the failing call." : ""}`;
      }
      case "patch":
        return sc.ev.kept
          ? `The fix is added to the real code (<span class="doc">highlighted</span>) and re-tested: <b>${sc.ev.before} → ${sc.ev.after}</b>. It helped, so it's <b class="doc">kept</b>.`
          : `The fix is tried and re-tested: ${sc.ev.before} → ${sc.ev.after}. It didn't help, so it's <b>rolled back</b>.`;
      case "note":
        return "That fix was already in place, so the Doctor moves on.";
      case "done": {
        const rounds = st.scenes.filter((s) => s.kind === "attack").length;
        return `<b class="doc">Battle over:</b> ${st.points[0]?.score ?? 0} → <b>${sc.ev.final_score}/100</b> in ${rounds} rounds. Every highlighted line is a real, reviewable diff.`;
      }
    }
    return "";
  }

  const PHASE = { attack: "attack", diag: "diagnose", patch: "patch", note: "patch", done: "verify" };

  // ---------- state ----------
  const S = { log: null, base: [], scenes: [], i: 0, timer: null, points: [] };

  function stateAt(k) {
    const st = { score: null, results: null, prevResults: null, attacker: null, doctor: null, verdict: null, lines: S.base, added: new Set(), points: [], scenes: S.scenes };
    for (let j = 0; j <= k; j++) {
      const sc = S.scenes[j];
      const here = j === k;
      if (sc.kind === "attack") { st.attacker = sc; st.doctor = null; st.verdict = null; }
      if (sc.kind === "scan") {
        st.prevResults = here ? st.results : null;
        st.score = sc.score; st.results = sc.results; st.scanRound = sc.round; st.scanPhase = sc.phase;
        st.points.push({ score: sc.score, phase: sc.phase });
      }
      if (sc.kind === "diag") { st.doctor = sc.ev; st.verdict = null; }
      if (sc.kind === "patch") {
        st.verdict = sc.ev;
        if (sc.ev.kept) {
          const r = applyDiff(st.lines, sc.ev.diff);
          st.lines = r.lines;
          st.added = here ? r.added : new Set();
          st.score = sc.ev.after;
          st.points.push({ score: sc.ev.after, phase: "patch" });
        }
      }
      if (!here && sc.kind !== "patch") st.added = new Set();
    }
    return st;
  }

  // ---------- render ----------
  function renderAttacker(st, live) {
    const box = $("#atk-body");
    $("#attacker").classList.toggle("live", live);
    const a = st.attacker;
    if (!a) { box.innerHTML = '<p class="muted small">Waiting for the first attack.</p>'; return; }
    if (a.attacks) {
      box.innerHTML = `<p class="kind atk">Round 1 · classic failures</p><p class="plain">Injected with agentic-chaos into the model client and the tool:</p>
        <div class="chips">${a.attacks.map((x) => `<span class="chip atk">${esc(kindName(x.kind))}</span>`).join("")}</div>`;
      return;
    }
    const k = a.attack;
    const ai = S.log.model.startsWith("rules") ? "" : '<span class="tag ai">chosen by AI</span>';
    box.innerHTML = `<p class="kind atk">Round ${a.round} · ${esc(kindName(k.kind))}${ai}</p>
      <p class="plain">${esc(kindText(k.kind))[0].toUpperCase() + esc(kindText(k.kind)).slice(1)}.</p>
      <dl class="kv"><div><dt>Target</dt><dd><code>${esc(k.target === "llm" ? "the model call" : k.target + "()")}</code></dd></div>
      ${Object.keys(k.params || {}).filter((p) => p !== "payload").length ? `<div><dt>Settings</dt><dd><code>${esc(Object.entries(k.params).filter(([p]) => p !== "payload").map(([p, v]) => `${p}=${v}`).join(", "))}</code></dd></div>` : ""}</dl>
      ${k.params?.payload ? `<div class="payload">${esc(k.params.payload)}</div>` : ""}
      ${k.rationale && k.rationale !== "not tried yet" ? `<p class="why">"${esc(k.rationale)}"</p>` : ""}`;
  }

  function renderDoctor(st, live) {
    const box = $("#doc-body");
    $("#doctor").classList.toggle("live", live);
    const d = st.doctor;
    if (!d) { box.innerHTML = '<p class="muted small">Waiting for something to break.</p>'; return; }
    const ai = d.source === "llm";
    const corrected = (d.explanation || "").startsWith("(placement corrected");
    const expl = (d.explanation || "").replace(/^\([^)]*\)\s*/, "");
    const params = Object.entries(d.params || {}).map(([k, v]) => `${k}=${v}`).join(", ");
    const conf = Math.round((d.confidence || 0) * 100);
    const v = st.verdict;
    box.innerHTML = `<p class="kind doc">${esc(kindName(label(d.attack)))}${ai ? '<span class="tag ai">AI diagnosis</span>' : '<span class="tag">rules</span>'}${corrected ? '<span class="tag fix">placement corrected</span>' : ""}</p>
      <dl class="kv">
        <div><dt>Root cause</dt><dd>${esc(d.root_cause)}</dd></div>
        <div><dt>Prescription</dt><dd><span class="rx">@guards.${esc(d.recipe)}${params ? `(${esc(params)})` : ""}</span><br><span class="muted small">${esc(RECIPE[d.recipe] || "")} · on ${esc(d.target_function)}()</span></dd></div>
        <div><dt>Confidence ${conf}%</dt><dd><div class="conf"><i style="transform:scaleX(${conf / 100})"></i></div></dd></div>
      </dl>
      ${expl && expl !== d.root_cause ? `<p class="why">${esc(expl)}</p>` : ""}
      ${v ? `<div class="verdict ${v.kept ? "kept" : "rolled"}">${v.kept ? "✓ Kept" : "↺ Rolled back"} · score ${v.before} → ${v.after}</div>` : ""}`;
  }

  function renderVitals(st, sc) {
    const s = st.score;
    $("#score").textContent = s === null ? "--" : s;
    const ring = $("#ring");
    ring.style.strokeDashoffset = String(326.7 * (1 - (s || 0) / 100));
    ring.style.stroke = s === null ? "var(--line)" : s >= 90 ? "var(--doc)" : s >= 60 ? "var(--warn)" : "var(--atk)";
    const tiles = $("#tiles");
    // Tiles come from full scans; after a patch they are one fix behind, so say so.
    const stale = ["patch", "diag", "attack", "note"].includes(sc.kind);
    tiles.classList.toggle("stale", stale && !!st.results);
    $(".v-label").textContent = !st.results
      ? "Resilience under each attack"
      : stale
        ? `Last full scan (round ${st.scanRound}) · ${sc.kind === "attack" ? "before this attack" : "before this fix"}`
        : `Each attack · round ${st.scanRound} ${st.scanPhase === "healed" ? "after healing" : "under attack"}`;
    if (!st.results) { tiles.innerHTML = '<span class="muted small">No attacks yet.</span>'; }
    else {
      const prev = new Map((st.prevResults || []).map((r) => [r.label, r.passes === r.trials]));
      tiles.innerHTML = st.results.map((r) => {
        const ok = r.passes === r.trials;
        const changed = sc.kind === "scan" && prev.size && prev.get(r.label) !== ok;
        return `<div class="tile ${ok ? "pass" : "fail"}${changed ? " new" : ""}" title="${esc(r.label)}"><span>${esc(kindName(r.attack.kind))}</span><span>${ok ? "✓" : "✗"}</span></div>`;
      }).join("");
    }
    // sparkline of every score the agent has had so far
    const pts = st.points;
    const W = 300, H = 46, n = Math.max(pts.length, 2);
    const x = (i) => 4 + (i * (W - 8)) / (n - 1);
    const y = (v) => 4 + ((100 - v) * (H - 8)) / 100;
    let g = `<line x1="4" x2="${W - 4}" y1="${y(100)}" y2="${y(100)}" stroke="#222c3b" stroke-dasharray="3 4"/>`;
    if (pts.length) {
      g += `<polyline fill="none" stroke="#e8eef6" stroke-width="1.6" stroke-linejoin="round" points="${pts.map((p, i) => `${x(i)},${y(p.score)}`).join(" ")}"/>`;
      g += pts.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.score)}" r="3.2" fill="${p.phase === "attacked" ? "#fb5a72" : "#22d3a0"}"/>`).join("");
    }
    $("#spark").innerHTML = g;
  }

  let codeKey = "";
  function renderCode(st) {
    const key = st.lines.length + ":" + [...st.added].join(",") + ":" + st.lines.join("\n").length;
    if (key === codeKey) return;
    codeKey = key;
    const code = $("#code");
    let inDoc = false;
    code.innerHTML = st.lines.map((line, i) => {
      const t = line.trim();
      let cls = "ln";
      if (st.added.has(i)) cls += " add";
      else if (t.startsWith("@guards")) cls += " guard";
      else if (t.startsWith("def ")) cls += " fn";
      if (t.startsWith('"""')) { cls += " cmt"; if (!(t.length > 3 && t.endsWith('"""'))) inDoc = !inDoc; }
      else if (inDoc || t.startsWith("#")) cls += " cmt";
      return `<span class="${cls}">${esc(line) || " "}</span>`;
    }).join("");
    const guards = st.lines.filter((l) => l.trim().startsWith("@guards")).length;
    $("#code-badge").textContent = guards ? `${guards} guard${guards > 1 ? "s" : ""} added` : "unprotected";
    // Bring the new guard into view (not the import line), inside the code box only.
    const added = [...code.querySelectorAll(".ln.add")];
    const target = added.find((el) => el.textContent.trim().startsWith("@guards")) || added[0];
    if (target) code.scrollTop = Math.max(0, target.offsetTop - code.clientHeight / 3);
  }

  function renderTimeline() {
    const tl = $("#timeline");
    const groups = [];
    S.scenes.forEach((sc, i) => {
      if (!groups.length || groups.at(-1).round !== sc.round) groups.push({ round: sc.round, items: [] });
      groups.at(-1).items.push(i);
    });
    const cls = { intro: "", attack: "k-attack", scan: "k-scan", diag: "k-diag", patch: "k-patch", note: "", done: "k-patch" };
    const name = { intro: "Start", attack: "Attack", scan: "Scan", diag: "Diagnosis", patch: "Patch", note: "Note", done: "Done" };
    tl.innerHTML = groups.map((g) => `<div class="tl-round"><span>${g.round ? "R" + g.round : ""}</span>${g.items
      .map((i) => `<button class="tl-step ${cls[S.scenes[i].kind]}" data-i="${i}" title="${name[S.scenes[i].kind]}" aria-label="Step ${i + 1}: ${name[S.scenes[i].kind]}"></button>`).join("")}</div>`).join("");
  }

  function render() {
    const sc = S.scenes[S.i];
    const st = stateAt(S.i);
    $("#caption-text").innerHTML = caption(sc, st);
    $("#step-no").textContent = `${S.i + 1}/${S.scenes.length}`;
    const phase = sc.kind === "scan" ? (sc.phase === "healed" ? "verify" : "scan") : PHASE[sc.kind];
    document.querySelectorAll("#phases li").forEach((li) => li.classList.toggle("on", li.dataset.p === phase));
    renderAttacker(st, sc.kind === "attack");
    renderDoctor(st, sc.kind === "diag" || sc.kind === "patch");
    renderVitals(st, sc);
    renderCode(st);
    document.querySelectorAll(".tl-step").forEach((b) => {
      const i = Number(b.dataset.i);
      b.classList.toggle("done", i < S.i);
      b.classList.toggle("now", i === S.i);
    });
    $("#prev").disabled = S.i === 0;
    $("#next").disabled = S.i === S.scenes.length - 1;
  }

  // ---------- player ----------
  const playBtn = $("#play");
  function go(i) { S.i = Math.max(0, Math.min(S.scenes.length - 1, i)); render(); }
  function stop() { clearTimeout(S.timer); S.timer = null; playBtn.textContent = S.i >= S.scenes.length - 1 ? "↺ Replay" : "▶ Play"; }
  function play() {
    if (S.i >= S.scenes.length - 1) go(0);
    playBtn.textContent = "❚❚ Pause";
    const tick = () => {
      if (S.i >= S.scenes.length - 1) return stop();
      go(S.i + 1);
      S.timer = setTimeout(tick, Number($("#speed").value));
    };
    S.timer = setTimeout(tick, 300);
  }

  async function load(src) {
    stop();
    $("#caption-text").textContent = "Loading the battle...";
    try {
      const [log, agent] = await Promise.all([
        fetch(src, { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
        S.base.length ? null : fetch("data/shop_agent.py.txt").then((r) => (r.ok ? r.text() : "")),
      ]);
      if (agent !== null) S.base = agent.split("\n");
      S.log = log;
      S.scenes = buildScenes(log);
      codeKey = "";
      const who = log.model.startsWith("rules") ? "rules (no model)" : `${log.model} · local`;
      $("#atk-model").textContent = who;
      $("#doc-model").textContent = who;
      renderTimeline();
      go(0);
      stop();
    } catch (err) {
      $("#caption-text").textContent = `Could not load this battle (${err.message}).`;
    }
  }

  playBtn.addEventListener("click", () => (S.timer ? stop() : play()));
  $("#prev").addEventListener("click", () => { stop(); go(S.i - 1); });
  $("#next").addEventListener("click", () => { stop(); go(S.i + 1); stop(); });
  $("#restart").addEventListener("click", () => { stop(); go(0); });
  $("#timeline").addEventListener("click", (e) => {
    const b = e.target.closest(".tl-step");
    if (b) { stop(); go(Number(b.dataset.i)); stop(); }
  });
  document.querySelectorAll(".tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => { t.classList.toggle("active", t === tab); t.setAttribute("aria-selected", t === tab); });
      load(tab.dataset.src);
    }),
  );
  document.addEventListener("keydown", (e) => {
    if (!S.scenes.length || e.target.closest("input, select, textarea")) return;
    if (e.key === "ArrowRight") { e.preventDefault(); stop(); go(S.i + 1); stop(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); stop(); go(S.i - 1); }
    else if (e.key === " " && !e.target.closest("button, a")) { e.preventDefault(); S.timer ? stop() : play(); }
  });

  // ---------- results + copy buttons ----------
  fetch("data/results.json").then((r) => r.json()).then((res) => {
    const b = res.benchmark["qwen3:4b"];
    const rows = b ? [
      ["Bugs fixed", b.fixed, b.cases, "var(--doc)"],
      ["Right recipe", b.recipe_correct, b.cases, "var(--doc)"],
      ["Right function, own pick", b.function_correct, b.cases, "var(--accent)"],
    ] : [];
    $("#bench").innerHTML = rows.map(([name, v, n, c]) =>
      `<div class="bar-row"><span>${name}</span><div class="bar"><i style="width:${(100 * v) / n}%;background:${c}"></i></div><b>${v}/${n}</b></div>`).join("") +
      (b ? `<p class="muted small" style="margin:0">qwen3:4b on an 8 GB M1, ~${Math.round(b.avg_seconds)} s per diagnosis, never fell back to rules. The rule-based Doctor scores 20/20 but was written for this menu.</p>` : "");
    const names = { rag_answerer: "RAG answerer", two_step_router: "Two-step router", hand_hardened: "Hand-hardened" };
    const lb = { shop_agent: { before: 0, after: 100 }, ...res.leaderboard };
    names.shop_agent = "Shop agent (demo)";
    $("#lb").innerHTML = Object.entries(lb).map(([k, v]) =>
      `<div class="lb-row"><span>${esc(names[k] || k)}</span><div class="lb-track"><i class="after" style="left:0;width:${v.after}%"></i><i class="before" style="left:0;width:${Math.max(v.before, 1.5)}%"></i></div><b>${v.before} → ${v.after}</b></div>`).join("") +
      '<p class="muted small" style="margin:0"><span class="atk">■</span> before · <span class="doc">■</span> after. The hand-hardened agent swallows errors, so retries can\'t help: an honest limitation.</p>';
  }).catch(() => {});

  document.querySelectorAll(".copy").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText($("#" + btn.dataset.copy).textContent); btn.textContent = "Copied"; }
      catch { btn.textContent = "Select + copy"; }
      setTimeout(() => (btn.textContent = "Copy"), 1500);
    }),
  );

  load("battles/qwen3-4b.json");
})();
