# Design: Demo GIFs for Peaky Peek

## Context

The README has a placeholder for a hero demo GIF. To improve adoption and help users quickly understand the product's value, we need multiple short demo GIFs showing key features in action.

## Goal

Create 6 short (10-15 second) animated GIFs demonstrating the most impactful features, placed in `docs/demos/` and embedded in the README.

## Scope

### In Scope
- 6 feature demos (Decision Tree, Session Replay, Trace Search, Live Streaming, Failure Clustering, Session Comparison)
- Recording guide with step-by-step instructions
- `docs/demos/` folder structure
- README updates with embedded GIFs

### Out of Scope
- Video production/editing beyond basic GIF capture
- Voice-over or captions
- Automated recording scripts

## Design

### Folder Structure

```
docs/demos/
├── README.md              # Recording guide
├── decision-tree.gif      # Interactive tree navigation
├── session-replay.gif     # Time-travel playback
├── trace-search.gif       # Finding events across sessions
├── live-streaming.gif     # Real-time SSE events
├── failure-clustering.gif # Click cluster → jump to failure
└── session-comparison.gif # Side-by-side diff
```

### Demo Specifications

| Demo | Duration | What It Shows | Key Interactions |
|------|----------|---------------|------------------|
| Decision Tree | 10-12s | Agent reasoning flow | Pan, zoom, click node, inspect |
| Session Replay | 12-15s | Time-travel debugging | Play, pause, step, seek |
| Trace Search | 8-10s | Cross-session search | Type query, click result |
| Live Streaming | 10-12s | Real-time events | Agent runs, events appear live |
| Failure Clustering | 8-10s | Adaptive analysis | Click cluster, jump to failure |
| Session Comparison | 10-12s | Side-by-side diff | Select second session, view diff |

### README Integration

Each feature section gets an embedded GIF:

```markdown
### Decision Tree Visualization

![Decision Tree demo](./docs/demos/decision-tree.gif)

Navigate agent reasoning as an interactive tree. Click nodes to inspect events, zoom to explore complex flows, and double-click to collapse branches.
```

### Recording Guide (docs/demos/README.md)

Contains for each demo:
1. **Setup** - seed data, server commands
2. **Steps** - exact clicks/interactions
3. **Tips** - framing, timing, highlights

## Implementation Notes

### Seed Data Requirements

The existing `scripts/seed_demo_sessions.py` should provide sufficient demo content. May need to verify it creates:
- Sessions with decision trees (multiple branches)
- Sessions with failures for clustering
- Sessions suitable for comparison
- Events searchable by keyword

### GIF Tool Recommendations

- **macOS**: Kap, GIPHY Capture
- **Linux**: Peek, Byzanz
- **Windows**: ScreenToGif

Target specs:
- Resolution: 1280x720 or 800x600 (consistent across all)
- Frame rate: 15fps (smaller file size)
- Max file size: ~2MB per GIF

## Verification

1. All 6 GIFs present in `docs/demos/`
2. Each GIF demonstrates the feature clearly
3. README renders with embedded GIFs
4. GIFs load quickly (reasonable file sizes)
5. Recording guide is accurate (steps work)

## Open Questions

- None - design approved
