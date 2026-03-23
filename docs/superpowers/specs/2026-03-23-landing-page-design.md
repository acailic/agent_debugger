# Landing Page Design — GitHub Pages

**Date:** 2026-03-23
**Product:** Peaky Peek (`peaky-peek` / `peaky-peek-server`)
**Repo:** https://github.com/acailic/agent_debugger
**Author assumption:** Senior FE Architect, maximum ROI, minimum maintenance

---

## Goal

A single static marketing/landing page hosted on GitHub Pages that converts developer visitors into installers and GitHub stars. No framework, no build step, no CI overhead.

---

## Approach

**Pure static HTML + CSS in `docs/` folder on `main` branch.**

- Enable GitHub Pages → Source: `docs/` folder in repo settings
- No Jekyll, no Vite, no Node dependencies
- Single `docs/index.html` + `docs/style.css`
- Re-uses existing screenshots from `docs/assets/`

---

## Architecture

```
docs/
  index.html       ← single page, all content
  style.css        ← hand-written, CSS variables, dark theme
  assets/          ← existing screenshots (already present)
```

No build pipeline. No `gh-pages` branch. No workflow changes needed.

---

## Page Sections

### 1. Hero
- **Headline:** "Debug AI agents like distributed systems — not black boxes."
- **Subheadline:** "Capture every decision, tool call, and LLM interaction as a queryable event timeline. Inspect live, replay from checkpoints, search across sessions."
- **Primary CTA:** Copyable `pip install peaky-peek-server` code block
- **Secondary CTA:** GitHub link with stars badge
- **Badges** (shields.io, use as `<img>` tags):
  - CI: `https://github.com/acailic/agent_debugger/actions/workflows/ci.yml/badge.svg`
  - PyPI peaky-peek: `https://img.shields.io/pypi/v/peaky-peek.svg?label=peaky-peek`
  - PyPI peaky-peek-server: `https://img.shields.io/pypi/v/peaky-peek-server.svg?label=peaky-peek-server`
  - Python: `https://img.shields.io/badge/python-3.10%2B-blue.svg`
  - License: `https://img.shields.io/badge/License-MIT-green.svg`
  - Downloads: `https://img.shields.io/pypi/dm/peaky-peek`

### 2. Why Peaky Peek
- 3-column grid cards: **Local-first** | **Agent-decision-aware** | **Interactive Replay**
- Comparison table — columns: Tool | Focus | Limitation:

| Tool | Focus | Limitation |
|------|-------|------------|
| LangSmith | LLM tracing | SaaS-first, no local-first option |
| OpenTelemetry | Infra observability | Not agent-decision-aware |
| Sentry | Error tracking | No reasoning-level insight |
| **Peaky Peek** | Agent-native debugging | **Local-first, open source** |

### 3. Feature Highlights
- 4 features in a 2×2 grid with screenshot thumbnails:
  1. Decision Tree Visualization → `assets/screenshot-decision-tree.png`
  2. Checkpoint Replay → `assets/screenshot-checkpoint-replay.png`
  3. Trace Search → `assets/screenshot-search.png`
  4. Failure Clustering → `assets/screenshot-failure-cluster.png`

**Unused screenshots** (present in `docs/assets/` but not displayed on the landing page):
`screenshot-checkpoint-state.png`, `screenshot-full-ui.png`, `screenshot-loop-detection.png`,
`screenshot-multi-agent-coord.png`, `screenshot-multi-agent.png`, `screenshot-refusal-detail.png`,
`screenshot-safety-session.png`, `screenshot-session-comparison.png`, `screenshot-session-list.png`,
`screenshot-timeline.png`, `screenshot-tool-inspector.png`

### 4. Quick Install
Exact commands to display (verbatim):
```
pip install peaky-peek-server
uvicorn api.main:app --reload --port 8000
```
Followed by a link to full docs at `https://github.com/acailic/agent_debugger/blob/main/docs/README.md`.

### 5. Footer
- Links: GitHub · Docs · Contributing · License · PyPI (peaky-peek) · PyPI (peaky-peek-server)
- MIT license notice

---

## Design System

| Token | Value |
|---|---|
| Background | `#0d1117` (GitHub dark) |
| Surface | `#161b22` |
| Border | `#30363d` |
| Accent | `#58a6ff` (blue) |
| Text primary | `#e6edf3` |
| Text muted | `#8b949e` |
| Code background | `#1f2428` |
| Font (body) | `system-ui, -apple-system, sans-serif` |
| Font (code) | `ui-monospace, SFMono-Regular, monospace` |

**Rationale:** Mirrors GitHub's own dark palette — familiar to the target audience, zero external font requests.

---

## Responsiveness

- Mobile-first CSS grid
- Single column on `< 768px`, multi-column above
- No JavaScript required. Copy-to-clipboard is the only optional JS enhancement: show a "Copy" button on the install code block that uses `navigator.clipboard.writeText()`. If JS is unavailable or fails, the `<pre><code>` block remains fully selectable — no fallback UI needed.

---

## Performance Targets

- No external CDN dependencies (no Tailwind, no Google Fonts)
- Page weight < 100KB HTML+CSS (screenshots lazy-loaded)
- Lighthouse score target: 95+ performance, 100 accessibility

---

## Required `<meta>` Tags

```html
<meta name="description" content="Debug AI agents like distributed systems. Capture decisions, tool calls, and LLM interactions as a queryable event timeline.">
<meta property="og:title" content="Peaky Peek — Agent Debugger">
<meta property="og:description" content="Local-first AI agent debugger. Inspect live, replay from checkpoints, search across sessions.">
<meta property="og:url" content="https://acailic.github.io/agent_debugger/">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
```

## Out of Scope

- Blog / docs site (that would justify Jekyll or a static site generator)
- Dark/light toggle
- Animations beyond CSS transitions
- Analytics (can be added later as a 1-line script tag)

---

## GitHub Pages Setup (one-time)

1. Push `docs/index.html` and `docs/style.css` to `main`
2. In repo Settings → Pages → Source: `Deploy from branch` → Branch: `main` → Folder: `/docs`
3. Page will be live at `https://acailic.github.io/agent_debugger/`

**IMPORTANT — Relative paths required:** GitHub Pages serves this site from the subpath `/agent_debugger/`, not the domain root. All asset, CSS, and link references in `index.html` must use **relative paths**:
- `href="style.css"` ✅ — not `href="/style.css"` ✗
- `src="assets/screenshot-decision-tree.png"` ✅ — not `src="/assets/..."` ✗

**Pre-existing `docs/` content:** The `docs/` folder contains existing markdown files (`README.md`, `architecture.md`, `integration.md`, `progress.md`, etc.) and subdirectories (`decisions/`, `papers/`, `superpowers/`, `demos/`). These will be publicly accessible via GitHub Pages URLs. This is acceptable — they are project documentation, not sensitive. No action required. A `docs/.nojekyll` file should be added to prevent Jekyll from processing the folder.

---

## Success Criteria

- Page loads and renders correctly on desktop and mobile
- `pip install` command is clearly visible and copyable above the fold
- All existing `docs/assets/` screenshots load correctly
- GitHub Pages deployment succeeds with no build errors
