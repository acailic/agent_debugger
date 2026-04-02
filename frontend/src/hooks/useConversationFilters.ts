import { useMemo, useState, useCallback } from 'react'
import type { TraceEvent } from '../types'

interface UseConversationFiltersResult {
  speakerFilter: string | null
  policyTemplateFilter: string | null
  filteredEntries: Array<{
    event: TraceEvent
    activePolicy: TraceEvent | null
    policyShift: {
      previousTemplate: string
      newTemplate: string
      magnitude: number
    } | null
    crossAgentInfluences?: Array<{
      agentId: string
      eventId: string
      influenceType: string
    }>
  }>
  uniqueSpeakers: string[]
  uniquePolicyTemplates: string[]
  promptPolicies: TraceEvent[]
  agentTurns: TraceEvent[]
  handleSpeakerFilterToggle: (speaker: string) => void
  handlePolicyFilterToggle: (template: string) => void
}

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

/**
 * Custom hook for filtering and processing conversation entries.
 * Extracts complex filtering logic from ConversationPanel for better testability and reusability.
 */
export function useConversationFilters(events: TraceEvent[]): UseConversationFiltersResult {
  const [speakerFilter, setSpeakerFilter] = useState<string | null>(null)
  const [policyTemplateFilter, setPolicyTemplateFilter] = useState<string | null>(null)

  // Memoize base event filters
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

  // Extract unique speakers and templates
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

  // Apply filters
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

  return {
    speakerFilter,
    policyTemplateFilter,
    filteredEntries,
    uniqueSpeakers,
    uniquePolicyTemplates,
    promptPolicies,
    agentTurns,
    handleSpeakerFilterToggle,
    handlePolicyFilterToggle,
  }
}
