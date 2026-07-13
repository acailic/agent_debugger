"""Deterministic session audit engine.

Given a captured session's events and checkpoints, :class:`SessionAuditEngine`
produces a :data:`SessionAuditReport` that reframes the run as an audit record:

* **What happened** — action/tool/model/decision/retry sequence counts.
* **Why** — decisions with their rationale, confidence, and alternatives.
* **Evidence** — input sources used and evidence coverage.
* **Outcome** — successes, failures, and state changes.
* **Where it failed** — first bad decision, failure root-cause suspects,
  drift / loop / contradiction signals.

It also classifies every decision as a *claim* with a deterministic
``verification_status`` and emits an explainable trust score composed of
inspectable sub-metrics.

Design rules (see AGENTS.md / project philosophy):

* Deterministic + inspectable. No LLM calls, no randomness.
* Reuses :class:`~collector.causal_analysis.CausalAnalyzer` and
  :class:`~collector.failure_diagnostics.FailureDiagnostics` rather than
  re-deriving failure localization.
* Reads both typed event attributes and the ``data`` dict via
  :func:`~collector.intelligence.helpers.event_value`, so it works on
  events reconstructed from storage as well as freshly built ones.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_debugger_sdk.core.events import Checkpoint, EventType, TraceEvent

from ..causal_analysis import CausalAnalyzer
from ..failure_diagnostics import FailureDiagnostics
from ..intelligence.helpers import event_value

# ---------------------------------------------------------------------------
# Verification taxonomy
# ---------------------------------------------------------------------------

#: A claim whose supporting evidence resolves to a concrete successful
#: tool result, user input, or retrieved document.
VERIFIED = "verified"
#: A claim that carries evidence, but none of it resolves to a concrete
#: tool/user/retrieved fact in the trace.
PARTIALLY_VERIFIED = "partially_verified"
#: A claim whose downstream subtree contains a failure — the confident
#: assertion was contradicted by what actually happened.
CONTRADICTED = "contradicted"
#: A confident claim (confidence >= 0.5) made with no evidence at all.
UNSUPPORTED = "unsupported"
#: A low-confidence claim with no evidence — an unverified assumption.
UNVERIFIED = "unverified"
#: A grounded claim whose cited evidence was superseded — a concrete fact
#: (tool result / user input / retrieved doc) existed at decision time that
#: was newer than every cited fact and that the agent did NOT cite. The
#: decision was built on possibly-outdated evidence.
STALE = "stale"

#: Evidence ``source`` values that count as tool-backed facts.
TOOL_BACKED_SOURCES = frozenset(
    {"tool_result", "tool", "function", "api", "tool_call"}
)
#: Evidence ``source`` values that count as user-provided facts.
USER_SOURCES = frozenset({"user_input", "user", "human", "operator"})
#: Evidence ``source`` values that count as retrieved documents.
RETRIEVED_SOURCES = frozenset(
    {"retrieved", "retrieval", "document", "search", "memory", "rag"}
)

# Claim/decision confidence threshold above which a missing-evidence claim is
# treated as "unsupported" rather than merely "unverified".
UNSUPPORTED_CONFIDENCE_THRESHOLD = 0.5
# Confidence above which an evidence-free decision is a notable risk signal.
HIGH_CONFIDENCE_THRESHOLD = 0.7


@dataclass
class SessionAuditReport:
    """Structured audit report for a single session (plain dict payload)."""

    session_id: str
    objective: str | None
    final_outcome: str
    questions: dict[str, Any]
    claims: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    critical_decisions: list[dict[str, Any]]
    trust: dict[str, Any]
    review_points: list[dict[str, Any]] = field(default_factory=list)


class SessionAuditEngine:
    """Build a :class:`SessionAuditReport` from captured events.

    The engine is stateless: construct once, call :meth:`audit` per session.
    """

    def __init__(
        self,
        *,
        causal: CausalAnalyzer | None = None,
        diagnostics: FailureDiagnostics | None = None,
    ) -> None:
        self._causal = causal or CausalAnalyzer()
        self._diagnostics = diagnostics or FailureDiagnostics(self._causal)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def audit(
        self,
        events: list[TraceEvent],
        checkpoints: list[Checkpoint] | None = None,
        *,
        session: dict[str, Any] | None = None,
        failure_explanations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-serializable audit report dict.

        Args:
            events: Ordered session events.
            checkpoints: Optional checkpoints (used for outcome context).
            session: Optional session dict (``status``, ``agent_name`` ...).
            failure_explanations: Optional precomputed failure explanations
                from :class:`~collector.intelligence.facade.TraceIntelligence`.
                If omitted, the engine derives its own using
                :class:`FailureDiagnostics`.
        """
        checkpoints = checkpoints or []
        session = session or {}

        id_lookup = {event.id: event for event in events}
        children_by_parent = _build_children_index(events)

        tool_backed_ids, user_input_ids, retrieved_ids = self._index_facts(events)
        failure_events = [event for event in events if self._diagnostics.is_failure_event(event)]
        failure_event_ids = {event.id for event in failure_events}

        explanations = (
            failure_explanations
            if failure_explanations is not None
            else self._diagnostics.build_failure_explanations(
                events,
                self._empty_ranking_by_event_id(events),
                self._causal_headline,
            )
        )

        claims = self._build_claims(
            events,
            id_lookup=id_lookup,
            children_by_parent=children_by_parent,
            failure_event_ids=failure_event_ids,
            tool_backed_ids=tool_backed_ids,
            user_input_ids=user_input_ids,
            retrieved_ids=retrieved_ids,
        )
        signals = self._build_signals(events, claims)
        failures = self._build_failures(events, explanations)
        critical_decisions = self._build_critical_decisions(claims)

        trust = self._build_trust(
            events=events,
            claims=claims,
            failures=failures,
            signals=signals,
        )

        objective = self._infer_objective(events, session)
        final_outcome = self._infer_final_outcome(events, session)
        questions = self._build_questions(
            events=events,
            claims=claims,
            failures=failures,
            signals=signals,
            tool_backed_ids=tool_backed_ids,
            user_input_ids=user_input_ids,
            retrieved_ids=retrieved_ids,
            checkpoints=checkpoints,
        )

        report = SessionAuditReport(
            session_id=session.get("id") or (events[0].session_id if events else ""),
            objective=objective,
            final_outcome=final_outcome,
            questions=questions,
            claims=claims,
            signals=signals,
            failures=failures,
            critical_decisions=critical_decisions,
            trust=trust,
            review_points=self._build_review_points(claims, failures, signals),
        )
        return _report_to_dict(report)

    # ------------------------------------------------------------------
    # Per-decision justification (why / evidence / outcome / where-failed)
    # ------------------------------------------------------------------

    def justify_decision(
        self,
        events: list[TraceEvent],
        event_id: str,
        *,
        session: dict[str, Any] | None = None,
        failure_explanations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Return a per-decision justification record.

        The dominant audit interaction is drilling into one important node
        and asking *what / why / evidence / outcome / where-failed*. This
        reuses :meth:`audit` so the claim's verification status, evidence
        classification, and failure localization stay identical to the
        session-level report, then localizes the outcome + failure path to
        the decision's downstream subtree.

        Returns ``None`` when *event_id* is not a captured decision — callers
        map that to a 404.
        """
        report = self.audit(
            events, session=session, failure_explanations=failure_explanations
        )
        claim = next(
            (item for item in report["claims"] if item["event_id"] == event_id), None
        )
        if claim is None:
            return None

        id_lookup = {event.id: event for event in events}
        children_by_parent = _build_children_index(events)
        failure_event_ids = {
            event.id for event in events if self._diagnostics.is_failure_event(event)
        }
        subtree_ids = self._descendants_set(event_id, children_by_parent)
        subtree_events = [
            id_lookup[eid] for eid in subtree_ids if eid in id_lookup
        ]

        downstream_results = [
            event
            for event in subtree_events
            if event.event_type == EventType.TOOL_RESULT
        ]
        successes = [
            event for event in downstream_results if not event_value(event, "error")
        ]
        downstream_failures = [
            event for event in downstream_results if event_value(event, "error")
        ]
        produced = [
            str(event_value(event, "tool_name", "") or event.name or event.id)
            for event in successes
        ]
        state_changes = sum(
            1
            for event in subtree_events
            if event.event_type == EventType.REPAIR_ATTEMPT
            and event_value(event, "repair_diff")
        )

        subtree_failure_entries = [
            {
                "event_id": failure["event_id"],
                "mode": failure["mode"],
                "symptom": failure["symptom"],
                "likely_cause_event_id": failure["likely_cause_event_id"],
            }
            for failure in report["failures"]
            if failure.get("event_id") in subtree_ids
        ]
        path_to_first_failure = self._path_to_first_failure(
            event_id, children_by_parent, failure_event_ids
        )

        policy_in_subtree = [
            {
                "event_id": event.id,
                "type": str(
                    event_value(event, "violation_type", event.name or "violation")
                ),
            }
            for event in subtree_events
            if event.event_type == EventType.POLICY_VIOLATION
        ]

        decision_event = id_lookup.get(event_id)
        alternatives_raw = (
            event_value(decision_event, "alternatives", []) if decision_event else []
        )
        intent = (
            event_value(decision_event, "intent", None)
            or event_value(decision_event, "goal", None)
            if decision_event
            else None
        )
        action = (
            event_value(decision_event, "chosen_action", "") or claim["claim"]
            if decision_event
            else claim["claim"]
        )

        return {
            "event_id": event_id,
            "headline": claim["headline"],
            "what": {
                "claim": claim["claim"],
                "action": action,
                "event_type": claim["event_type"],
                "timestamp": claim["timestamp"],
            },
            "why": {
                "rationale": claim["rationale"],
                "intent": intent,
                "confidence": claim["confidence"],
                "alternatives": _summarize_alternatives(alternatives_raw),
            },
            "evidence": {
                "refs": claim["evidence_refs"],
                "resolved_refs": [
                    ref for ref in claim["evidence_refs"] if ref in id_lookup
                ],
                "sources": claim["evidence_sources"],
                "verification_status": claim["verification_status"],
                "verification_basis": claim["verification_basis"],
            },
            "outcome": {
                "downstream_event_count": len(subtree_events),
                "downstream_successes": len(successes),
                "downstream_failures": len(downstream_failures),
                "produced": produced,
                "state_changes": state_changes,
            },
            "where_it_failed": {
                "contradicted": claim["contradicted"],
                "subtree_failures": subtree_failure_entries,
                "path_to_first_failure": path_to_first_failure,
            },
            "policy": {
                "violations_in_subtree": policy_in_subtree,
                "compliant": len(policy_in_subtree) == 0,
            },
        }

    # ------------------------------------------------------------------
    # Evidence-provenance graph
    # ------------------------------------------------------------------

    def build_evidence_graph(
        self,
        events: list[TraceEvent],
        *,
        session: dict[str, Any] | None = None,
        failure_explanations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return an evidence-provenance graph for the session.

        Nodes are *claims* (decisions) and the *facts* available to the agent
        (tool results, user input). Edges are either ``evidence`` (a decision
        cites a fact via ``evidence_event_ids``) or ``causal`` (parent /
        upstream data-flow). Claim nodes carry the same ``verification_status``
        as the session-level audit, so the graph is a navigable view of how
        every claim connects to its evidence — including facts that existed
        but were never cited (a missing-evidence smell).

        Deterministic and derived entirely from captured event fields.
        """
        report = self.audit(
            events, session=session, failure_explanations=failure_explanations
        )
        claim_by_id = {claim["event_id"]: claim for claim in report["claims"]}
        id_lookup = {event.id: event for event in events}
        failure_event_ids = {
            event.id for event in events if self._diagnostics.is_failure_event(event)
        }

        node_ids: set[str] = set()
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_edges: set[tuple[str, str, str, str | None]] = set()
        unresolved_refs = 0

        def add_node(event_id: str) -> None:
            if event_id in node_ids or event_id not in id_lookup:
                return
            node_ids.add(event_id)
            event = id_lookup[event_id]
            claim = claim_by_id.get(event_id)
            nodes.append(
                _evidence_node(
                    event,
                    claim=claim,
                    failure_event_ids=failure_event_ids,
                )
            )

        def add_edge(
            source_id: str,
            target_id: str,
            edge_type: str,
            source_class: str | None,
        ) -> None:
            key = (source_id, target_id, edge_type, source_class)
            if key in seen_edges:
                return
            seen_edges.add(key)
            edges.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "edge_type": edge_type,
                    "source_class": source_class,
                }
            )

        # All claims + all available facts become nodes.
        for event in events:
            if _classify_node_role(event) in {"claim", "tool_fact", "user_fact"}:
                add_node(event.id)
        # Pull in any resolved evidence refs whose source event is "other".
        for claim in report["claims"]:
            for ref in claim["evidence_refs"]:
                if ref in id_lookup:
                    add_node(ref)

        # Evidence edges: claim -> cited fact.
        for claim in report["claims"]:
            for ref in claim["evidence_refs"]:
                if ref in id_lookup:
                    target = id_lookup[ref]
                    add_edge(
                        claim["event_id"],
                        ref,
                        "evidence",
                        _source_class_for(target),
                    )
                else:
                    unresolved_refs += 1

        # Causal edges among nodes already in the graph.
        for node_id in list(node_ids):
            event = id_lookup[node_id]
            upstream = set(event_value(event, "upstream_event_ids", []) or [])
            if event.parent_id:
                upstream.add(event.parent_id)
            for parent_id in upstream:
                if parent_id in node_ids:
                    add_edge(parent_id, node_id, "causal", None)

        role_counts: Counter[str] = Counter(node["role"] for node in nodes)
        verification_counts: Counter[str] = Counter(
            claim["verification_status"] for claim in report["claims"]
        )
        stats = {
            "node_count": len(nodes),
            "claim_count": len(report["claims"]),
            "fact_count": sum(
                count for role, count in role_counts.items() if role != "claim"
            ),
            "evidence_edges": sum(1 for e in edges if e["edge_type"] == "evidence"),
            "causal_edges": sum(1 for e in edges if e["edge_type"] == "causal"),
            "unresolved_evidence_refs": unresolved_refs,
            "verification_counts": dict(verification_counts),
            "evidence_coverage": report["trust"]["components"]["evidence_coverage"],
        }

        return {
            "session_id": report["session_id"],
            "nodes": nodes,
            "edges": edges,
            "stats": stats,
        }

    # ------------------------------------------------------------------
    # Portfolio aggregation (cross-session trust / verification)
    # ------------------------------------------------------------------

    def aggregate_audits(
        self,
        reports: list[dict[str, Any]],
        *,
        sessions_meta: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Aggregate per-session audit reports into a fleet-level summary.

        Cross-session counterpart of :meth:`audit`: it does not re-read
        events, it reduces already-computed audit reports into the portfolio
        view an operator scans to find the least trustworthy runs without
        opening each one. Pure and deterministic (no I/O, no LLM).

        Args:
            reports: Audit report dicts (as produced by :meth:`audit`).
            sessions_meta: Optional ``{session_id: {agent_name, started_at,
                status}}`` lookup merged into each per-session row.
        """
        sessions_meta = sessions_meta or {}
        band_distribution: Counter[str] = Counter()
        verification_totals: Counter[str] = Counter()
        signal_type_counts: Counter[str] = Counter()
        failure_mode_counts: Counter[str] = Counter()
        component_sums: dict[str, float] = {
            "evidence_coverage": 0.0,
            "verification_rate": 0.0,
            "policy_compliance": 0.0,
            "recovery_rate": 0.0,
            "failure_severity": 0.0,
        }
        total_decisions = 0
        total_failures = 0
        total_contradictions = 0
        total_unsupported = 0
        total_signals = 0
        trust_score_sum = 0.0
        rows: list[dict[str, Any]] = []

        for report in reports:
            trust = report.get("trust", {})
            score = _as_float(trust.get("score", 0.0), default=0.0)
            band = trust.get("band", "low")
            band_distribution[band] += 1
            trust_score_sum += score

            components = trust.get("components", {})
            for key in component_sums:
                component_sums[key] += _as_float(components.get(key, 0.0), default=0.0)

            claims = report.get("claims", [])
            for claim in claims:
                status = claim.get("verification_status", UNVERIFIED)
                verification_totals[status] += 1
                if status == UNSUPPORTED:
                    total_unsupported += 1
                elif status == CONTRADICTED:
                    total_contradictions += 1

            for signal in report.get("signals", []):
                signal_type_counts[signal.get("type", "unknown")] += 1
            total_signals += len(report.get("signals", []))

            for failure in report.get("failures", []):
                failure_mode_counts[failure.get("mode") or "unknown"] += 1

            session_id = report.get("session_id", "")
            meta = sessions_meta.get(session_id, {})
            decision_count = int(components.get("decision_count", 0) or 0)
            failure_count = int(components.get("failure_count", 0) or 0)
            total_decisions += decision_count
            total_failures += failure_count

            where_failed = report.get("questions", {}).get("where_it_failed", {}) or {}
            rows.append(
                {
                    "session_id": session_id,
                    "agent_name": meta.get("agent_name"),
                    "started_at": meta.get("started_at"),
                    "status": meta.get("status"),
                    "trust_score": round(score, 4),
                    "band": band,
                    "decision_count": decision_count,
                    "unsupported_count": sum(
                        1 for c in claims if c.get("verification_status") == UNSUPPORTED
                    ),
                    "contradiction_count": int(components.get("contradiction_count", 0) or 0),
                    "failure_count": failure_count,
                    "signal_count": len(report.get("signals", [])),
                    "first_bad_decision": where_failed.get("first_bad_decision"),
                    "objective": report.get("objective"),
                    "final_outcome": report.get("final_outcome"),
                }
            )

        count = len(reports)
        if count:
            means = {key: round(val / count, 4) for key, val in component_sums.items()}
            mean_trust = round(trust_score_sum / count, 4)
        else:
            means = {key: 0.0 for key in component_sums}
            mean_trust = 0.0

        # Worst-trust-first; tie-break by more failures then session id for determinism.
        rows.sort(key=lambda row: (row["trust_score"], -row["failure_count"], row["session_id"]))

        return {
            "total_sessions": count,
            "trust": {
                "mean_score": mean_trust,
                "band_distribution": dict(band_distribution),
            },
            "means": means,
            "verification_totals": dict(verification_totals),
            "totals": {
                "decisions": total_decisions,
                "failures": total_failures,
                "unsupported_claims": total_unsupported,
                "contradictions": total_contradictions,
                "signals": total_signals,
            },
            "signal_type_counts": [
                {"type": t, "count": c} for t, c in signal_type_counts.most_common()
            ],
            "failure_mode_counts": [
                {"mode": m, "count": c} for m, c in failure_mode_counts.most_common()
            ],
            "sessions": rows,
        }

    def _descendants_set(
        self, root_id: str, children_by_parent: dict[str, list[str]]
    ) -> set[str]:
        """Return the set of all event ids transitively downstream of *root_id*."""
        seen: set[str] = set()
        frontier = list(children_by_parent.get(root_id, []))
        # Bounded walk so a cyclic graph cannot loop forever.
        for _ in range(2000):
            if not frontier:
                return seen
            next_frontier: list[str] = []
            for node_id in frontier:
                if node_id in seen:
                    continue
                seen.add(node_id)
                next_frontier.extend(children_by_parent.get(node_id, []))
            frontier = next_frontier
        return seen

    def _path_to_first_failure(
        self,
        root_id: str,
        children_by_parent: dict[str, list[str]],
        failure_event_ids: set[str],
    ) -> list[str]:
        """BFS downstream from *root_id*; return the event-id path to the first failure.

        The path is inclusive of the failing event and exclusive of *root_id*.
        Returns an empty list when the decision's subtree has no failure.
        """
        queue: list[tuple[str, list[str]]] = [(root_id, [root_id])]
        seen: set[str] = {root_id}
        for _ in range(2000):
            if not queue:
                return []
            node, path = queue.pop(0)
            for child in children_by_parent.get(node, []):
                if child in seen:
                    continue
                seen.add(child)
                child_path = path + [child]
                if child in failure_event_ids:
                    return child_path
                queue.append((child, child_path))
        return []

    # ------------------------------------------------------------------
    # Fact indexing — what counts as grounded evidence in this trace
    # ------------------------------------------------------------------

    def _index_facts(
        self, events: list[TraceEvent]
    ) -> tuple[set[str], set[str], set[str]]:
        tool_backed: set[str] = set()
        user_input: set[str] = set()
        retrieved: set[str] = set()
        for event in events:
            if event.event_type == EventType.TOOL_RESULT and not event_value(event, "error"):
                tool_backed.add(event.id)
            if event.event_type in {EventType.AGENT_TURN, EventType.AGENT_START}:
                if event_value(event, "content") or event_value(event, "goal"):
                    user_input.add(event.id)
            # Evidence items that name a concrete source are themselves facts.
            for item in event_value(event, "evidence", []) or []:
                source = str(item.get("source", "")).lower() if isinstance(item, dict) else ""
                if source in TOOL_BACKED_SOURCES:
                    tool_backed.add(event.id)
                elif source in RETRIEVED_SOURCES:
                    retrieved.add(event.id)
                elif source in USER_SOURCES:
                    user_input.add(event.id)
        return tool_backed, user_input, retrieved

    # ------------------------------------------------------------------
    # Claim construction + verification
    # ------------------------------------------------------------------

    def _build_claims(
        self,
        events: list[TraceEvent],
        *,
        id_lookup: dict[str, TraceEvent],
        children_by_parent: dict[str, list[str]],
        failure_event_ids: set[str],
        tool_backed_ids: set[str],
        user_input_ids: set[str],
        retrieved_ids: set[str],
    ) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        # Chronological list of (timestamp, id) for every concrete fact in the
        # trace — used to detect decisions that acted on stale (superseded)
        # evidence. Computed once here from the fact sets already classified.
        concrete_fact_ids = tool_backed_ids | user_input_ids | retrieved_ids
        fact_timeline = sorted(
            (_event_ts(event), event.id)
            for event in events
            if event.id in concrete_fact_ids
        )
        for event in events:
            if event.event_type != EventType.DECISION:
                continue
            confidence = _as_float(event_value(event, "confidence", 0.5), default=0.5)
            evidence_items = event_value(event, "evidence", []) or []
            evidence_event_ids = event_value(event, "evidence_event_ids", []) or []
            rationale = (
                event_value(event, "rationale", None)
                or event_value(event, "reasoning", None)
                or ""
            )

            evidence_sources = _classify_evidence(evidence_items)
            resolved_evidence_ids = [eid for eid in evidence_event_ids if eid in id_lookup]

            verification_status, verification_basis = self._verify_claim(
                event=event,
                confidence=confidence,
                evidence_items=evidence_items,
                evidence_event_ids=evidence_event_ids,
                resolved_evidence_ids=resolved_evidence_ids,
                tool_backed_ids=tool_backed_ids,
                user_input_ids=user_input_ids,
                retrieved_ids=retrieved_ids,
                children_by_parent=children_by_parent,
                failure_event_ids=failure_event_ids,
                fact_timeline=fact_timeline,
            )

            contradicted = verification_status == CONTRADICTED
            claims.append(
                {
                    "event_id": event.id,
                    "event_type": str(event.event_type),
                    "headline": self._causal_headline(event),
                    "claim": event_value(event, "chosen_action", "") or rationale or event.name,
                    "rationale": rationale,
                    "confidence": round(confidence, 4),
                    "alternatives_considered": len(event_value(event, "alternatives", []) or []),
                    "evidence_refs": list(evidence_event_ids),
                    "evidence_sources": evidence_sources,
                    "verification_status": verification_status,
                    "verification_basis": verification_basis,
                    "contradicted": contradicted,
                    "timestamp": _iso(event),
                }
            )
        return claims

    def _verify_claim(
        self,
        *,
        event: TraceEvent,
        confidence: float,
        evidence_items: list[Any],
        evidence_event_ids: list[str],
        resolved_evidence_ids: list[str],
        tool_backed_ids: set[str],
        user_input_ids: set[str],
        retrieved_ids: set[str],
        children_by_parent: dict[str, list[str]],
        failure_event_ids: set[str],
        fact_timeline: list[tuple[datetime, str]],
    ) -> tuple[str, str]:
        has_evidence = bool(evidence_items) or bool(evidence_event_ids)

        # Contradiction: a confident decision whose downstream subtree failed.
        if confidence >= UNSUPPORTED_CONFIDENCE_THRESHOLD and _descendants_include_failure(
            event.id, children_by_parent, failure_event_ids
        ):
            return CONTRADICTED, "decision subtree contains a failure event"

        resolved_tool_backed = [eid for eid in resolved_evidence_ids if eid in tool_backed_ids]
        resolved_user = [eid for eid in resolved_evidence_ids if eid in user_input_ids]
        resolved_retrieved = [eid for eid in resolved_evidence_ids if eid in retrieved_ids]
        named_tool_backed = any(
            (isinstance(item, dict) and str(item.get("source", "")).lower() in TOOL_BACKED_SOURCES)
            for item in evidence_items
        )
        named_user = any(
            (isinstance(item, dict) and str(item.get("source", "")).lower() in USER_SOURCES)
            for item in evidence_items
        )
        named_retrieved = any(
            (isinstance(item, dict) and str(item.get("source", "")).lower() in RETRIEVED_SOURCES)
            for item in evidence_items
        )

        if resolved_tool_backed or named_tool_backed:
            base_status, base_basis = VERIFIED, "backed by a successful tool result"
        elif resolved_user or named_user:
            base_status, base_basis = VERIFIED, "backed by user-provided input"
        elif resolved_retrieved or named_retrieved:
            base_status, base_basis = (
                PARTIALLY_VERIFIED,
                "backed by retrieved evidence (not tool-verified)",
            )
        elif has_evidence:
            base_status, base_basis = (
                PARTIALLY_VERIFIED,
                "carries evidence that does not resolve to a concrete fact",
            )
        elif confidence >= UNSUPPORTED_CONFIDENCE_THRESHOLD:
            base_status, base_basis = UNSUPPORTED, "confident claim made with no evidence"
        else:
            base_status, base_basis = UNVERIFIED, "low-confidence claim with no evidence"

        # Staleness: a grounded claim that ignored a newer concrete fact.
        # Only overrides VERIFIED / PARTIALLY_VERIFIED — ungrounded claims have
        # no cited evidence to be "outdated", and CONTRADICTED is already worse.
        if base_status in {VERIFIED, PARTIALLY_VERIFIED}:
            stale, stale_basis = _staleness_check(event, resolved_evidence_ids, fact_timeline)
            if stale:
                return STALE, stale_basis
        return base_status, base_basis

    # ------------------------------------------------------------------
    # Risk signals
    # ------------------------------------------------------------------

    def _build_signals(
        self,
        events: list[TraceEvent],
        claims: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []

        for claim in claims:
            event_id = claim["event_id"]
            confidence = claim["confidence"]
            evidence_refs = claim["evidence_refs"]
            evidence_sources = claim["evidence_sources"]

            # missing_evidence / unsupported_claim / confidence_evidence_mismatch
            if claim["verification_status"] == UNSUPPORTED:
                signals.append(
                    _signal(
                        event_id,
                        "unsupported_claim",
                        "high",
                        f'Decision "{claim["headline"]}" asserted at confidence '
                        f"{confidence:.2f} without any evidence.",
                    )
                )
                signals.append(
                    _signal(
                        event_id,
                        "confidence_evidence_mismatch",
                        "high",
                        f"Confidence {confidence:.2f} is unjustified: no evidence attached.",
                    )
                )
            elif not evidence_refs and not evidence_sources and confidence >= HIGH_CONFIDENCE_THRESHOLD:
                signals.append(
                    _signal(
                        event_id,
                        "missing_evidence",
                        "medium",
                        f'High-confidence decision "{claim["headline"]}" lacks evidence references.',
                    )
                )

            if claim["verification_status"] == CONTRADICTED:
                signals.append(
                    _signal(
                        event_id,
                        "contradiction",
                        "high",
                        f'Confident decision "{claim["headline"]}" was followed by a failure '
                        "in its causal subtree.",
                    )
                )

            if claim["verification_status"] == PARTIALLY_VERIFIED:
                signals.append(
                    _signal(
                        event_id,
                        "weak_evidence",
                        "low",
                        f'Decision "{claim["headline"]}" relies on evidence that is not '
                        "tool-verified.",
                    )
                )

            if claim["verification_status"] == STALE:
                signals.append(
                    _signal(
                        event_id,
                        "stale_evidence",
                        "medium",
                        f'Decision "{claim["headline"]}" relies on evidence that was '
                        "superseded by a newer concrete fact it did not cite.",
                    )
                )

        # repeated_failed_strategy: same tool failing more than once.
        tool_failures: Counter[str] = Counter()
        tool_failure_event: dict[str, str] = {}
        for event in events:
            if (
                event.event_type == EventType.TOOL_RESULT
                and event_value(event, "error")
            ):
                tool_name = event_value(event, "tool_name", "<unknown>") or "<unknown>"
                tool_failures[tool_name] += 1
                tool_failure_event.setdefault(tool_name, event.id)
        for tool_name, count in tool_failures.items():
            if count >= 2:
                signals.append(
                    _signal(
                        tool_failure_event[tool_name],
                        "repeated_failed_strategy",
                        "high" if count >= 3 else "medium",
                        f'Tool "{tool_name}" failed {count} times — repeated failed strategy.',
                    )
                )

        # plan_drift: explicit DRIFT events, tool-loop alerts, or status error.
        for event in events:
            if event.event_type == EventType.DRIFT:
                signals.append(
                    _signal(
                        event.id,
                        "plan_drift",
                        "high",
                        f"Drift detected: {event_value(event, 'signal', event.name or 'agent diverged from plan')}.",
                    )
                )
            if event.event_type == EventType.BEHAVIOR_ALERT and event_value(
                event, "alert_type", ""
            ) == "tool_loop":
                signals.append(
                    _signal(
                        event.id,
                        "plan_drift",
                        "high",
                        f"Tool-loop behavior: {event_value(event, 'signal', 'repeated tool invocations')}.",
                    )
                )

        # policy violations lower trust and are surfaced explicitly.
        for event in events:
            if event.event_type == EventType.POLICY_VIOLATION:
                signals.append(
                    _signal(
                        event.id,
                        "policy_violation",
                        "high",
                        f"Policy violation: {event_value(event, 'violation_type', event.name or 'rule breach')}.",
                    )
                )

        signals.sort(key=lambda item: (_SEVERITY_RANK[item["severity"]], item["type"]))
        return signals

    # ------------------------------------------------------------------
    # Failures (reuse FailureDiagnostics explanations)
    # ------------------------------------------------------------------

    def _build_failures(
        self, events: list[TraceEvent], explanations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        index_lookup = {event.id: index for index, event in enumerate(events)}
        failures: list[dict[str, Any]] = []
        for explanation in explanations:
            failures.append(
                {
                    "event_id": explanation.get("failure_event_id"),
                    "event_type": explanation.get("failure_event_type"),
                    "headline": explanation.get("failure_headline"),
                    "mode": explanation.get("failure_mode"),
                    "symptom": explanation.get("symptom"),
                    "likely_cause": explanation.get("likely_cause"),
                    "likely_cause_event_id": explanation.get("likely_cause_event_id"),
                    "confidence": explanation.get("confidence", 0.0),
                    "supporting_event_ids": explanation.get("supporting_event_ids", []),
                    "position": index_lookup.get(str(explanation.get("failure_event_id")), -1),
                }
            )
        failures.sort(key=lambda item: (-float(item.get("confidence") or 0.0), item.get("position", 0)))
        return failures

    def _build_critical_decisions(self, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """High-impact decisions worth surfacing for human review."""
        critical = [
            claim
            for claim in claims
            if claim["verification_status"] in {UNSUPPORTED, CONTRADICTED}
            or claim["confidence"] >= HIGH_CONFIDENCE_THRESHOLD
        ]
        critical.sort(key=lambda claim: (-claim["confidence"], claim["event_id"]))
        return critical[:10]

    # ------------------------------------------------------------------
    # Trust / reliability score (explainable)
    # ------------------------------------------------------------------

    def _build_trust(
        self,
        *,
        events: list[TraceEvent],
        claims: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        decisions = [event for event in events if event.event_type == EventType.DECISION]
        decision_count = len(decisions) or 1
        decisions_with_evidence = sum(1 for claim in claims if claim["evidence_refs"])

        evidence_coverage = decisions_with_evidence / decision_count
        verification_rate = _safe_rate(
            claims,
            lambda claim: claim["verification_status"] == VERIFIED,
        )
        contradiction_count = sum(1 for claim in claims if claim["verification_status"] == CONTRADICTED)
        contradiction_rate = contradiction_count / decision_count

        failure_severity = _max_failure_severity(failures, events, self._causal)

        repair_attempts = [event for event in events if event.event_type == EventType.REPAIR_ATTEMPT]
        recoveries = sum(
            1
            for event in repair_attempts
            if str(event_value(event, "repair_outcome", "")).lower() == "success"
        )
        failure_count = max(1, len(failures))
        recovery_rate = recoveries / failure_count

        policy_violations = sum(1 for event in events if event.event_type == EventType.POLICY_VIOLATION)
        policy_compliance = max(0.0, 1.0 - policy_violations / decision_count)

        repeated_strategy = sum(
            1 for signal in signals if signal["type"] == "repeated_failed_strategy"
        )

        # Transparent weighted blend. Each term is inspectable above.
        score = (
            0.30
            + 0.25 * evidence_coverage
            + 0.20 * verification_rate
            + 0.10 * policy_compliance
            + 0.10 * recovery_rate
            - 0.15 * failure_severity
            - 0.05 * contradiction_rate
            - 0.05 * min(repeated_strategy, 3) / 3.0
        )
        score = max(0.0, min(1.0, score))

        components = {
            "evidence_coverage": round(evidence_coverage, 4),
            "verification_rate": round(verification_rate, 4),
            "contradiction_count": contradiction_count,
            "contradiction_rate": round(contradiction_rate, 4),
            "failure_severity": round(failure_severity, 4),
            "recovery_rate": round(recovery_rate, 4),
            "policy_compliance": round(policy_compliance, 4),
            "decision_count": len(decisions),
            "failure_count": len(failures),
        }
        band = "low" if score < 0.45 else "medium" if score < 0.7 else "high"
        explanation = (
            f"trust={score:.2f} ({band}) from evidence_coverage={evidence_coverage:.2f}, "
            f"verification_rate={verification_rate:.2f}, policy_compliance={policy_compliance:.2f}, "
            f"recovery_rate={recovery_rate:.2f}, failure_severity={failure_severity:.2f}, "
            f"contradictions={contradiction_count}."
        )
        return {
            "score": round(score, 4),
            "band": band,
            "components": components,
            "explanation": explanation,
        }

    # ------------------------------------------------------------------
    # The five questions
    # ------------------------------------------------------------------

    def _build_questions(
        self,
        *,
        events: list[TraceEvent],
        claims: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        signals: list[dict[str, Any]],
        tool_backed_ids: set[str],
        user_input_ids: set[str],
        retrieved_ids: set[str],
        checkpoints: list[Checkpoint],
    ) -> dict[str, Any]:
        tool_calls = sum(1 for event in events if event.event_type == EventType.TOOL_CALL)
        tool_results = sum(1 for event in events if event.event_type == EventType.TOOL_RESULT)
        llm_calls = sum(1 for event in events if event.event_type == EventType.LLM_REQUEST)
        retries = sum(1 for event in events if event.event_type == EventType.REPAIR_ATTEMPT)
        decisions = [event for event in events if event.event_type == EventType.DECISION]
        edits = sum(
            1
            for event in events
            if event.event_type == EventType.REPAIR_ATTEMPT and event_value(event, "repair_diff")
        )

        what_happened = {
            "summary": (
                f"{len(events)} events: {tool_calls} tool calls, {llm_calls} model calls, "
                f"{len(decisions)} decisions, {retries} retries, {len(failures)} failures."
            ),
            "event_count": len(events),
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "llm_calls": llm_calls,
            "decisions": len(decisions),
            "retries": retries,
            "edits": edits,
        }

        why = {
            "decisions_with_rationale": [
                {
                    "event_id": claim["event_id"],
                    "headline": claim["headline"],
                    "rationale": claim["rationale"],
                    "confidence": claim["confidence"],
                    "alternatives_considered": claim["alternatives_considered"],
                }
                for claim in claims
                if claim["rationale"]
            ],
        }

        evidence = {
            "tool_backed_facts": len(tool_backed_ids),
            "user_input_facts": len(user_input_ids),
            "retrieved_facts": len(retrieved_ids),
            "evidence_sources": sorted(
                {source for claim in claims for source in claim["evidence_sources"]}
            ),
            "coverage_of_decisions": (
                sum(1 for claim in claims if claim["evidence_refs"]) / max(1, len(claims))
            ),
        }

        successful_tools = sum(
            1
            for event in events
            if event.event_type == EventType.TOOL_RESULT and not event_value(event, "error")
        )
        failed_tools = sum(
            1
            for event in events
            if event.event_type == EventType.TOOL_RESULT and event_value(event, "error")
        )
        outcome = {
            "success_count": successful_tools,
            "failure_count": len(failures),
            "failed_tool_results": failed_tools,
            "state_snapshots": len(checkpoints),
            "failures": [
                {
                    "event_id": failure["event_id"],
                    "mode": failure["mode"],
                    "symptom": failure["symptom"],
                    "likely_cause_event_id": failure["likely_cause_event_id"],
                }
                for failure in failures
            ],
        }

        where_failed = {
            "first_failure": failures[-1]["event_id"] if failures else None,
            "first_bad_decision": _first_bad_decision(claims, failures),
            "failures": len(failures),
            "top_signals": [
                {"type": signal["type"], "severity": signal["severity"], "message": signal["message"]}
                for signal in signals
                if signal["severity"] in {"high", "medium"}
            ][:8],
        }

        return {
            "what_happened": what_happened,
            "why": why,
            "evidence": evidence,
            "outcome": outcome,
            "where_it_failed": where_failed,
        }

    # ------------------------------------------------------------------
    # Objective / outcome inference
    # ------------------------------------------------------------------

    def _infer_objective(self, events: list[TraceEvent], session: dict[str, Any]) -> str | None:
        config_goal = session.get("goal") if isinstance(session.get("goal"), str) else None
        if config_goal:
            return config_goal
        for event in events:
            goal = event_value(event, "goal", None)
            if goal:
                return str(goal)
        # Fall back to the first user-flavored content.
        for event in events:
            if event.event_type in {EventType.AGENT_TURN, EventType.AGENT_START}:
                content = event_value(event, "content", None)
                if content:
                    return self._causal._clip(content, 160)
        return None

    def _infer_final_outcome(self, events: list[TraceEvent], session: dict[str, Any]) -> str:
        status = session.get("status")
        failures = [event for event in events if self._diagnostics.is_failure_event(event)]
        if status == "error" or (failures and not events):
            return "session ended in error"
        if failures:
            return f"completed with {len(failures)} failure signal(s)"
        if status:
            return f"completed ({status})"
        return "completed"

    # ------------------------------------------------------------------
    # Review points (human audit assist)
    # ------------------------------------------------------------------

    def _build_review_points(
        self,
        claims: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        signals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        review: list[dict[str, Any]] = []
        for claim in claims:
            if claim["verification_status"] in {UNSUPPORTED, CONTRADICTED}:
                review.append(
                    {
                        "event_id": claim["event_id"],
                        "priority": "high",
                        "reason": (
                            f"Decision \"{claim['headline']}\" is {claim['verification_status']} "
                            f"(confidence {claim['confidence']:.2f})."
                        ),
                    }
                )
        for failure in failures[:3]:
            review.append(
                {
                    "event_id": failure["event_id"],
                    "priority": "high",
                    "reason": f"Failure ({failure['mode']}): {failure['symptom']}",
                }
            )
        for signal in signals:
            if signal["severity"] == "high":
                review.append(
                    {
                        "event_id": signal["event_id"],
                        "priority": "medium",
                        "reason": f"{signal['type']}: {signal['message']}",
                    }
                )
        # Deduplicate by (event_id, reason) while preserving order.
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for item in review:
            key = (item["event_id"], item["reason"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        unique.sort(key=lambda item: (priority_rank[item["priority"]], item["event_id"]))
        return unique[:15]

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _causal_headline(self, event: TraceEvent) -> str:
        # Reuse the failure-diagnostics clip via the causal analyzer.
        name = event.name or str(event.event_type).replace("_", " ")
        return self._causal._clip(name, 96)

    def _empty_ranking_by_event_id(self, events: list[TraceEvent]) -> dict[str, dict[str, Any]]:
        return {
            event.id: {
                "event_id": event.id,
                "severity": self._causal.severity(event),
                "composite": self._causal.severity(event),
                "importance": float(event.importance or 0.0),
            }
            for event in events
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _signal(event_id: str, signal_type: str, severity: str, message: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "type": signal_type,
        "severity": severity,
        "message": message,
    }


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _iso(event: TraceEvent) -> str:
    timestamp = event.timestamp
    return timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)


def _classify_evidence(evidence_items: list[Any]) -> list[str]:
    sources: list[str] = []
    for item in evidence_items or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).lower()
        if not source:
            continue
        if source in TOOL_BACKED_SOURCES:
            sources.append("tool_backed")
        elif source in USER_SOURCES:
            sources.append("user_provided")
        elif source in RETRIEVED_SOURCES:
            sources.append("retrieved")
        else:
            sources.append("inferred")
    return sources


def _event_ts(event: TraceEvent) -> datetime:
    """Comparable timestamp for an event (datetime, normalized to UTC).

    Tolerant of storage-reconstructed events whose ``timestamp`` may be an
    ISO string; unparseable values fall back to a sentinel so ordering stays
    total instead of raising.
    """
    ts = event.timestamp
    if isinstance(ts, datetime):
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _staleness_check(
    event: TraceEvent,
    resolved_evidence_ids: list[str],
    fact_timeline: list[tuple[datetime, str]],
) -> tuple[bool, str]:
    """Return ``(is_stale, basis)`` for a grounded claim.

    A claim is stale when it cites at least one concrete fact AND a strictly
    newer concrete fact existed at decision time that the agent did NOT cite —
    i.e. it acted on possibly-outdated evidence when fresher evidence was
    available. Purely structural (event timestamps + ordering), so it is
    deterministic and stable on synthetic traces; no wall-clock window.
    """
    if not fact_timeline or not resolved_evidence_ids:
        return False, ""
    decision_ts = _event_ts(event)
    cited_ts = [ts for ts, eid in fact_timeline if eid in resolved_evidence_ids]
    if not cited_ts:
        return False, ""
    newest_cited = max(cited_ts)
    newer_uncited = [
        ts
        for ts, eid in fact_timeline
        if eid not in resolved_evidence_ids and newest_cited < ts <= decision_ts
    ]
    if newer_uncited:
        return True, (
            "cited evidence was superseded: a newer concrete fact was "
            "available at decision time and was not cited"
        )
    return False, ""


def _build_children_index(events: list[TraceEvent]) -> dict[str, list[str]]:
    """Map each event id to the ids of events that declare it as a parent/upstream/evidence source.

    Used for downstream (causal-subtree) walks without re-scanning all events.
    """
    children: dict[str, list[str]] = {}
    for event in events:
        parent_refs = set(event_value(event, "upstream_event_ids", []) or [])
        parent_refs.update(event_value(event, "evidence_event_ids", []) or [])
        if event.parent_id:
            parent_refs.add(event.parent_id)
        for parent_id in parent_refs:
            children.setdefault(parent_id, []).append(event.id)
    return children


def _descendants_include_failure(
    root_id: str,
    children_by_parent: dict[str, list[str]],
    failure_event_ids: set[str],
) -> bool:
    """BFS downstream from *root_id*; True if any descendant is a failure event."""
    frontier = list(children_by_parent.get(root_id, []))
    seen: set[str] = {root_id}
    # Bound the walk so a cyclic graph cannot loop forever.
    for _ in range(200):
        if not frontier:
            return False
        next_frontier: list[str] = []
        for node_id in frontier:
            if node_id in seen:
                continue
            seen.add(node_id)
            if node_id in failure_event_ids:
                return True
            next_frontier.extend(children_by_parent.get(node_id, []))
        frontier = next_frontier
    return False


def _classify_node_role(event: TraceEvent) -> str:
    """Classify an event into an evidence-graph node role."""
    if event.event_type == EventType.DECISION:
        return "claim"
    if event.event_type == EventType.TOOL_RESULT:
        return "tool_fact"
    if event.event_type in {EventType.AGENT_TURN, EventType.AGENT_START}:
        return "user_fact"
    return "other"


def _source_class_for(event: TraceEvent) -> str:
    """Evidence-edge ``source_class`` for a cited target event."""
    role = _classify_node_role(event)
    if role == "tool_fact":
        return "tool_backed"
    if role == "user_fact":
        return "user_provided"
    return "other"


def _event_label(event: TraceEvent) -> str:
    label = (
        event_value(event, "tool_name", None)
        or event_value(event, "chosen_action", None)
        or event_value(event, "goal", None)
        or event.name
        or str(event.event_type).replace("_", " ")
    )
    return str(label)[:96]


def _evidence_node(
    event: TraceEvent,
    *,
    claim: dict[str, Any] | None,
    failure_event_ids: set[str],
) -> dict[str, Any]:
    role = _classify_node_role(event)
    if claim is not None:
        verification_status: str | None = claim["verification_status"]
        confidence: float | None = claim["confidence"]
    else:
        verification_status = None
        confidence = None
    return {
        "event_id": event.id,
        "event_type": str(event.event_type),
        "role": role,
        "label": _event_label(event),
        "verification_status": verification_status,
        "confidence": confidence,
        "is_failure": event.id in failure_event_ids,
        "timestamp": _iso(event),
    }


def _summarize_alternatives(alternatives: list[Any]) -> list[dict[str, Any]]:
    """Normalize raw alternative entries into a stable {action, chosen} shape."""
    summarized: list[dict[str, Any]] = []
    for alternative in alternatives or []:
        if isinstance(alternative, dict):
            action = (
                alternative.get("action")
                or alternative.get("description")
                or alternative.get("name")
                or alternative.get("option")
                or ""
            )
            summarized.append({"action": str(action), "chosen": bool(alternative.get("chosen", False))})
        else:
            summarized.append({"action": str(alternative), "chosen": False})
    return summarized


def _safe_rate(claims: list[dict[str, Any]], predicate) -> float:
    if not claims:
        return 0.0
    return sum(1 for claim in claims if predicate(claim)) / len(claims)


def _max_failure_severity(
    failures: list[dict[str, Any]],
    events: list[TraceEvent],
    causal: CausalAnalyzer,
) -> float:
    if not failures:
        return 0.0
    failure_ids = {failure["event_id"] for failure in failures if failure.get("event_id")}
    severities = [causal.severity(event) for event in events if event.id in failure_ids]
    return max(severities) if severities else 0.0


def _first_bad_decision(
    claims: list[dict[str, Any]], failures: list[dict[str, Any]]
) -> str | None:
    """Earliest decision that is unsupported/contradicted or blamed as a cause."""
    blamed = {failure.get("likely_cause_event_id") for failure in failures}
    blamed.discard(None)
    bad = [
        claim
        for claim in claims
        if claim["verification_status"] in {UNSUPPORTED, CONTRADICTED} or claim["event_id"] in blamed
    ]
    if not bad:
        return None
    return bad[0]["event_id"]


def _report_to_dict(report: SessionAuditReport) -> dict[str, Any]:
    return {
        "session_id": report.session_id,
        "objective": report.objective,
        "final_outcome": report.final_outcome,
        "questions": report.questions,
        "claims": report.claims,
        "signals": report.signals,
        "failures": report.failures,
        "critical_decisions": report.critical_decisions,
        "trust": report.trust,
        "review_points": report.review_points,
    }
