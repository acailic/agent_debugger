# ADR-009: Frontend Strategy

**Status:** Accepted
**Date:** 2026-03-23

## Open Challenge

Skipping VS Code extension may leave a major adoption channel on the table. VS Code is where developers already live. A lightweight extension (session list + basic trace view inside the editor) could drive adoption more than a standalone web UI.

**Action:** Evaluate a minimal VS Code extension for Phase 2 or 3 — not a full debugger, but a sidebar that shows active sessions and links to the web UI. Low effort, high visibility.

## Resolution

Approved: React + Vite + TypeScript stack, three-panel layout, dark theme, Tailwind + shadcn/ui components. VS Code extension deferred to future consideration — not part of Phase 1. The standalone web UI is the priority for initial launch.

---

## Original Decision (Partially Deferred)

### Approved Parts
- React + Vite + TypeScript (keep current stack)
- Three core workflows: investigate failure, understand decision, monitor live
- Dark theme, three-panel layout, shareable session URLs
- Tailwind + shadcn/ui for components

### Deferred Part
- VS Code extension — originally deferred entirely, now reconsidered as a lightweight adoption tool
