# Deep Code Upgrade

Analyze and improve a target module with modern patterns, better error handling, tighter types, and hardened boundaries.

Target: $ARGUMENTS

## Step 0: Resolve Target

If `$ARGUMENTS` is empty or missing, ask the user which module or file path they want to upgrade. Do not proceed until a target is provided.

Once you have a target, determine if it is a Python module (inside `agent_debugger_sdk/` or `api/`) or a frontend module (inside `frontend/src/`). This determines which idioms and best practices to apply.
Also treat `collector/`, `storage/`, `auth/`, and `redaction/` as Python/server targets when applicable.

## Step 1: Read and Understand

Read ALL files in the target module/directory. If the target is a single file, also read any closely related files (imports, tests, callers).

Before suggesting anything, build a mental model of:
- What the module does and its role in the larger system
- Its public API surface vs internal implementation
- Who calls it and what it depends on
- Existing test coverage in `tests/` and `tests/auto_patch/` when relevant
- Whether the module participates in a backend/frontend contract boundary

## Step 2: Analyze and Suggest Improvements

Group all suggestions into the following categories. For each suggestion, provide the specific file and line, the current code, the proposed change, and a brief rationale.

### For Python targets:

**A. Modernize Patterns**
- Replace `Union[X, Y]` with `X | Y` (Python 3.10+)
- Replace `Optional[X]` with `X | None`
- Use `match`/`case` where it is cleaner than `if`/`elif` chains (only where it genuinely improves readability)
- Use walrus operator (`:=`) where it eliminates duplicate calls or assignments
- Replace old-style string formatting with f-strings where not already done
- Use `pathlib.Path` over `os.path` where appropriate
- Use modern dict merge (`{**a, **b}` or `a | b`) where applicable

**B. Error Handling**
- Find bare `except:` or `except Exception:` that swallow errors without logging or re-raising
- Find missing error context (exceptions caught but re-raised without chaining via `from`)
- Identify places where errors should be caught but are not (e.g., I/O operations, external calls)
- Suggest exception hierarchies if the module defines custom exceptions poorly or not at all
- Ensure async context managers and cleanup paths handle errors properly

**C. Type Tightening**
- Add type hints to all public function signatures (parameters and return types)
- Find uses of `Any` that can be replaced with concrete types
- Ensure return types are explicit, not inferred
- Check that Pydantic models use proper field types and validators
- For SQLAlchemy models, verify column types match Python type annotations

**D. Boundary Hardening**
- Validate inputs at the module's public entry points
- Check that internal implementation details are not leaking through the public API
- Ensure clean separation between layers (SDK vs API vs frontend)
- Look for functions doing too much -- suggest splitting where appropriate
- Check that configuration values are validated early, not deep in call chains
- If event or API shapes are involved, inspect `api/schemas.py`, `frontend/src/types/index.ts`, and `frontend/src/api/client.ts` together

**E. Docstrings**
- ONLY suggest docstrings for public API surfaces that are genuinely unclear from the function name and type signature alone
- Do NOT add boilerplate docstrings that just restate the function name
- Focus on documenting non-obvious behavior, side effects, exceptions raised, and important constraints
- If the code is already clear, skip this category entirely

### For TypeScript/React targets:

**A. Modernize Patterns**
- Proper TypeScript generics instead of `any`
- Modern React patterns (hooks over class components, proper effect cleanup)
- Use `const` assertions, template literal types, discriminated unions where appropriate
- Replace verbose patterns with optional chaining (`?.`) and nullish coalescing (`??`)

**B. Error Handling**
- Error boundaries for React components
- Proper async error handling in effects and event handlers
- Type-safe error handling patterns

**C. Type Tightening**
- Eliminate `any` types
- Add proper generics to hooks and utility functions
- Ensure component props are fully typed
- Use strict TypeScript patterns (`satisfies`, `as const`, branded types where useful)

**D. Boundary Hardening**
- Validate API response shapes at the boundary (Zod or similar)
- Ensure proper separation of concerns between components, hooks, and services
- Check for prop drilling that should be state management
- If the target consumes API data, compare it against `frontend/src/types/index.ts` and the matching backend shape

**E. Docstrings**
- JSDoc only on complex utility functions or hooks with non-obvious behavior

## Step 3: Present Suggestions

Present all suggestions grouped by category. For each category, show:
1. A summary count (e.g., "3 suggestions")
2. Each suggestion with file path, current code snippet, proposed change, and rationale

Ask the user which categories they want to apply. They can pick one, multiple, or all.

## Step 4: Apply Changes

Apply changes ONE CATEGORY AT A TIME, in the order the user specifies. After applying each category:

1. Run `ruff check .` (for Python) or `cd frontend && npm run build` (for TypeScript/React) to verify no errors were introduced
2. Run `python3 -m pytest -q` for Python targets. For frontend targets, run the build again and note if no frontend test runner exists
3. Report the results before moving to the next category

If any check fails after applying a category, fix the issue before proceeding. If the fix is non-trivial, ask the user how to proceed.

## Step 5: Summary

After all requested categories are applied, provide a brief summary:
- Number of changes made per category
- Any verification results
- Remaining suggestions that were not applied (if any), for future reference
