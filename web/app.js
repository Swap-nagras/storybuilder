// ChatGPT-style client. Streams pipeline events from /story (SSE) and renders
// them as a live trace inside the assistant bubble, then the final story.

const chat = document.getElementById("chat");
const form = document.getElementById("composer");
const promptEl = document.getElementById("prompt");
const sendBtn = document.getElementById("send");
const resetBtn = document.getElementById("reset");

// Per-session state.
let priorSpec = null;       // null until a story has been produced
let priorRequest = null;    // the original user_input that produced priorSpec
let inFlight = false;

resetBtn.addEventListener("click", () => {
  priorSpec = null;
  priorRequest = null;
  chat.innerHTML = "";
  promptEl.placeholder = "What kind of story would you like? (e.g. Alice and her cat Bob)";
  promptEl.focus();
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (inFlight) return;
  const text = promptEl.value.trim();
  if (!text) return;
  promptEl.value = "";

  addUserMessage(text);
  const assistant = addAssistantShell();
  inFlight = true;
  sendBtn.disabled = true;

  // If we already have a priorSpec, this is a revision request; otherwise it's a new story.
  const body = priorSpec
    ? { user_input: priorRequest, prior_spec: priorSpec, revision_note: text }
    : { user_input: text };

  try {
    await streamStory(body, assistant);
  } catch (err) {
    assistant.story.textContent = "Sorry, something went wrong: " + err.message;
    assistant.bubble.classList.add("refusal");
  } finally {
    inFlight = false;
    sendBtn.disabled = false;
    promptEl.focus();
  }
});

function addUserMessage(text) {
  const div = document.createElement("div");
  div.className = "msg user";
  div.textContent = text;
  chat.appendChild(div);
  scrollToBottom();
}

function addAssistantShell() {
  const bubble = document.createElement("div");
  bubble.className = "msg assistant";

  const trace = document.createElement("details");
  trace.className = "trace";
  trace.open = true;
  const summary = document.createElement("summary");
  summary.textContent = "Pipeline (live)";
  trace.appendChild(summary);

  const story = document.createElement("div");
  story.className = "story";

  bubble.appendChild(trace);
  bubble.appendChild(story);
  chat.appendChild(bubble);
  scrollToBottom();
  return { bubble, trace, summary, story };
}

function traceRow(trace, icon, body, cls) {
  const row = document.createElement("div");
  row.className = "row" + (cls ? " " + cls : "");
  const i = document.createElement("span");
  i.className = "icon";
  i.textContent = icon;
  const b = document.createElement("span");
  b.className = "body";
  b.textContent = body;
  row.appendChild(i);
  row.appendChild(b);
  trace.appendChild(row);
  scrollToBottom();
  return row;
}

async function streamStory(body, ui) {
  const resp = await fetch("/story", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    throw new Error("HTTP " + resp.status);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE frames separated by \n\n
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (frame.startsWith("data:")) {
        const json = frame.slice(5).trim();
        try {
          handleEvent(JSON.parse(json), ui);
        } catch (e) {
          console.warn("bad SSE frame", json, e);
        }
      }
    }
  }
}

function handleEvent(ev, ui) {
  const { type, payload } = ev;
  if (type === "safety_in") {
    const label = payload.revision ? "revision" : "input";
    if (payload.status === "running") {
      traceRow(ui.trace, "🛡", `Safety check (${label}): running …`);
    } else {
      const cls = payload.allow ? "pass" : "fail";
      traceRow(ui.trace, "🛡",
        `Safety check (${label}): ` +
        (payload.allow ? "ALLOWED" : "REFUSED") + " — " + payload.reason, cls);
    }
  } else if (type === "spec") {
    if (payload.status === "running") {
      traceRow(ui.trace, "✏️", "Prompt engineer: planning …");
    } else if (payload.status === "reused") {
      traceRow(ui.trace, "✏️", "Reusing prior spec. " + (payload.note || ""));
    } else {
      const s = payload.spec || {};
      traceRow(ui.trace, "✏️",
        `Prompt engineer → category=${s.category}, arc=${s.arc}, vocab=${s.vocab_band}, target=${s.target_words}w`);
    }
  } else if (type === "storyteller") {
    if (payload.status === "running") {
      traceRow(ui.trace, "📖",
        `Storyteller (iter ${payload.iteration}/${payload.max}): writing …`);
    } else {
      traceRow(ui.trace, "📖",
        `Storyteller (iter ${payload.iteration}): wrote ${payload.words} words`);
    }
  } else if (type === "evaluator") {
    if (payload.status === "running") {
      traceRow(ui.trace, "⚖️", `Evaluator (iter ${payload.iteration}): judging …`);
    } else {
      const cls = payload.passed ? "pass" : "warn";
      const row = traceRow(ui.trace, "⚖️",
        `Evaluator (iter ${payload.iteration}): ${payload.passed ? "PASS" : "retry"} — score ${payload.score}`,
        cls);
      const scores = document.createElement("div");
      scores.className = "scores";
      scores.textContent =
        `   safety=${payload.safety} age=${payload.age_fit} arc=${payload.arc_quality} ` +
        `engage=${payload.engagement} vocab=${payload.vocab_fit} length=${payload.length_fit}`;
      row.appendChild(scores);
      (payload.issues || []).forEach((i) => {
        const div = document.createElement("div");
        div.className = "issue";
        div.textContent = "• " + i;
        ui.trace.appendChild(div);
      });
    }
  } else if (type === "safety_out") {
    if (payload.status === "running") {
      traceRow(ui.trace, "🛡", "Final safety re-check: running …");
    } else {
      const cls = payload.allow ? "pass" : "fail";
      traceRow(ui.trace, "🛡",
        "Final safety re-check: " + (payload.allow ? "OK" : "BLOCKED") + " — " + payload.reason,
        cls);
    }
  } else if (type === "story") {
    const text = payload.text || "";
    ui.story.textContent = text;
    const score = document.createElement("span");
    score.className = "final-score";
    score.textContent = "final score: " + payload.final_score;
    ui.story.appendChild(score);
    // Save spec for revisions; collapse trace.
    priorSpec = payload.spec;
    priorRequest = priorRequest ?? promptEl.dataset.lastRequest ?? null;
    if (!priorRequest) {
      // first story: the user's typed text is the original request
      const userBubbles = chat.querySelectorAll(".msg.user");
      if (userBubbles.length) priorRequest = userBubbles[0].textContent;
    }
    ui.trace.open = false;
    promptEl.placeholder = "Want any changes? (e.g. shorter, more dragons)  ‒ or click 'New story'";
  } else if (type === "refusal") {
    ui.bubble.classList.add("refusal");
    ui.story.textContent = payload.reason;
    ui.trace.open = false;
    // On refusal of a *new* request, do not stash a spec.
    if (!priorSpec) {
      priorRequest = null;
    }
  } else if (type === "error") {
    ui.bubble.classList.add("refusal");
    ui.story.textContent = "Internal error: " + (payload.message || "?");
    ui.trace.open = false;
  }
  scrollToBottom();
}

function scrollToBottom() {
  chat.scrollTop = chat.scrollHeight;
}
