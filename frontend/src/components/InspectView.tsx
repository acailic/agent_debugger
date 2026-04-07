import { lazy, Suspense, useEffect, useState } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { useDerivedSessionData } from '../hooks/useDerivedSessionData'
import { useInspectEvent } from '../hooks/useInspectEvent'
import { useDriftData } from '../hooks/useDriftData'
import { ErrorBoundary } from './ErrorBoundary'
import { EmptyState } from './EmptyState'
import { DecisionTreeMemo } from './DecisionTree'
import { ConversationPanelMemo } from './ConversationPanel'
import { DriftAlertsPanel } from './DriftAlertsPanel'
import { FailureClusterPanelMemo } from './FailureClusterPanel'
import { LLMViewer } from './LLMViewer'
import { LiveDashboard } from './LiveDashboard'
import { MultiAgentCoordinationPanelMemo } from './MultiAgentCoordinationPanel'
import { ToolInspector } from './ToolInspector'
import { CheckpointSnapshot } from './CheckpointSnapshot'

const SessionComparisonPanel = lazy(() =>
  import('./SessionComparisonPanel').then((m) => ({ default: m.SessionComparisonPanel })),
)

export function InspectView() {
  const derived = useDerivedSessionData()
  const handleInspectEvent = useInspectEvent(derived.displayEvents)
  useDriftData()

  // Local state for collapsible sections
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({})

  // Store subscriptions
  const {
    selectedSessionId,
    selectedEventId,
    selectedCheckpointId,
    liveSummary,
    streamConnected,
    liveEvents,
    compareLoading,
    driftData,
    driftLoading,
    replay,
    bundle,
    secondaryBundle,
    sessions,
    secondarySessionId,
  } = useSessionStore(
    (state) => ({
      selectedSessionId: state.selectedSessionId,
      selectedEventId: state.selectedEventId,
      selectedCheckpointId: state.selectedCheckpointId,
      liveSummary: state.liveSummary,
      streamConnected: state.streamConnected,
      liveEvents: state.liveEvents,
      compareLoading: state.compareLoading,
      driftData: state.driftData,
      driftLoading: state.driftLoading,
      replay: state.replay,
      bundle: state.bundle,
      secondaryBundle: state.secondaryBundle,
      sessions: state.sessions,
      secondarySessionId: state.secondarySessionId,
    }),
  )

  const {
    setSelectedEventId,
    setSelectedSessionId,
    setSecondarySessionId,
    setSelectedCheckpointId,
    setReplayMode,
  } = useSessionStore(
    (state) => ({
      setSelectedEventId: state.setSelectedEventId,
      setSelectedSessionId: state.setSelectedSessionId,
      setSecondarySessionId: state.setSecondarySessionId,
      setSelectedCheckpointId: state.setSelectedCheckpointId,
      setReplayMode: state.setReplayMode,
    }),
  )

  // Auto-select default checkpoint when bundle/replay changes
  useEffect(() => {
    const defaultCheckpointId =
      bundle?.analysis.checkpoint_rankings[0]?.checkpoint_id ??
      replay?.nearest_checkpoint?.id ??
      bundle?.checkpoints[0]?.id ??
      null
    const currentCheckpointId = useSessionStore.getState().selectedCheckpointId
    if (currentCheckpointId && derived.checkpointLookup.has(currentCheckpointId)) {
      return
    }
    setSelectedCheckpointId(defaultCheckpointId)
  }, [
    bundle?.analysis.checkpoint_rankings,
    bundle?.checkpoints,
    derived.checkpointLookup,
    replay?.nearest_checkpoint?.id,
    setSelectedCheckpointId,
  ])

  return (
    <main className="workspace workspace--inspect slide-up">
      <section className="main-stage">
        {!selectedSessionId ? (
          <EmptyState
            icon="&#128300;"
            title="No session selected"
            description="Go to the Trace tab and select a session to inspect its decision tree, checkpoints, and behavior alerts."
          />
        ) : null}
        <div className="trace-layout" style={selectedSessionId ? undefined : { opacity: 0.3, pointerEvents: 'none' as const }}>
          <ErrorBoundary>
            <div className="panel panel--primary timeline-panel">
              <DecisionTreeMemo
                tree={bundle?.tree ?? null}
                selectedEventId={selectedEventId}
                onSelectEvent={setSelectedEventId}
              />
            </div>
          </ErrorBoundary>
        </div>

        <div className="inspect-grid">
          {/* Analysis Group: Inspectors + Conversation + Comparison */}
          <div
            className={`inspect-section-divider ${collapsedSections['analysis'] ? 'collapsed' : ''}`}
            onClick={() => setCollapsedSections((prev: Record<string, boolean>) => ({ ...prev, analysis: !prev.analysis }))}
          >
            <span className="inspect-section-label">Analysis</span>
          </div>

          <div data-section="analysis" data-section-hidden={collapsedSections['analysis'] ? 'true' : 'false'}>
            <ErrorBoundary>
              <section className="panel panel--primary">
                <div className="inspectors-grid">
                  <div className="inspector-wrapper">
                    <span className="inspector-label">Tool Inspector</span>
                    <ToolInspector event={derived.toolEvent} />
                  </div>
                  <div className="inspector-separator" />
                  <div className="inspector-wrapper">
                    <span className="inspector-label">LLM Viewer</span>
                    <LLMViewer request={derived.llmRequest} response={derived.llmResponse} />
                  </div>
                </div>
              </section>

              <section className="panel panel--secondary">
                <ConversationPanelMemo
                  events={derived.mergedSessionEvents}
                  selectedEventId={selectedEventId}
                  onSelectEvent={handleInspectEvent}
                />
              </section>

              <section className="panel panel--secondary">
                <Suspense fallback={<div className="loading-placeholder fade-in">Loading comparison...</div>}>
                  {compareLoading && (
                    <div className="comparison-loading-state">
                      <div className="loading-spinner" />
                      <p>Loading comparison session...</p>
                      <small>This may take a moment for large sessions</small>
                    </div>
                  )}
                  <SessionComparisonPanel
                    primaryBundle={bundle}
                    secondaryBundle={secondaryBundle}
                    sessions={sessions}
                    selectedSessionId={selectedSessionId}
                    secondarySessionId={secondarySessionId}
                    compareLoading={compareLoading}
                    onSelectSecondarySession={setSecondarySessionId}
                  />
                </Suspense>
              </section>
            </ErrorBoundary>
          </div>

          {/* Monitoring Group: Live Dashboard + Checkpoints + Alerts */}
          <div
            className={`inspect-section-divider ${collapsedSections['monitoring'] ? 'collapsed' : ''}`}
            onClick={() =>
              setCollapsedSections((prev: Record<string, boolean>) => ({ ...prev, monitoring: !prev.monitoring }))
            }
          >
            <span className="inspect-section-label">Monitoring</span>
          </div>

          <div data-section="monitoring" data-section-hidden={collapsedSections['monitoring'] ? 'true' : 'false'}>
            <ErrorBoundary>
              <section className="panel panel--secondary">
                <LiveDashboard
                  session={derived.currentSession}
                  events={derived.mergedSessionEvents}
                  checkpoints={bundle?.checkpoints ?? []}
                  liveSummary={liveSummary}
                  isConnected={streamConnected}
                  liveEventCount={liveEvents.length}
                  onSelectEvent={handleInspectEvent}
                />
              </section>

              <section className="panel panel--secondary">
                <div className="panel-head">
                  <p className="eyebrow">Checkpoint Ranking</p>
                  <h2>Restore candidates</h2>
                </div>
                <div className="checkpoint-list">
                  {bundle?.analysis.checkpoint_rankings.slice(0, 5).map((ranking) => {
                    const checkpoint = derived.checkpointLookup.get(ranking.checkpoint_id)
                    if (!checkpoint) return null
                    return (
                      <button
                        key={ranking.checkpoint_id}
                        type="button"
                        className={`checkpoint-card ${selectedCheckpointId === checkpoint.id ? 'active' : ''}`}
                        data-tier={ranking.retention_tier.replace('tier-', '')}
                        onClick={() => setSelectedCheckpointId(checkpoint.id)}
                      >
                        <span>Sequence {checkpoint.sequence}</span>
                        <strong>Restore {ranking.restore_value.toFixed(2)}</strong>
                        <small>Replay {ranking.replay_value.toFixed(2)}</small>
                        <small>{ranking.retention_tier}</small>
                      </button>
                    )
                  }) ?? <p>No checkpoints captured.</p>}
                </div>
                {derived.selectedCheckpoint && (
                  <>
                    <div className="checkpoint-actions">
                      <button
                        type="button"
                        onClick={() => {
                          handleInspectEvent(derived.selectedCheckpoint!.event_id)
                          setReplayMode('focus')
                        }}
                      >
                        Focus replay
                      </button>
                      <button type="button" onClick={() => handleInspectEvent(derived.selectedCheckpoint!.event_id)}>
                        Inspect event
                      </button>
                    </div>
                    {derived.selectedCheckpointRanking && (
                      <div className="analysis-strip">
                        <span>Restore {derived.selectedCheckpointRanking.restore_value.toFixed(2)}</span>
                        <span>Replay {derived.selectedCheckpointRanking.replay_value.toFixed(2)}</span>
                        <span>Importance {derived.selectedCheckpointRanking.importance.toFixed(2)}</span>
                        <span>Tier {derived.selectedCheckpointRanking.retention_tier}</span>
                      </div>
                    )}
                    <div className="checkpoint-compare-grid">
                      <CheckpointSnapshot title="Selected checkpoint" checkpoint={derived.selectedCheckpoint} variant="selected" />
                      {replay?.nearest_checkpoint && replay.nearest_checkpoint.id !== derived.selectedCheckpoint.id ? (
                        <CheckpointSnapshot title="Replay anchor" checkpoint={replay.nearest_checkpoint} variant="anchor" />
                      ) : null}
                    </div>
                  </>
                )}
              </section>

              <section className="panel alerts-panel">
                <div className="panel-head">
                  <p className="eyebrow">Behavior Alerts</p>
                  <h2>
                    Live heuristics
                    {bundle?.analysis?.behavior_alerts && bundle.analysis.behavior_alerts.length > 0 && (
                      <span className="alert-badge">{bundle.analysis.behavior_alerts.length}</span>
                    )}
                  </h2>
                </div>
                <div className="alert-list">
                  {bundle?.analysis?.behavior_alerts?.length ? (
                    bundle.analysis.behavior_alerts.map((alert) => (
                      <button
                        key={`${alert.alert_type}-${alert.event_id}`}
                        type="button"
                        className="alert-row"
                        data-severity={alert.severity.toLowerCase()}
                        onClick={() => handleInspectEvent(alert.event_id)}
                      >
                        <span>{alert.alert_type}</span>
                        <strong>{alert.severity}</strong>
                        <small>{alert.signal}</small>
                      </button>
                    ))
                  ) : (
                    <div className="empty-state">
                      <div className="empty-state-icon">&#128269;</div>
                      <h3>All clear</h3>
                      <p>No oscillation, looping, or confidence drops detected.</p>
                      <small>Alerts appear here when behavior patterns need attention</small>
                    </div>
                  )}
                </div>
              </section>

              <DriftAlertsPanel
                agentName={derived.currentSession?.agent_name ?? null}
                driftData={driftData}
                loading={driftLoading}
              />
            </ErrorBoundary>
          </div>

          {/* Intelligence Group: Failure Clusters + Coordination */}
          <div
            className={`inspect-section-divider ${collapsedSections['intelligence'] ? 'collapsed' : ''}`}
            onClick={() =>
              setCollapsedSections((prev: Record<string, boolean>) => ({ ...prev, intelligence: !prev.intelligence }))
            }
          >
            <span className="inspect-section-label">Intelligence</span>
          </div>

          <div data-section="intelligence" data-section-hidden={collapsedSections['intelligence'] ? 'true' : 'false'}>
            <ErrorBoundary>
              <section className="panel panel--accent failure-cluster-panel">
                <FailureClusterPanelMemo
                  clusters={[]}
                  onSelectSession={setSelectedSessionId}
                  selectedSessionId={selectedSessionId}
                  analysisClusters={bundle?.analysis.failure_clusters ?? []}
                  events={derived.mergedSessionEvents}
                />
              </section>

              <section className="panel panel--accent coordination-panel">
                <MultiAgentCoordinationPanelMemo bundle={bundle} />
              </section>
            </ErrorBoundary>
          </div>
        </div>
      </section>
    </main>
  )
}
