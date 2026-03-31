import { useMemo, useState, useCallback, memo } from 'react'
import type { TraceEvent } from '../types'

interface ConversationPanelProps {
  events: TraceEvent[]
  selectedEventId: string | null
  onSelectEvent: (eventId: string) => void
}

function formatEventTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function ConversationPanel({ events, selectedEventId, onSelectEvent }: ConversationPanelProps) {
  const [speakerFilter, setSpeakerFilter] = useState<string | null>(null)
  const [policyTemplateFilter, setPolicyTemplateFilter] = useState<string | null>(null)

  const promptPolicies = useMemo(
    () => events.filter((event) => event.event_type === 'prompt_policy'),
    [events],
  )
  const agentTurns = useMemo(
    () => events.filter((event) => event.event_type === 'agent_turn'),
    [events],
  )

  // Build enhanced conversation entries with policy shift detection and cross-agent influence
  const conversationEntries = useMemo(
    () =>
      events
        .filter((event) => event.event_type === 'agent_turn' || event.event_type === 'prompt_policy')
        .map((event, index, filteredEvents) => {
          const activePolicy = [...promptPolicies]
            .reverse()
            .find((policy) => {
              if (policy.timestamp > event.timestamp) return false
              if (!event.speaker) return true
              return !policy.speaker || policy.speaker === event.speaker
            }) ?? null

          // Detect policy shifts from previous entry
          let policyShift = null
          if (index > 0) {
            const prevEntry = filteredEvents[index - 1]
            const prevPolicy = [...promptPolicies]
              .reverse()
              .find((policy) => {
                if (policy.timestamp > prevEntry.timestamp) return false
                if (!prevEntry.speaker) return true
                return !policy.speaker || policy.speaker === prevEntry.speaker
              }) ?? null

            if (activePolicy?.template_id && prevPolicy?.template_id && activePolicy.template_id !== prevPolicy.template_id) {
              // Calculate magnitude based on parameter differences
              const magnitude = calculatePolicyShiftMagnitude(
                prevPolicy.policy_parameters ?? {},
                activePolicy.policy_parameters ?? {}
              )
              policyShift = {
                previousTemplate: prevPolicy.template_id,
                newTemplate: activePolicy.template_id,
                magnitude,
              }
            }
          }

          // Detect cross-agent influences (when an event references another agent's events)
          const crossAgentInfluences: Array<{
            agentId: string
            eventId: string
            influenceType: string
          }> = []
          if (event.related_event_ids) {
            event.related_event_ids.forEach((relatedId) => {
              const relatedEvent = events.find((e) => e.id === relatedId)
              if (relatedEvent && relatedEvent.agent_id && relatedEvent.agent_id !== event.agent_id) {
                crossAgentInfluences.push({
                  agentId: relatedEvent.agent_id,
                  eventId: relatedId,
                  influenceType: 'references',
                })
              }
            })
          }
          if (event.upstream_event_ids) {
            event.upstream_event_ids.forEach((upstreamId) => {
              const upstreamEvent = events.find((e) => e.id === upstreamId)
              if (upstreamEvent && upstreamEvent.agent_id && upstreamEvent.agent_id !== event.agent_id) {
                if (!crossAgentInfluences.some((inf) => inf.eventId === upstreamId)) {
                  crossAgentInfluences.push({
                    agentId: upstreamEvent.agent_id,
                    eventId: upstreamId,
                    influenceType: 'upstream',
                  })
                }
              }
            })
          }

          return {
            event,
            activePolicy,
            policyShift,
            crossAgentInfluences: crossAgentInfluences.length > 0 ? crossAgentInfluences : undefined,
          }
        }),
    [events, promptPolicies],
  )

  const uniqueSpeakers = useMemo(
    () =>
      Array.from(
        new Set(
          agentTurns
            .map((event) => event.speaker ?? event.agent_id ?? '')
            .filter(Boolean),
        ),
      ),
    [agentTurns],
  )

  const uniquePolicyTemplates = useMemo(
    () =>
      Array.from(
        new Set(
          promptPolicies
            .map((event) => event.template_id ?? '')
            .filter(Boolean),
        ),
      ),
    [promptPolicies],
  )

  // Filter entries based on selected filters
  const filteredEntries = useMemo(
    () =>
      conversationEntries.filter((entry) => {
        if (speakerFilter && entry.event.speaker !== speakerFilter && entry.event.agent_id !== speakerFilter) {
          return false
        }
        if (policyTemplateFilter && entry.activePolicy?.template_id !== policyTemplateFilter) {
          return false
        }
        return true
      }),
    [conversationEntries, speakerFilter, policyTemplateFilter],
  )

  const handleSpeakerFilterToggle = useCallback((speaker: string) => {
    setSpeakerFilter((prev) => (prev === speaker ? null : speaker))
  }, [])

  const handlePolicyFilterToggle = useCallback((template: string) => {
    setPolicyTemplateFilter((prev) => (prev === template ? null : template))
  }, [])

  return (
    <div className="conversation-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Coordination</p>
          <h2>Conversation and policy</h2>
        </div>
        <div className="conversation-metrics">
          <span>{agentTurns.length} turns</span>
          <span>{promptPolicies.length} prompt policies</span>
          <span>{uniqueSpeakers.length} speakers</span>
        </div>
      </div>

      {/* Speaker Filter */}
      {uniqueSpeakers.length > 0 && (
        <div className="speaker-filter">
          <span className="filter-label">Filter by speaker:</span>
          {uniqueSpeakers.map((speaker) => (
            <button
              key={speaker}
              type="button"
              className={`filter-pill ${speakerFilter === speaker ? 'active' : ''}`}
              onClick={() => handleSpeakerFilterToggle(speaker)}
            >
              {speaker}
            </button>
          ))}
        </div>
      )}

      {/* Policy Template Filter */}
      {uniquePolicyTemplates.length > 0 && (
        <div className="policy-filter">
          <span className="filter-label">Filter by policy:</span>
          {uniquePolicyTemplates.map((template) => (
            <button
              key={template}
              type="button"
              className={`filter-pill ${policyTemplateFilter === template ? 'active' : ''}`}
              onClick={() => handlePolicyFilterToggle(template)}
            >
              {template}
            </button>
          ))}
        </div>
      )}

      <div className="speaker-strip">
        {uniqueSpeakers.length ? (
          uniqueSpeakers.map((speaker) => (
            <span key={speaker} className="speaker-pill">
              {speaker}
            </span>
          ))
        ) : (
          <span className="speaker-pill muted">No agent turns captured</span>
        )}
      </div>

      <div className={`conversation-list ${filteredEntries.length <= 3 ? 'conversation-list--single' : ''}`}>
        {filteredEntries.length ? (
          filteredEntries.map(({ event, activePolicy, policyShift, crossAgentInfluences }) => {
            const isPromptPolicy = event.event_type === 'prompt_policy'
            const headline = isPromptPolicy
              ? event.template_id ?? event.name
              : event.speaker ?? event.agent_id ?? event.name
            const subhead = isPromptPolicy
              ? event.goal ?? 'Prompt policy update'
              : event.goal ?? event.name

            return (
              <button
                key={event.id}
                type="button"
                className={`conversation-row ${event.id === selectedEventId ? 'active' : ''} ${event.event_type}`}
                onClick={() => onSelectEvent(event.id)}
              >
                <div className="conversation-row-head">
                  <span className={`conversation-chip ${event.event_type}`}>{event.event_type.replaceAll('_', ' ')}</span>
                  <span className="conversation-time">{formatEventTime(event.timestamp)}</span>
                </div>
                <strong>{headline}</strong>
                <p>{subhead}</p>
                {event.content ? <pre>{event.content}</pre> : null}

                {/* Policy template badge */}
                {activePolicy?.template_id && (
                  <div className="policy-badge">
                    <span>📋 {activePolicy.template_id}</span>
                    {activePolicy.speaker && <small>({activePolicy.speaker})</small>}
                  </div>
                )}

                {/* Policy shift indicator */}
                {policyShift && (
                  <div className="policy-shift-indicator">
                    <span>🔄 Policy shift:</span>
                    <span className="shift-from">{policyShift.previousTemplate}</span>
                    <span>→</span>
                    <span className="shift-to">{policyShift.newTemplate}</span>
                    <span className="shift-magnitude">({policyShift.magnitude.toFixed(2)})</span>
                  </div>
                )}

                {/* Cross-agent influence markers */}
                {crossAgentInfluences && crossAgentInfluences.length > 0 && (
                  <div className="conversation-row-meta">
                    {crossAgentInfluences.map((influence, idx) => (
                      <span key={idx} className="influence-marker">
                        🔗 {influence.agentId} ({influence.influenceType})
                      </span>
                    ))}
                  </div>
                )}

                {/* Policy parameters for prompt policy events */}
                {isPromptPolicy ? (
                  <pre>{JSON.stringify(event.policy_parameters ?? {}, null, 2)}</pre>
                ) : null}

                {/* Turn-level goals for agent turns */}
                {!isPromptPolicy && event.goal && (
                  <div className="turn-goal">
                    <small>Goal:</small>
                    <span>{event.goal}</span>
                  </div>
                )}
              </button>
            )
          })
        ) : (
          <div className="empty-panel">
            <p>{speakerFilter || policyTemplateFilter ? 'No matching conversation entries.' : 'No multi-agent turns or prompt-policy events captured yet.'}</p>
          </div>
        )}
      </div>
    </div>
  )
}

// Custom comparison for ConversationPanel
function arePropsEqual(
  prevProps: Readonly<ConversationPanelProps>,
  nextProps: Readonly<ConversationPanelProps>
): boolean {
  return (
    prevProps.selectedEventId === nextProps.selectedEventId &&
    prevProps.events === nextProps.events
  )
}

export const ConversationPanelMemo = memo(ConversationPanel, arePropsEqual)

/**
 * Calculate the magnitude of a policy shift by comparing parameter differences.
 * Returns a value between 0 and 1, where higher values indicate larger shifts.
 */
function calculatePolicyShiftMagnitude(
  prevParams: Record<string, unknown>,
  newParams: Record<string, unknown>
): number {
  const allKeys = new Set([...Object.keys(prevParams), ...Object.keys(newParams)])
  if (allKeys.size === 0) return 0

  let totalDifference = 0
  let maxPossibleDifference = 0

  allKeys.forEach((key) => {
    const prevValue = JSON.stringify(prevParams[key])
    const newValue = JSON.stringify(newParams[key])

    // Simple string-based difference calculation
    if (prevValue !== newValue) {
      const maxLength = Math.max(prevValue.length, newValue.length)
      if (maxLength > 0) {
        // Levenshtein-like distance (simplified)
        const distance = Math.abs(prevValue.length - newValue.length)
        totalDifference += distance / maxLength
      }
      maxPossibleDifference += 1
    }
  })

  return maxPossibleDifference > 0 ? totalDifference / maxPossibleDifference : 0
}
