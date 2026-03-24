# Polish a UI Component

Run the full polish pipeline on a frontend component to improve its UX quality, robustness, accessibility, and visual consistency.

**Target component:** $ARGUMENTS

## Workflow

### Step 1: Identify the target component

If `$ARGUMENTS` is empty or unclear, list all available components from `frontend/src/components/` and ask the user which one to polish. Do not proceed without a clear target.

If `$ARGUMENTS` names a component, locate its file in `frontend/src/components/`. The user may provide just the name (e.g., "TraceTimeline") or the full filename (e.g., "TraceTimeline.tsx"). Resolve accordingly.

### Step 2: Read the component

Read the target component file in full. Also read any associated CSS files and any Zustand stores or hooks it depends on, so you have full context for the polish steps.

### Step 3: Run critique

Use the `critique` skill on the component to get a UX assessment. This identifies layout issues, confusing interactions, visual inconsistencies, and usability problems.

Review the critique output carefully before proceeding. This shapes the priorities for the next steps.

### Step 4: Run polish

Use the `polish` skill on the component to fix alignment, spacing, and visual consistency issues. This addresses the cosmetic and layout problems identified in the critique.

### Step 5: Run harden

Use the `harden` skill on the component to improve error handling, guard against edge cases such as empty states, text overflow, missing data, and loading states, and make the component more resilient.

### Step 6: Run audit

Use the `audit` skill on the component to check accessibility, performance, and theming consistency.

### Step 7: Verify the build

Run the frontend build to confirm everything still compiles:

```
cd frontend && npm run build
```

If the build fails, fix the errors and rebuild until it succeeds.

### Step 8: Visual verification with Playwright

Take a screenshot of the polished component for visual review:

1. Start the Vite preview server in the background: `cd frontend && npm run preview`
2. Wait a moment for the server to start
3. Use the `playwright` skill to navigate to `http://localhost:4173`
4. Take a screenshot of the page showing the component
5. Present the screenshot for the user to review
6. Kill the preview server process when done

### Step 9: Present summary

Provide a clear summary of all changes made across the four passes:
- **Critique findings** -- what UX issues were identified
- **Polish changes** -- alignment, spacing, and visual fixes applied
- **Hardening changes** -- error handling and edge case guards added
- **Audit changes** -- accessibility, performance, and theming improvements
- **Files modified** -- list every file that was changed with a brief note on what changed
