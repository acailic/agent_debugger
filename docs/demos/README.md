# Demo Recording Guide

This guide provides step-by-step instructions for recording the 6 feature demo GIFs for Peaky Peek.

## Prerequisites

1. **Seed demo data:**
   ```bash
   python scripts/seed_demo_sessions.py
   ```

2. **Start the backend:**
   ```bash
   uvicorn api.main:app --reload --port 8000
   ```

3. **Start the frontend:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. **Open:** http://localhost:5173

## GIF Recording Tools

- **macOS:** [Kap](https://getkap.co/), [GIPHY Capture](https://giphy.com/apps/giphycapture)
- **Linux:** [Peek](https://github.com/phw/peek), [Byzanz](https://github.com/GNOME/byzanz)
- **Windows:** [ScreenToGif](https://www.screentogif.com/)

**Target specs:**
- Resolution: 1280x720 or 800x600 (be consistent)
- Frame rate: 15fps
- Max file size: ~2MB per GIF

---

## Demo 1: Decision Tree (`decision-tree.gif`)

**Duration:** 10-12 seconds

**What it shows:** Interactive navigation of agent reasoning as a tree structure.

### Setup
- Ensure seeded sessions exist
- Open the UI at http://localhost:5173

### Recording Steps
1. Click on a session in the left sidebar (e.g., "multi_step_agent")
2. Wait for the decision tree to render in the center panel
3. **Pan:** Click and drag the tree to show different areas
4. **Zoom:** Use the +/- buttons or Ctrl+scroll to zoom in/out
5. **Click a node:** Click on an orange (decision) or green (tool) node
6. **Inspect:** Show the event details panel updating on the right
7. **Double-click:** Double-click a node with children to collapse/expand

### Tips
- Start with a full tree view, then zoom in
- Choose a session with a visible tree structure (not too flat)
- Show the legend at the top of the tree panel

---

## Demo 2: Session Replay (`session-replay.gif`)

**Duration:** 12-15 seconds

**What it shows:** Time-travel debugging with checkpoint-aware playback controls.

### Setup
- Select a session with multiple events
- Locate the "Replay Controls" panel near the bottom

### Recording Steps
1. **Click the Play button** (▶) to start auto-playback
2. Let it run for 2-3 events
3. **Click Pause** (⏸) to stop
4. **Click Step Forward** (⏭) to advance one event
5. **Click Step Backward** (⏮) to go back one event
6. **Drag the timeline slider** to seek to a specific point
7. **Change speed** using the dropdown (0.5x, 1x, 2x, 5x)

### Tips
- Show the timeline markers (checkpoints, decisions, errors)
- Demonstrate keyboard shortcuts if comfortable (Space, Arrow keys)
- Highlight the event counter (e.g., "5 / 23")

---

## Demo 3: Trace Search (`trace-search.gif`)

**Duration:** 8-10 seconds

**What it shows:** Finding specific events across sessions using keyword search.

### Setup
- Locate the "Trace Search" panel on the right sidebar
- Ensure you have multiple sessions with varied content

### Recording Steps
1. Click the search input field
2. **Type a query** (e.g., "weather", "error", "tool")
3. **Click Search** or press Enter
4. **Show results appearing** in the list below
5. **Click a result** to jump to that event in the session
6. **Show the session switching** if result is from another session

### Tips
- Use a query that returns results from multiple sessions
- Show the event type filter dropdown
- Demonstrate "Current session" vs "All sessions" scope toggle

---

## Demo 4: Live Streaming (`live-streaming.gif`)

**Duration:** 10-12 seconds

**What it shows:** Real-time SSE events appearing as an agent runs.

### Setup
- Keep the backend running
- You'll need to trigger an agent while recording

### Recording Steps
1. **Select a session** in the sidebar
2. **Run a simple agent script** that generates events:
   ```python
   # In a separate terminal, run a quick agent
   python -c "
   import asyncio
   from agent_debugger_sdk import TraceContext, init
   init()
   async def demo():
       async with TraceContext(agent_name='live_demo', framework='custom') as ctx:
           await ctx.record_decision('Step 1', 0.9, 'action_a', [])
           await asyncio.sleep(0.5)
           await ctx.record_tool_call('demo_tool', {'input': 'test'})
           await asyncio.sleep(0.5)
           await ctx.record_tool_result('demo_tool', {'output': 'done'}, 100)
   asyncio.run(demo())
   "
   ```
3. **Show events appearing** in the Live Summary panel
4. **Highlight the connection indicator** turning green

### Tips
- Position the Live Summary panel clearly in frame
- Show the "Connected" status badge
- Time the recording with the agent execution

---

## Demo 5: Failure Clustering (`failure-clustering.gif`)

**Duration:** 8-10 seconds

**What it shows:** Clicking a failure cluster to jump to the root cause.

### Setup
- Use a session that has failures (seeded error scenarios)
- Locate the "Adaptive Intelligence" / "Representative failures" panel

### Recording Steps
1. **Find the failure clusters** in the analysis ribbon
2. **Click on a cluster pill** (shows fingerprint + count)
3. **Watch the view jump** to the representative failure event
4. **Show the event details** panel updating with the failure info

### Tips
- Choose a cluster with a clear failure type
- Show the fingerprint label (e.g., "tool_timeout", "low_confidence")
- Highlight the count showing how many similar failures exist

---

## Demo 6: Session Comparison (`session-comparison.gif`)

**Duration:** 10-12 seconds

**What it shows:** Side-by-side comparison of two agent runs.

### Setup
- Have at least 2 sessions available
- Locate the Session Comparison panel

### Recording Steps
1. **Click "Compare with another session"** (or similar UI element)
2. **Select a second session** from the dropdown or list
3. **Show the side-by-side view** appearing
4. **Highlight differences** in events, decisions, or outcomes
5. **Click on a differing event** to inspect details

### Tips
- Compare two sessions with different outcomes (one success, one failure)
- Show clear visual differences in the comparison
- Demonstrate clicking through to event details

---

## After Recording

1. **Save each GIF** to this `docs/demos/` folder with the correct filename
2. **Verify file sizes** are under 2MB
3. **Test in README** - the GIFs should be embedded and render correctly

## File Checklist

- [ ] `decision-tree.gif`
- [ ] `session-replay.gif`
- [ ] `trace-search.gif`
- [ ] `live-streaming.gif`
- [ ] `failure-clustering.gif`
- [ ] `session-comparison.gif`