// Interactive "how it works" loop: click a step to see what happens and who does it,
// or walk through the loop. A packet travels the connectors to show the direction of flow.
(() => {
  const svg = document.getElementById("loop-svg");
  const detail = document.getElementById("loop-detail");
  const playBtn = document.getElementById("loop-play");
  if (!svg) return;

  const W = 172, H = 92;
  const NODES = [
    { id: "agent", n: "", kind: "you", x: 20, y: 40, title: "Your agent", lines: ["agent.py exposes", "client, TOOLS, run()"], who: "you",
      text: "Any Python agent that exposes client, TOOLS, TASKS, run() and check(). The demo is a shop support bot that looks up an order and asks an LLM to reply." },
    { id: "scan", n: "1", kind: "code", x: 210, y: 40, title: "Scan", lines: ["agentic-chaos injects", "faults: model + tools"], who: "agentic-chaos",
      text: "Faults hit the model client (timeouts, 429 storms, garbled replies, too-long prompts) and the tools (crashes, prompt injection hidden in their data)." },
    { id: "score", n: "2", kind: "code", x: 400, y: 40, title: "Score 0-100", lines: ["agentic-chaos contracts", "+ the agent's check()"], who: "deterministic code",
      text: "Each run passes only if no error escaped, retries stayed bounded, and the agent's own check() accepts the answer. Score = average pass rate × 100." },
    { id: "doctor", n: "3", kind: "doc", x: 590, y: 40, title: "Doctor AI", lines: ["Qwen3 reads the failure", "→ JSON prescription"], who: "open-weight model",
      text: "Qwen3 reads the failure and the source and answers in strict JSON: root cause, which function, one recipe from a fixed menu, and its parameters. A call-site check fixes placement if needed." },
    { id: "patch", n: "4", kind: "code", x: 780, y: 40, title: "Patch", lines: ["ast adds one guard", "decorator; must parse"], who: "deterministic code",
      text: "Python's ast inserts one decorator such as @guards.retry or @guards.sanitize. The file must still parse, so the agent can never be broken by a fix." },
    { id: "verify", n: "5", kind: "code", x: 780, y: 230, title: "Verify", lines: ["re-scan: keep if score", "goes up, else roll back"], who: "deterministic code",
      text: "Every attack runs again. The patch stays only if the score rises; otherwise it is rolled back. Anything still failing goes back to the Doctor." },
    { id: "attacker", n: "6", kind: "atk", x: 400, y: 230, title: "Attacker AI", lines: ["Qwen3 reads patched", "code, picks next attack"], who: "open-weight model",
      text: "Once everything passes, Qwen3 studies the patched code and picks the next attack from a fixed menu, writing its own prompt-injection payloads. Then the loop runs again." },
  ];
  const EDGES = [
    { from: "agent", to: "scan", d: "M192 86H208", label: ["round 1: 5 classic faults", 200, 28] },
    { from: "scan", to: "score", d: "M382 86H398" },
    { from: "score", to: "doctor", d: "M572 86H588" },
    { from: "doctor", to: "patch", d: "M762 86H778" },
    { from: "patch", to: "verify", d: "M866 132V228" },
    { from: "verify", to: "doctor", d: "M780 258H676V134", label: ["still failing: next fix", 686, 190] },
    { from: "verify", to: "attacker", d: "M780 300H574", label: ["all pass: next round", 604, 320] },
    { from: "attacker", to: "scan", d: "M400 276H296V134", label: ["new attack (incl. its own", 306, 196], label2: ["prompt-injection payloads)", 306, 212] },
  ];
  const ORDER = ["agent", "scan", "score", "doctor", "patch", "verify", "attacker", "scan"];
  const byId = Object.fromEntries(NODES.map((n) => [n.id, n]));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  let g = `<defs><marker id="lp-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#5b6b84"/></marker></defs>`;
  for (const e of EDGES) {
    g += `<path class="edge${e.from !== "agent" ? " flow" : ""}" data-from="${e.from}" data-to="${e.to}" d="${e.d}" marker-end="url(#lp-arrow)"/>`;
    if (e.label) g += `<text class="elabel" x="${e.label[1]}" y="${e.label[2]}">${esc(e.label[0])}</text>`;
    if (e.label2) g += `<text class="elabel" x="${e.label2[1]}" y="${e.label2[2]}">${esc(e.label2[0])}</text>`;
  }
  // The packet runs the loop scan → patch → verify → attacker → scan, behind the boxes.
  g += `<path id="lp-route" d="M296 86H866V276H296V86" fill="none" stroke="none"/>
    <circle class="packet" r="5"><animateMotion dur="7s" repeatCount="indefinite" rotate="auto"><mpath href="#lp-route"/></animateMotion></circle>`;
  for (const n of NODES) {
    g += `<g class="node ${n.kind}" data-id="${n.id}" tabindex="0" role="button" aria-label="${esc(`${n.n ? "Step " + n.n + ": " : ""}${n.title}`)}">
      <rect x="${n.x}" y="${n.y}" width="${W}" height="${H}" rx="12"/>
      ${n.n ? `<text class="n" x="${n.x + W - 16}" y="${n.y + 22}" text-anchor="end">${n.n}</text>` : ""}
      <text class="t" x="${n.x + 16}" y="${n.y + 30}">${esc(n.title)}</text>
      <text class="b" x="${n.x + 16}" y="${n.y + 56}">${esc(n.lines[0])}</text>
      <text class="b" x="${n.x + 16}" y="${n.y + 74}">${esc(n.lines[1])}</text>
    </g>`;
  }
  svg.innerHTML = g;

  function select(id, prev) {
    const n = byId[id];
    svg.querySelectorAll(".node").forEach((el) => el.classList.toggle("sel", el.dataset.id === id));
    svg.querySelectorAll(".edge").forEach((el) => el.classList.toggle("hot", !!prev && el.dataset.from === prev && el.dataset.to === id));
    const whoCls = n.kind === "doc" ? "doc" : n.kind === "atk" ? "atk" : "";
    detail.innerHTML = `<span class="d-step">${n.n ? "Step " + n.n : "Start"}</span>
      <h3>${esc(n.title)}<span class="who ${whoCls}">${esc(n.who)}</span></h3>
      <p>${esc(n.text)}</p>`;
  }

  let timer = null, pos = 0;
  function stopWalk() { clearInterval(timer); timer = null; playBtn.textContent = "▶ Walk me through it"; }
  function walk() {
    if (timer) return stopWalk();
    pos = 0;
    select(ORDER[0]);
    playBtn.textContent = "❚❚ Stop";
    timer = setInterval(() => {
      pos += 1;
      if (pos >= ORDER.length) return stopWalk();
      select(ORDER[pos], ORDER[pos - 1]);
    }, 2200);
  }

  svg.addEventListener("click", (e) => {
    const node = e.target.closest(".node");
    if (node) { stopWalk(); select(node.dataset.id); }
  });
  svg.addEventListener("keydown", (e) => {
    const node = e.target.closest(".node");
    if (node && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); stopWalk(); select(node.dataset.id); }
  });
  playBtn.addEventListener("click", walk);
  select("doctor");
})();
