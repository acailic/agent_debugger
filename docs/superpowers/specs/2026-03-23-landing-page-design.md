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
- **Badges:** CI status, PyPI versions, Python 3.10+, License, Downloads

### 2. Why Peaky Peek
- 3-column grid cards: **Local-first** | **Agent-decision-aware** | **Interactive Replay**
- Comparison table (LangSmith / OpenTelemetry / Sentry / Peaky Peek)

### 3. Feature Highlights
- 4 features in a 2×2 grid with screenshot thumbnails:
  1. Decision Tree Visualization → `screenshot-decision-tree.png`
  2. Checkpoint Replay → `screenshot-checkpoint-state.png`
  3. Trace Search → `screenshot-search.png`
  4. Failure Clustering → `screenshot-failure-cluster.png`

### 4. Quick Install
- 2-step code block (pip install + uvicorn run)
- Link to full docs

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
- No JavaScript required (copy-to-clipboard is the only optional JS enhancement)

---

## Performance Targets

- No external CDN dependencies (no Tailwind, no Google Fonts)
- Page weight < 100KB HTML+CSS (screenshots lazy-loaded)
- Lighthouse score target: 95+ performance, 100 accessibility

---

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

---

## Success Criteria

- Page loads and renders correctly on desktop and mobile
- `pip install` command is clearly visible and copyable above the fold
- All existing `docs/assets/` screenshots load correctly
- GitHub Pages deployment succeeds with no build errors
