# Scaffold a New UI Component

Create a new React component for the peaky-peek agent debugger frontend.

**Component request:** $ARGUMENTS

## Workflow

### Step 1: Learn project patterns

Read the composition root and 2-3 similar components to understand the actual patterns in this repo:

- `frontend/src/App.tsx`
- `frontend/src/types/index.ts`
- `frontend/src/api/client.ts`
- `frontend/src/stores/sessionStore.ts`
- 2-3 relevant files in `frontend/src/components/`

Good component starting points:

- `frontend/src/components/TraceTimeline.tsx` (D3 visualization patterns)
- `frontend/src/components/ConversationPanel.tsx` (data display with hooks)
- `frontend/src/components/ToolInspector.tsx` (interactive UI with state)

Pay attention to:
- Import ordering and style
- TypeScript typing patterns (props interfaces, generic usage)
- React hooks usage (useState, useEffect, useMemo, useCallback, useRef)
- How D3.js bindings are structured (useRef + useEffect pattern)
- How Zustand stores are connected (useStore selectors)
- CSS class naming conventions (check `frontend/src/App.css`)
- Export style (default vs named)

Also check `frontend/src/stores/`, `frontend/src/hooks/`, and `frontend/src/types/` for existing shared state, hooks, and type definitions that the new component should reuse.

### Step 2: Clarify requirements if needed

If `$ARGUMENTS` is just a component name with no description of what it should do, ask the user what the component should render and what behavior it needs. Do not guess.

If `$ARGUMENTS` includes a description or enough context to understand the purpose, proceed directly.

### Step 3: Generate the component

Create the component file at `frontend/src/components/ComponentName.tsx` following the patterns learned in Step 1.

The component must include:
- A typed props interface (e.g., `interface ComponentNameProps { ... }`)
- Proper React hooks following the project's conventions
- D3.js bindings using the useRef + useEffect pattern if the component is a visualization
- Zustand store connection via selectors if the component needs shared state
- CSS class naming that follows the existing conventions in the project

If the component needs to be wired into the existing application shell, update `frontend/src/App.tsx` and any related types/client hooks instead of leaving the component orphaned.

### Step 4: Add styles

If the component needs custom styles, add them using the project's current pattern in `frontend/src/App.css` unless there is already a more appropriate existing stylesheet.

### Step 5: Verify the build

Run the following to confirm the component compiles without errors:

```
cd frontend && npm run build
```

### Step 6: Fix build errors

If the build fails, read the error output, fix the issues in the generated files, and re-run the build. Repeat until it succeeds.

### Step 7: Report

Summarize what was created:
- The component file path
- Whether `App.tsx`, shared types, or API client code were updated
- Any new types, hooks, or store slices added
- Any CSS added
- Patterns or conventions worth noting for future components
