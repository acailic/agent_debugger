# Delivery follow-up: implemented changes and remaining acceptance

**Verified:** 2026-09-20. **Baseline:** local and remote main at `f832204`.
This note follows the [earlier delivery refresh](2026-09-20-planning-evidence.md).
The [roadmap](../ROADMAP.md) owns priorities. Delivery/PR tests ran in an isolated
worktree; the later secret-scan correction and redaction tests used the primary
checkout. The local correction adds only scanner fingerprints and documentation;
no production code, PR branch or GitHub tracker state was changed.

## Newly delivered code

| Slice | Commit | Verified scope | Remaining boundary |
|---|---|---|---|
| Q06 | `42a6c6b` | Cluster routes use the shared tenant repository; checkpoint writes check parent-session ownership; route inventory and nine ASGI matrix tests exist | Real hosted startup, missing-key rejection, analytics scope, checkpoint event/session consistency and complete negative route coverage remain |
| Q07 | `730d1dc` | Python `eval` replaced by an allowlisted AST interpreter; forbidden calls/dunders rejected during evaluation | Creation/import validation, API 4xx errors and evaluation work/output bounds remain |
| Q08 | `7f95046` | Configured redaction covers stored event fields/metadata, live fan-out, checkpoints, session config and NDJSON spill; sentinel tests exist | Policy is opt-in; broad auth, retention and every future export sink are separate scopes |
| Q09 | `bd37ce0` | Explicit endpoint works without API key; disabled/no-endpoint paths are inert; offline handling is bounded | Installed-wheel onboarding and CLI behavior remain Q12 |
| Q10 | `e61f04d` | SDK calls semantic restore with configured auth, adopts returned IDs/provenance, and labels legacy GET fallback | Runtime continuation, browser restore workflow and hosted boundary completion remain separate |
| Q13 | `e8e6696` | Lazy Redis import, configured URL, bounded subscriber queue, reconnect and durability documentation | Real-service tests were skipped locally because the optional Redis client is absent; do not claim the service acceptance gate passed |

Q06 and Q07 were marked DONE in the previous queue update, but their original
acceptance gates are broader than the delivered code. Keep their completed
foundations visible and retain the remaining work under the same IDs. Q13's code
is delivered; its real-service acceptance remains unverified in this audit.

## Workflow evidence

- [CI run 35483421378](https://github.com/acailic/agent_debugger/actions/runs/35483421378)
  on `f832204` succeeded: Python 3.10/3.11/3.12 and dependency security.
- [Secret scan 35483421310](https://github.com/acailic/agent_debugger/actions/runs/35483421310)
  on the same revision failed in “Scan repository for committed secrets.” Its
  SARIF artifact identifies one synthetic redaction fixture, now reproduced and
  corrected locally as detailed below. The historical run remains failed; no new
  GitHub run has validated this correction. No matched values are copied here.
- [Earlier wave-1 CI](https://github.com/acailic/agent_debugger/actions/runs/35481828489)
  failed; later CI success does not erase that history. Q02's earlier three-run
  recovery gate remains completed, not a permanent guarantee of green workflows.

### Secret-scan diagnosis and local correction

The `gitleaks-results.sarif` artifact from run `35483421310` reports exactly one
`aws-access-token` finding: `tests/test_redaction_boundary.py:58`, introduced in
`7f950460dd0dc543e634b3f158656794a7171bcb`. The module explicitly defines synthetic
sentinels to prove redaction at storage, streaming and spill boundaries. This
finding is a deliberate dummy value, not an issued credential.

The failed-step CLI shortcut returned no log. The direct
[job log](https://github.com/acailic/agent_debugger/actions/runs/35483421310/job/106005224779)
established that the action actually used **Gitleaks 8.24.3**; the SARIF driver's
`v8.0.0` label is not the executed binary version. Version 8.30.1 reports the same
historical fixture as `generic-api-key` instead. Official release binaries were
downloaded into a temporary directory and their published checksums verified.

The local [`.gitleaksignore`](../../.gitleaksignore) contains the two exact
commit/path/rule/line fingerprints observed in these versions. It preserves the
fixture, all default detector rules, and scanning of future changes to that file.
There is no directory, path-wide or rule-wide exclusion.

| Check | Gitleaks 8.24.3 (CI version) | Gitleaks 8.30.1 |
|---|---|---|
| Failed push range before correction | 1 finding, nonzero exit | 1 finding, nonzero exit |
| Same range with exact fingerprints | 0 findings, exit 0 | 0 findings, exit 0 |
| Different synthetic value at the same path/line in a new disposable-clone commit | 1 new finding, exit 2 | 1 new finding, exit 2 |

The reproduced action range is `--no-merges --first-parent eb0e8a2^..f832204`.
With the CI version available as `gitleaks`, the corrected-range check is:

```bash
gitleaks git . --log-opts='--no-merges --first-parent eb0e8a2^..f832204' \
  --exit-code=2 --redact --no-banner
# exit 0 with .gitleaksignore; one finding without its fingerprints
.venv-ci/bin/python -m pytest -q tests/test_redaction_boundary.py \
  tests/test_redaction.py tests/test_redaction_security.py --maxfail=3
# 43 passed in 2.19s
```

A broader **complete HEAD-history** scan (`--log-opts=HEAD`, Gitleaks 8.24.3)
still exits 2 with **19 older findings** in March/April test and documentation
commits. They are outside the failed push range and are not suppressed by this
patch. A passing range scan is not a clean-history claim. W01 must retain this
separate historical baseline and confirm a new GitHub run after delivery of the
local correction.

Historical source review classified all 19 as test fixtures or documentation
placeholders; no evidence of an issued credential was found in this set. Values
are omitted below. Counts refer to historical findings, not distinct credentials.

| Rule / count | Historical path and lines | Commit | Classification evidence |
|---|---|---|---|
| `curl-auth-header` ×1 | `docs-site/docs/api-reference.md:21` | `549f59d5593f` | Explicit user-supplied placeholder in an authentication example |
| `private-key` ×2 | `tests/test_api_validation.py:227,230` | `5319d6520f87` | PEM begin headers only, without key bodies; regex fixtures |
| `jwt` ×1 | `tests/test_api_validation.py:213` | `5319d6520f87` | Conventional public demonstration token; local signature check matches its public example HMAC secret |
| `generic-api-key` ×7 | `tests/test_api_validation.py:249–254,263` | `5319d6520f87` | Patterned API-format and minimum-length test inputs |
| `generic-api-key` ×1 | `TESTING_QUICK_START.md:52` | `f93eee7b197a` | Patterned synthetic input in a documented redaction test |
| `generic-api-key` ×1 | `tests/test_sdk_config.py:32` | `0341fe616d93` | Test-labelled literal selects cloud defaults |
| `generic-api-key` ×2 | `tests/test_sdk_config.py:15,17` | `c55f8c8ffb5b` | Same synthetic input in initialization and its equality assertion |
| `generic-api-key` ×2 | `old_docs/superpowers/plans/2026-03-23-agent-debugger-cloud-evolution.md:792,794` | `5b9b3100eea7` | Historical copy of that SDK unit-test example |
| `generic-api-key` ×2 | `docs/superpowers/plans/2026-03-23-agent-debugger-cloud-evolution.md:792,794` | `ea6b4bac9787` | Another historical copy of the same example |

That cleanup rule has now been executed. **Historical baseline resolved
2026-09-21** in the primary checkout (working tree, not committed) using the
CI-matched **Gitleaks 8.24.3** official linux-amd64 release binary downloaded
from the gitleaks GitHub releases page, with its published checksum verified:
sha256 `9991e0b2903da4c8f6122b5c3186448b927a5da4deef1fe45271c3793f4ee29c`
for `gitleaks_8.24.3_linux_x64.tar.gz`, matching `gitleaks_8.24.3_checksums.txt`.

The reproduced complete-history scan (`gitleaks git . --log-opts=HEAD
--exit-code=2 --redact --no-banner`) exited 2 with exactly 19 findings, and
every finding mapped 1:1 onto the inventory rows above by rule, path, line and
commit — no finding was uncovered by the table and no row lacked a finding.
All **19 exact `commit:file:rule:line` fingerprints** were appended to
[`.gitleaksignore`](../../.gitleaksignore) under a commented
historical-fixture section, each with a one-line reason from this inventory's
classification; the two sentinel entries are unchanged. Re-runs on the same
checkout: `--log-opts=HEAD` now exits 0 with "no leaks found" across 670
commits, and the push range `--no-merges --first-parent eb0e8a2^..8a00a891`
exits 0 across 17 commits.

The failing new-value control was retained in a disposable clone under /tmp
(this checkout untouched): with the updated `.gitleaksignore` committed, one
further commit changed the flagged `tests/test_api_validation.py:249` value to
a different synthetic value that was first confirmed detector-visible (a
candidate the 8.24.3 detector did not flag was rejected as a control value).
`gitleaks git . --log-opts='HEAD~1..HEAD'` on that clone exits 2 with one
`generic-api-key` finding at the new commit, and the clone's own
`--log-opts=HEAD` scan reports exactly that one finding — the fingerprints are
exact-value exceptions, not blanket path ignores. The clone was then
discarded; no matched values are recorded here. No new GitHub run has yet
validated this broader-scan correction, so W01's new-CI-evidence item above
still stands.

## Fresh validation

The interpreter is the existing primary-checkout `.venv-ci/bin/python`; command
working directories are the isolated worktree. No dependencies were installed.

At `f832204`, with the exact #325 test file overlaid:

```bash
python3 -m pytest -q tests/alerts \
  tests/sdk/test_no_key_delivery.py tests/sdk/test_semantic_restore.py \
  tests/e2e/test_no_key_local_delivery.py tests/e2e/test_semantic_restore_sdk.py \
  tests/test_redaction_boundary.py tests/test_hosted_tenant_matrix.py --maxfail=3
# 86 passed in 9.34s; two websockets/uvicorn deprecation warnings
```

This includes real TCP collector/no-key delivery and real-server SDK restore.
It does not turn the ASGI hosted matrix into a real hosted-startup test.

At the preceding `e8e6696` worktree revision:

```bash
python3 -m pytest -q tests/test_breakpoint_safety.py tests/test_stepper.py \
  tests/test_stepper_routes.py tests/test_buffer_redis.py \
  tests/test_buffer_redis_service.py --maxfail=3
# 123 passed; two Redis test modules skipped: redis package unavailable
```

The [PR review](../reports/2026-09-20-pr325-review.md) records the separate
38-test warning-strict alert run, targeted 100% coverage and Ruff result.
These counts overlap; do not add them into a unique full-suite total. No full
local suite, browser, installed wheel, Docker or Redis service was exercised.

## Gaps reproduced or source-checked

### Q06: identity and reference checks

`tests/test_hosted_tenant_matrix.py` installs private cloud configuration and uses
ASGITransport. Its missing-key case deliberately asserts anonymous session
creation succeeds, and its analytics case asserts unauthenticated access succeeds.
These are useful observations of current behavior, not passing negative-auth gates.

`auth/middleware.py` still returns local identity when Authorization is absent.
`api/analytics_routes.py` GET/POST analytics routes remain unscoped.
`collector/server.py` checks checkpoint session ownership, but
`storage/repositories/checkpoint_repo.py` copies the supplied event ID without
checking that the event belongs to the checkpoint's session. The route inventory
is documentary; no registered-route synchronization check was found.

### Q07: validate before changing state

A safe in-memory probe used the unsupported expression `len(event.data) > 0`.
`AgentStepper.set_breakpoint` accepted it and appended state; evaluation later
raised the expected unsupported-function-call error. `import_state` also accepted
the unsupported condition. No unsafe expression or resource-intensive operation
was evaluated.

The interpreter removes unrestricted execution, but validation must move to
creation/import boundaries and API errors must become explicit 4xx responses.
Source inspection also found asymmetric sequence-multiplication limits and no
aggregate output/work budget. Verify limits using a recording operator stub so a
test proves rejection before any large allocation. Do not call syntax-size caps
a bound on total evaluation work.

### Q13: code versus service evidence

Real Redis tests are present but skipped when dependencies are absent. Schedule a
job with an actual ephemeral service and client, require those tests to run, and
retain fan-out, reconnect and queue-bound evidence. The implementation explicitly
does not promise replay/redelivery of messages missed during disconnects.

## Next plans

Deliver the locally verified secret-scan correction and obtain new CI evidence;
resolve the separate 19-finding historical fixture baseline. Complete the #325 review
handoff and finish Q06/Q07 acceptance. In parallel, Q04 can add payload contracts and Q12 can prove
installed artifacts. Q11 then needs browser interaction and visible restore
provenance, not merely the newly passing SDK restore tests. Q09/Q10 code should
be reused rather than reimplemented.

Refresh this note if the source revision, failed scan classification, PR head or
acceptance evidence changes. Historical benchmark/CI results retain their original
revision; this audit makes no new native-engine accuracy or hosting-readiness claim.
