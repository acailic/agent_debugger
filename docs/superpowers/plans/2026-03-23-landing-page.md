# Landing Page (GitHub Pages) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a single static HTML/CSS landing page at `docs/index.html` that is immediately servable via GitHub Pages with zero build steps.

**Architecture:** Pure static files (`index.html` + `style.css` + `.nojekyll`) placed in `docs/` on `main` branch. GitHub Pages serves them directly from that folder. All asset references use relative paths because GitHub Pages serves the site from the `/agent_debugger/` subpath, not the domain root.

**Tech Stack:** HTML5, hand-written CSS3 (CSS custom properties + grid + flexbox), one inline `<script>` for copy-to-clipboard. No frameworks, no build tools, no CDN dependencies.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `docs/.nojekyll` | Create (empty) | Prevents GitHub Pages from running Jekyll on the `docs/` folder |
| `docs/style.css` | Create | All styles: design tokens, reset, layout, components |
| `docs/index.html` | Create | Full page HTML with all five sections + meta tags |

`docs/assets/` — already present, read-only. Use relative path `assets/<filename>`.

---

## CSS Class Contract (shared between Tasks 1 and 2)

The following class names are used in `index.html` and must be defined in `style.css`:

```
/* Layout */
.container          max-width wrapper (1100px, auto margin)
.section            section padding (80px top/bottom)
.section--alt       alternate background (#161b22) for visual rhythm

/* Hero */
.hero               full-width hero section
.hero__headline     h1 — large display text
.hero__sub          subheadline paragraph
.hero__cta          flex row — install block + GitHub button
.hero__badges       flex row of shield.io badge images
.install-block      dark code block with copy button
.install-block__pre <pre><code> inside
.copy-btn           copy-to-clipboard button (top-right corner of install-block)
.btn                base button styles
.btn--primary       accent-colored filled button
.btn--outline       bordered outline button

/* Why section */
.why-grid           3-column responsive grid
.why-card           individual pillar card
.why-card__icon     large emoji/icon above title
.why-card__title    card heading
.why-card__body     card body text
.compare-table      full-width comparison table
.compare-table thead th  header cells
.compare-table--highlight  row for Peaky Peek (accent color)

/* Features */
.features-grid      2×2 responsive grid
.feature-card       individual feature card
.feature-card__img  screenshot thumbnail (lazy-loaded, full-width)
.feature-card__title feature title
.feature-card__body  feature description

/* Quick Install */
.install-steps      two code blocks stacked with a label above each

/* Footer */
.footer             footer wrapper
.footer__links      flex row of footer links
.footer__legal      small muted copyright line
```

---

## Task 1 — Scaffold + CSS

**Files:**
- Create: `docs/.nojekyll` (empty)
- Create: `docs/style.css`

### CSS Design Tokens (write these as `:root` vars at the top)

```css
:root {
  --bg:          #0d1117;
  --surface:     #161b22;
  --border:      #30363d;
  --accent:      #58a6ff;
  --accent-hover:#79b8ff;
  --text:        #e6edf3;
  --muted:       #8b949e;
  --code-bg:     #1f2428;
  --font-sans:   system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono:   ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace;
  --radius:      6px;
  --max-w:       1100px;
}
```

- [ ] **Step 1: Create `.nojekyll`**

Create `docs/.nojekyll` as a completely empty file (zero bytes).

- [ ] **Step 2: Write `style.css` — reset + base**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html { scroll-behavior: smooth; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-hover); text-decoration: underline; }

img { display: block; max-width: 100%; height: auto; }

code, pre { font-family: var(--font-mono); }
```

- [ ] **Step 3: Write layout utilities**

```css
.container {
  max-width: var(--max-w);
  margin: 0 auto;
  padding: 0 24px;
}

.section {
  padding: 80px 0;
}

.section--alt {
  background: var(--surface);
}

.section__title {
  font-size: clamp(1.5rem, 3vw, 2rem);
  font-weight: 700;
  margin-bottom: 12px;
  text-align: center;
}

.section__sub {
  color: var(--muted);
  text-align: center;
  margin-bottom: 48px;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
}
```

- [ ] **Step 4: Write hero styles**

```css
.hero {
  padding: 96px 0 80px;
  text-align: center;
  border-bottom: 1px solid var(--border);
}

.hero__headline {
  font-size: clamp(1.8rem, 4vw, 2.8rem);
  font-weight: 800;
  line-height: 1.2;
  margin-bottom: 20px;
  letter-spacing: -0.02em;
}

.hero__sub {
  color: var(--muted);
  font-size: 1.125rem;
  max-width: 640px;
  margin: 0 auto 36px;
}

.hero__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-bottom: 36px;
}

.hero__badges img { height: 20px; }

.hero__cta {
  display: flex;
  gap: 16px;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: var(--radius);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  text-decoration: none;
}

.btn--primary {
  background: var(--accent);
  color: #0d1117;
  border: 1px solid var(--accent);
}

.btn--primary:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
  color: #0d1117;
  text-decoration: none;
}

.btn--outline {
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border);
}

.btn--outline:hover {
  border-color: var(--accent);
  color: var(--accent);
  text-decoration: none;
}

.install-block {
  position: relative;
  display: inline-block;
  text-align: left;
}

.install-block__pre {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 56px 14px 18px;
  font-size: 0.95rem;
  color: var(--text);
  white-space: pre;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--muted);
  font-size: 0.75rem;
  padding: 4px 8px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.copy-btn:hover { color: var(--text); border-color: var(--accent); }
.copy-btn.copied { color: #3fb950; border-color: #3fb950; }
```

- [ ] **Step 5: Write "Why Peaky Peek" styles**

```css
.why-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 24px;
  margin-bottom: 56px;
}

.why-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 28px 24px;
}

.why-card__icon { font-size: 2rem; margin-bottom: 12px; }
.why-card__title { font-size: 1rem; font-weight: 700; margin-bottom: 8px; }
.why-card__body { color: var(--muted); font-size: 0.9rem; line-height: 1.6; }

.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.compare-table th,
.compare-table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.compare-table thead th {
  background: var(--surface);
  color: var(--muted);
  font-weight: 600;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.compare-table tbody tr:last-child td { border-bottom: none; }

.compare-table--highlight td {
  background: #132034;
  color: var(--accent);
  font-weight: 600;
}
```

- [ ] **Step 6: Write features grid styles**

```css
.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 24px;
}

.feature-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: border-color 0.2s;
}

.feature-card:hover { border-color: var(--accent); }

.feature-card__img {
  width: 100%;
  aspect-ratio: 16/9;
  object-fit: cover;
  border-bottom: 1px solid var(--border);
}

.feature-card__body-wrap { padding: 20px; }

.feature-card__title {
  font-size: 0.95rem;
  font-weight: 700;
  margin-bottom: 6px;
}

.feature-card__body {
  color: var(--muted);
  font-size: 0.875rem;
  line-height: 1.5;
}
```

- [ ] **Step 7: Write quick-install section styles**

```css
.install-steps {
  max-width: 640px;
  margin: 0 auto;
}

.install-steps__label {
  color: var(--muted);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
  margin-top: 20px;
}

.install-steps__label:first-child { margin-top: 0; }

.install-steps pre {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  font-size: 0.9rem;
  color: var(--text);
  overflow-x: auto;
}

.install-steps__note {
  color: var(--muted);
  font-size: 0.85rem;
  margin-top: 24px;
  text-align: center;
}

.install-steps__note a { color: var(--accent); }
```

- [ ] **Step 8: Write footer styles**

```css
.footer {
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: 40px 0;
  text-align: center;
}

.footer__links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  justify-content: center;
  margin-bottom: 16px;
  font-size: 0.9rem;
}

.footer__links a { color: var(--muted); }
.footer__links a:hover { color: var(--text); text-decoration: none; }

.footer__legal {
  color: var(--muted);
  font-size: 0.8rem;
}
```

- [ ] **Step 9: Write responsive overrides**

```css
@media (max-width: 767px) {
  .section { padding: 56px 0; }
  .hero { padding: 64px 0 56px; }
  .why-grid { grid-template-columns: 1fr; }
  .features-grid { grid-template-columns: 1fr; }
  .hero__cta { flex-direction: column; align-items: stretch; }
  .btn { justify-content: center; }
  /* NOTE: Hides the "Limitation/Status" column on mobile — intentional trade-off.
     The Peaky Peek highlight row uses this column for positive copy ("✓ Local-first & open source"),
     so hiding it on mobile loses some impact. Accepted: keeps the table readable on small screens. */
  .compare-table th:last-child,
  .compare-table td:last-child { display: none; }
}
```

- [ ] **Step 10: Verify CSS file is syntactically valid**

The brace-count check below is a heuristic only — it will not catch all syntax errors:

```bash
open=$(grep -c '{' docs/style.css); close=$(grep -c '}' docs/style.css); echo "open=$open close=$close"; [ "$open" -eq "$close" ] && echo "brace count OK" || echo "MISMATCH — check CSS"
```

If counts match, also do a quick Python parse check (catches encoding and obvious structural errors):

```bash
python3 -c "
import re
css = open('docs/style.css').read()
opens = css.count('{')
closes = css.count('}')
assert opens == closes, f'Brace mismatch: {opens} open vs {closes} close'
print(f'CSS OK — {len(css)} bytes, {opens} rule blocks')
"
```

If either check fails, open `docs/style.css`, locate the mismatched block, and fix it before committing.

- [ ] **Step 11: Commit scaffolding**

```bash
git add docs/.nojekyll docs/style.css
git commit --author="acailic <acailic@users.noreply.github.com>" -m "feat: add landing page CSS and nojekyll scaffold"
```

---

## Task 2 — HTML Page

**Files:**
- Create: `docs/index.html`

**Depends on:** Task 1 CSS class names being defined (the class contract above applies).

- [ ] **Step 1: Write the `<head>` block**

Full `<head>` with charset, viewport, title, meta description, all OG/Twitter tags, and CSS link:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Peaky Peek — Agent Debugger</title>
  <meta name="description" content="Debug AI agents like distributed systems. Capture decisions, tool calls, and LLM interactions as a queryable event timeline.">
  <meta property="og:title" content="Peaky Peek — Agent Debugger">
  <meta property="og:description" content="Local-first AI agent debugger. Inspect live, replay from checkpoints, search across sessions.">
  <meta property="og:url" content="https://acailic.github.io/agent_debugger/">
  <meta property="og:type" content="website">
  <meta property="og:image" content="https://acailic.github.io/agent_debugger/assets/screenshot-full-ui.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:image" content="https://acailic.github.io/agent_debugger/assets/screenshot-full-ui.png">
  <link rel="stylesheet" href="style.css">
</head>
```

- [ ] **Step 2: Write the Hero section**

```html
<body>

<!-- HERO -->
<section class="hero">
  <div class="container">
    <h1 class="hero__headline">Debug AI agents like distributed systems<br>— not black boxes.</h1>
    <p class="hero__sub">Capture every decision, tool call, and LLM interaction as a queryable event timeline. Inspect live, replay from checkpoints, search across sessions.</p>

    <div class="hero__badges">
      <a href="https://github.com/acailic/agent_debugger/actions/workflows/ci.yml"><img src="https://github.com/acailic/agent_debugger/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
      <img src="https://img.shields.io/pypi/v/peaky-peek.svg?label=peaky-peek" alt="PyPI peaky-peek">
      <img src="https://img.shields.io/pypi/v/peaky-peek-server.svg?label=peaky-peek-server" alt="PyPI peaky-peek-server">
      <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
      <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License MIT">
      <img src="https://img.shields.io/pypi/dm/peaky-peek" alt="Downloads">
    </div>

    <div class="hero__cta">
      <div class="install-block">
        <pre class="install-block__pre"><code>pip install peaky-peek-server</code></pre>
        <button class="copy-btn" onclick="copyInstall(this)" aria-label="Copy install command">Copy</button>
      </div>
      <a href="https://github.com/acailic/agent_debugger" class="btn btn--outline">★ GitHub</a>
    </div>
  </div>
</section>
```

- [ ] **Step 3: Write the "Why Peaky Peek" section**

```html
<!-- WHY -->
<section class="section">
  <div class="container">
    <h2 class="section__title">Why Peaky Peek?</h2>
    <p class="section__sub">Traditional observability tools weren't built for agent-native debugging.</p>

    <div class="why-grid">
      <div class="why-card">
        <div class="why-card__icon">🏠</div>
        <div class="why-card__title">Local-first by default</div>
        <p class="why-card__body">No external telemetry. No SaaS lock-in. Your agent data stays on your machine unless you explicitly configure cloud mode.</p>
      </div>
      <div class="why-card">
        <div class="why-card__icon">🧠</div>
        <div class="why-card__title">Agent-decision-aware</div>
        <p class="why-card__body">Captures the causal chain behind every action — reasoning steps, confidence, evidence, and chosen action — not just function calls.</p>
      </div>
      <div class="why-card">
        <div class="why-card__icon">⏪</div>
        <div class="why-card__title">Interactive replay</div>
        <p class="why-card__body">Time-travel through any session. Play, pause, step, and seek to any checkpoint. Replay the exact state before a failure occurred.</p>
      </div>
    </div>

    <table class="compare-table">
      <thead>
        <tr>
          <th>Tool</th>
          <th>Focus</th>
          <th>Limitation</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>LangSmith</td>
          <td>LLM tracing</td>
          <td>SaaS-first, no local-first option</td>
        </tr>
        <tr>
          <td>OpenTelemetry</td>
          <td>Infra observability</td>
          <td>Not agent-decision-aware</td>
        </tr>
        <tr>
          <td>Sentry</td>
          <td>Error tracking</td>
          <td>No reasoning-level insight</td>
        </tr>
        <tr class="compare-table--highlight">
          <td><strong>Peaky Peek</strong></td>
          <td>Agent-native debugging</td>
          <td>✓ Local-first &amp; open source</td>
        </tr>
      </tbody>
    </table>
  </div>
</section>
```

- [ ] **Step 4: Write the Feature Highlights section**

```html
<!-- FEATURES -->
<section class="section section--alt">
  <div class="container">
    <h2 class="section__title">Feature Highlights</h2>
    <p class="section__sub">Everything you need to understand why your agent did what it did.</p>

    <div class="features-grid">
      <div class="feature-card">
        <img class="feature-card__img" src="assets/screenshot-decision-tree.png" alt="Decision Tree Visualization" loading="lazy">
        <div class="feature-card__body-wrap">
          <div class="feature-card__title">Decision Tree Visualization</div>
          <p class="feature-card__body">Navigate agent reasoning as an interactive tree. Click nodes to inspect events and trace the causal chain from policy to tool call.</p>
        </div>
      </div>
      <div class="feature-card">
        <img class="feature-card__img" src="assets/screenshot-checkpoint-replay.png" alt="Checkpoint Replay" loading="lazy">
        <div class="feature-card__body-wrap">
          <div class="feature-card__title">Checkpoint Replay</div>
          <p class="feature-card__body">Time-travel through agent execution. Play, pause, step, and seek to any point. Checkpoints ranked by restore value.</p>
        </div>
      </div>
      <div class="feature-card">
        <img class="feature-card__img" src="assets/screenshot-search.png" alt="Trace Search" loading="lazy">
        <div class="feature-card__body-wrap">
          <div class="feature-card__title">Trace Search</div>
          <p class="feature-card__body">Find specific events across all sessions. Search by keyword, filter by event type, and jump directly to results.</p>
        </div>
      </div>
      <div class="feature-card">
        <img class="feature-card__img" src="assets/screenshot-failure-cluster.png" alt="Failure Clustering" loading="lazy">
        <div class="feature-card__body-wrap">
          <div class="feature-card__title">Failure Clustering</div>
          <p class="feature-card__body">Adaptive analysis groups similar failures. Surface highest-severity, highest-novelty events. Click a cluster to focus the timeline.</p>
        </div>
      </div>
    </div>
  </div>
</section>
```

- [ ] **Step 5: Write the Quick Install section**

```html
<!-- QUICK INSTALL -->
<section class="section">
  <div class="container">
    <h2 class="section__title">Get Started in 2 Steps</h2>
    <p class="section__sub">Requires Python 3.10+ and a cloned repo. No config files needed to start.</p>

    <div class="install-steps">
      <p class="install-steps__label">Step 1 — Install</p>
      <pre><code>pip install peaky-peek-server</code></pre>

      <p class="install-steps__label">Step 2 — Run (from repo root after cloning)</p>
      <pre><code>git clone https://github.com/acailic/agent_debugger
cd agent_debugger
uvicorn api.main:app --reload --port 8000</code></pre>

      <p class="install-steps__note">
        API available at <code>http://localhost:8000</code> &middot;
        <a href="https://github.com/acailic/agent_debugger/blob/main/docs/README.md">Full documentation →</a>
      </p>
    </div>
  </div>
</section>
```

- [ ] **Step 6: Write the Footer and close the page**

```html
<!-- FOOTER -->
<footer class="footer">
  <div class="container">
    <nav class="footer__links" aria-label="Footer links">
      <a href="https://github.com/acailic/agent_debugger">GitHub</a>
      <a href="https://github.com/acailic/agent_debugger/blob/main/docs/README.md">Docs</a>
      <a href="https://github.com/acailic/agent_debugger/blob/main/CONTRIBUTING.md">Contributing</a>
      <a href="https://github.com/acailic/agent_debugger/blob/main/LICENSE">License</a>
      <a href="https://pypi.org/project/peaky-peek/">PyPI peaky-peek</a>
      <a href="https://pypi.org/project/peaky-peek-server/">PyPI peaky-peek-server</a>
    </nav>
    <p class="footer__legal">Released under the MIT License &middot; <a href="https://github.com/acailic/agent_debugger">acailic/agent_debugger</a></p>
  </div>
</footer>
```

- [ ] **Step 7: Write the copy-to-clipboard script and close `</body></html>`**

```html
<script>
function copyInstall(btn) {
  var text = btn.previousElementSibling.textContent.trim();
  navigator.clipboard.writeText(text).then(function() {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(function() {
      btn.textContent = 'Copy';
      btn.classList.remove('copied');
    }, 2000);
  }).catch(function() {
    // Silent fail — user can select text manually
  });
}
</script>

</body>
</html>
```

- [ ] **Step 8: Verify all relative paths are correct**

Run the following to confirm every referenced asset exists (must be run from the repo root `/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger`):

```bash
cd /home/nistrator/Documents/github/amplifier/ai_working/agent_debugger && \
grep -oE 'src="assets/[^"]*"' docs/index.html | sed 's/src="//;s/"//' | while read f; do
  [ -f "docs/$f" ] && echo "OK: $f" || echo "MISSING: $f"
done
```

Expected output: 4 lines starting with `OK:` — one per screenshot.

- [ ] **Step 9: Verify no absolute `/` paths slipped in**

```bash
grep -n 'href="/' docs/index.html || echo "clean"
grep -n 'src="/' docs/index.html || echo "clean"
```

Both should print `clean`. If any `/`-prefixed paths are found, replace them with relative equivalents.

- [ ] **Step 10: Commit HTML**

```bash
git add docs/index.html
git commit --author="acailic <acailic@users.noreply.github.com>" -m "feat: add landing page HTML for GitHub Pages"
```

---

## Task 3 — Push and Verify

**Files:** None created. Push + manual verification.

- [ ] **Step 1: Push to remote**

```bash
git push
```

- [ ] **Step 2: Remind user to enable GitHub Pages**

Output this reminder (if Pages not already enabled):

> In the GitHub repo Settings → Pages → Source: `Deploy from branch` → Branch: `main` → Folder: `/docs` → Save.
> Page will be live at: `https://acailic.github.io/agent_debugger/`

- [ ] **Step 3: Verify `.nojekyll` is in the push**

```bash
git log --oneline -3
git show HEAD:docs/.nojekyll && echo "nojekyll present"
```

- [ ] **Step 4: Final structural sanity check**

```bash
# Confirm all three deliverable files exist
ls -la docs/index.html docs/style.css docs/.nojekyll
```

Expected: all three files present, `index.html` > 5KB, `style.css` > 4KB, `.nojekyll` 0 bytes.

---

## Success Criteria

- [ ] `docs/.nojekyll` exists (0 bytes)
- [ ] `docs/style.css` contains `:root` CSS variable block
- [ ] `docs/index.html` has all 5 sections: Hero, Why, Features, Quick Install, Footer
- [ ] All 4 screenshot `src` paths use relative form `assets/*.png`
- [ ] No `href="/"` or `src="/"` absolute paths in `index.html`
- [ ] Copy button present in Hero install block
- [ ] All footer link `href` values are fully-qualified GitHub/PyPI URLs
- [ ] Both commits pushed to `main`
