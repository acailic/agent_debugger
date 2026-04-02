import { memo } from 'react'
import type { TraceEvent } from '../types'
import { useConversationFilters } from '../hooks/useConversationFilters'

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
  const {
    speakerFilter,
    policyTemplateFilter,
    filteredEntries,
    uniqueSpeakers,
    uniquePolicyTemplates,
    promptPolicies,
    agentTurns,
    handleSpeakerFilterToggle,
    handlePolicyFilterToggle,
  } = useConversationFilters(events)

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
