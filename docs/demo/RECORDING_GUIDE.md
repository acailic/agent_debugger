# Demo Recording Guide

Five short demos that together cover all key features. Each is 20-45 seconds.
Record them separately and use the best take of each.

## Setup (do once before recording anything)

```bash
# 1. Install
make install

# 2. Seed benchmark sessions + start everything
make demo-setup      # seeds data and prints next steps

# Terminal 1
make server          # FastAPI → http://localhost:8000

# Terminal 2
make frontend        # React UI → http://localhost:5173
```

Open http://localhost:5173 and confirm you see 8 sessions in the sidebar.

**Recommended screen recorder:**
- Linux: `peek` or `vhs`
- Mac: `Kap` (free) or QuickTime
- Windows: `LICEcap` or ShareX

Target: 1080p, 15-30fps, output as GIF or MP4.

---

## Demo 1 — Live Streaming (40s)

**What it shows:** Events appearing in the timeline in real time as an agent runs.

**Setup:**
1. Open http://localhost:5173 — you're on the session list
2. In a second terminal, run: `make demo-live`
3. Start recording just before running the command

**What to capture:**
- Session list — watch new sessions appear as each ticket processes
- Click into the first session mid-run — see events populating the timeline
- Scroll through the timeline as the tool calls and decisions arrive

**Save as:** `docs/assets/demo-live-stream.gif`

---

## Demo 2 — Decision Tree + Event Inspection (45s)

**What it shows:** Navigating a session's decision tree, clicking nodes, inspecting evidence.

**Best session:** `seed-safety-escalation` (rich tree: policy → LLM → tool → safety checks → refusal)

**Steps:**
1. Open http://localhost:5173
2. Click on `seed-safety-escalation`
3. Switch to the **Decision Tree** tab
4. Click on the decision node ("block" decision)
5. In the right panel: show Evidence, Alternatives, Upstream Events
6. Click one of the upstream event links to jump to the tool call

**What to capture:**
- The tree layout with all nodes visible
- The detail panel opening on click
- Navigating between linked events

**Save as:** `docs/assets/demo-decision-tree.gif`

---

## Demo 3 — Checkpoint Replay (30s)

**What it shows:** Rewinding to a saved checkpoint and replaying forward from that state.

**Best session:** `seed-safety-escalation` (has a checkpoint at the approval gate failure)
or run `make demo-safety` (creates a richer checkpoint at the same moment).

**Steps:**
1. Open the session in the UI
2. Switch to the **Replay** tab
3. Show the checkpoint list — one checkpoint at phase `guard-escalation`
4. Click **Replay from checkpoint**
5. Step through events forward from the checkpoint

**What to capture:**
- The checkpoint panel with state snapshot visible
- Clicking replay and seeing the event cursor advance
- The state panel updating as you step through

**Save as:** `docs/assets/demo-checkpoint-replay.gif`

---

## Demo 4 — Safety Audit (35s)

**What it shows:** The full safety trail — policy check → tool guard → block → policy violation → refusal.

**Setup:** Run `make demo-safety` first to create the three safety sessions.

**Steps:**
1. Open http://localhost:5173
2. Pick the **destructive tool** session (agent: `data_management_agent`)
3. In the Timeline, use the event type filter — select **Safety checks**
4. Show the warn → block escalation
5. Switch filter to **Policy violations**
6. Then **Refusals** — show the safe alternative suggestion

**What to capture:**
- Filtering the timeline by event type
- The safety check detail: outcome, risk level, rationale
- The refusal detail: blocked action + safe alternative

**Save as:** `docs/assets/demo-safety-audit.gif`

---

## Demo 5 — Cross-Session Search (25s)

**What it shows:** Searching for events across all sessions by keyword and event type.

**Steps:**
1. Open http://localhost:5173
2. Click the **Search** view or use the search box
3. Type `blocked` — see results across multiple sessions
4. Filter by event type: **Refusals**
5. Click a result to jump directly to that event in its session

**What to capture:**
- Results populating across sessions in real time
- The event type filter narrowing results
- Clicking a result and landing in the correct session + event

**Save as:** `docs/assets/demo-search.gif`

---

## Adding GIFs to the README

Once recorded, uncomment the demo GIF line in `README.md`:

```markdown
<!-- TODO: Record demo GIF showing decision tree view → checkpoint replay → search -->
<!-- ![Demo](./docs/demo.gif) -->
```

Replace with:

```markdown
![Live Stream Demo](./docs/assets/demo-live-stream.gif)
```

Or use an animated collage tool to combine all five into one `demo.gif`.

---

## Tips for Clean Recordings

- Use a dark terminal theme (Dracula or Nord) — easier to read in GIF
- Set browser zoom to 90% so more UI fits in the recording area
- Seed fresh data right before recording: `make demo-seed`
- Pause 1-2 seconds on each interesting detail so viewers can read it
- Keep recordings under 45 seconds — attention drops fast
