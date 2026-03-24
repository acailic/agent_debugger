# GitHub Pages Full Refresh Design Spec

**Date**: 2026-03-24
**Status**: Approved
**Approach**: Enhanced Feature Grid with Categories + Visual Polish

## Summary

Full refresh of the GitHub Pages landing page (`docs/index.html`) with:
- **Hero**: Bolder two-line headline, signature visual moment, stronger CTAs
- **Features**: Reorganized into 3 categories (Core Debugger, Multi-Agent, Safety & Analysis)
- **CTAs**: Prominent primary button, secondary actions, social proof section
- **Get Started**: Clearer steps with bottom CTA

## Design Principles

### AI Slop Prevention
- **No generic templates** — distinctive debugger aesthetic, dark, technical
- **Signature moment** — hero screenshot creates visual anchor
- **Information hierarchy** — categories guide attention; progressive disclosure reveals more

### Feature Categories (8 Features in 3 Groups)

| Category | Features | Screenshot |
|----------|----------|------------|
| **Core Debugger** | Decision Tree | `screenshot-decision-tree.png` |
| | Checkpoint Replay | `screenshot-checkpoint-replay.png` |
| | Trace Search | `screenshot-search.png` |
| **Multi-Agent** | Coordination | `screenshot-multi-agent-coord.png` |
| | Session Comparison | `screenshot-session-comparison.png` |
| **Safety & Analysis** | Safety Audit Trail | `screenshot-safety-session.png` |
| | Loop Detection | `screenshot-loop-detection.png` |
| | Failure Clustering | `screenshot-failure-cluster.png` |

### Visual Changes

| Element | Before | After |
|---------|--------|-------|
| Hero headline | Long sentence | Two-line punchy statement |
| Hero visual | None | `screenshot-full-ui.png` as signature anchor |
| Hero CTAs | Scattered | Single prominent primary button |
| Features | 4-card grid | 3 categories with 2-3 features each |
| Social proof | None | Placeholder badges + quote section |
| Get Started | Simple steps | Clearer steps + bottom CTA |

### Files to Update

| File | Changes |
|------|---------|
| `docs/index.html` | All sections updated per design spec |
| `docs/style.css` | New category styles, enhanced cards, signature hero styling |

### Social Proof Placeholder

```
"Finally, a debugger that shows me WHY my agent failed, not just THAT it failed."
— Early user, AI Engineer
```

### Implementation Notes

1. All existing screenshots are used - no new assets needed
2. Single-page HTML structure maintained
3. Responsive design handled (mobile stacks to single column)
4. No external dependencies added
5. This spec supersedes `2026-03-23-landing-page-design.md`

## Next Steps

1. Review the written spec
2. Invoke writing-plans skill for implementation plan
