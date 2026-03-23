import { useMemo } from 'react'
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
  const promptPolicies = useMemo(
    () => events.filter((event) => event.event_type === 'prompt_policy'),
    [events],
  )
  const agentTurns = useMemo(
    () => events.filter((event) => event.event_type === 'agent_turn'),
    [events],
  )

  const conversationEntries = useMemo(
    () =>
      events
        .filter((event) => event.event_type === 'agent_turn' || event.event_type === 'prompt_policy')
        .map((event) => {
          const activePolicy = [...promptPolicies]
            .reverse()
            .find((policy) => {
              if (policy.timestamp > event.timestamp) return false
              if (!event.speaker) return true
              return !policy.speaker || policy.speaker === event.speaker
            }) ?? null

          return {
            event,
            activePolicy,
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

      <div className="conversation-list">
        {conversationEntries.length ? (
          conversationEntries.map(({ event, activePolicy }) => {
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
                {isPromptPolicy ? (
                  <pre>{JSON.stringify(event.policy_parameters ?? {}, null, 2)}</pre>
                ) : activePolicy ? (
                  <div className="policy-inline">
                    <span>Policy</span>
                    <strong>{activePolicy.template_id ?? activePolicy.name}</strong>
                    <small>{activePolicy.speaker || 'shared'}</small>
                  </div>
                ) : null}
              </button>
            )
          })
        ) : (
          <div className="empty-panel">
            <p>No multi-agent turns or prompt-policy events captured yet.</p>
          </div>
        )}
      </div>
    </div>
  )
}
