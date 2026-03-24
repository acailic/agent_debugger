# GitHub Pages Refresh Implementation Plan

> **for agentic workers:** Required sub-skill: use superpowers:subagent-driven-development (recommended) | superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking
**Goal:** Create implementation plan for GitHub Pages refresh based approved design spec

**Architecture:** Single HTML page with categories. Pure CSS styling
**Tech Stack:** HTML5, CSS3
**Files to modify:**
- `docs/index.html`
- `docs/style.css`
---
```

## Task Structure
```
markdown
### Task 1: Update HTML structure
**Files:** `docs/index.html`, `docs/style.css`

**Goal:** Restructure HTML with hero, features, and get started sections

**Approach:**
- Update hero section with bolder headline and signature visual
- Add 3 feature categories with 2-3 features each
- Add social proof section with placeholder
- Improve get started steps
- Add comparison table (moved after social proof)
- Update footer

**Details:**
- Hero: Replace existing `<section class="hero">` with enhanced structure
- Features: Create new `<section class="section section--alt" id="features">` with 3 categories
- Social Proof: Create new `<section class="section" id="social-proof">` between features and get started
- Comparison: Move comparison table after social proof (in new section)
- Get Started: Update with clearer steps + bottom CTA
**Testing:**
- Manual browser testing (open `docs/index.html`)
- Verify all sections render correctly
- Verify all links work
- Verify responsive layout (mobile, tablet, desktop)
- Copy button functionality

- Verify dark theme appearance

**Verification Command:** Open `docs/index.html` in browser
```

### Task 2: Update CSS Styling
**Files:** `docs/style.css`
**Goal:** Add new styles for categories, signature hero, social proof
**Approach:**
- Add category section styles (`.category`, `.category__title`, `.category__grid`)
- Add signature hero styles (enhanced `.hero` with larger screenshot)
- Add social proof section styles (`.social-proof`, `.social-proof__quote`, `.social-proof__logos`)
- Enhance feature cards with category styling (`.feature-card--category`)
- Add comparison table enhancement styles
- Add get started section enhancements
**Details:**
- Category sections: 3 per theme section with title and feature grid
- Signature hero: Larger screenshot with better aspect ratio, drop shadow
- Social proof: Flex layout with quote and placeholder logos
- Feature cards: Support category color coding, subtle hover enhancements
- Comparison table: Moved inside social proof section with updated styling
- Get Started: Enhanced spacing, prominent CTA button styles
**Testing:**
- Manual browser testing
- Verify all new styles apply correctly
- Verify dark theme consistency
- Verify responsive breakpoints
- Cross-browser testing (Chrome, Firefox, Safari)

- Visual regression testing

**Verification command:** Open `docs/index.html` in multiple browsers
```

### Task 3: Commit and Push
**Goal:** Commit changes and push to GitHub
**Approach:**
- Stage modified files
- Commit with descriptive message
- Push to main branch
**Commands:**
```bash
git add docs/index.html docs/style.css docs/superpowers/specs/2026-03-24-github-pages-refresh-design.md docs/superpowers/plans/2026-03-24-github-pages-refresh.md
git commit -m "docs: refresh GitHub Pages with all new features"
```

**Testing:**
- Verify files committed correctly
- Verify commit message is clear
- Confirm no unintended changes

**Verification command:** `git status --short`
```

## Notes
- All screenshots already exist in `docs/assets/`
- Single HTML file structure maintained
- No JavaScript changes required (existing copy button functionality preserved)
- No external dependencies added
- Dark theme preserved throughout
