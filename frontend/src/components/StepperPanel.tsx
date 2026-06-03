import { useState, useEffect } from 'react'
import {
  setBreakpoint,
  clearBreakpoint,
  clearAllBreakpoints,
  listBreakpoints,
  stepExecution,
  getStepperState,
  createBranch,
  listBranches,
  deleteBranch,
  resetStepper,
} from '../api/client'
import type {
  Breakpoint,
  BreakpointType,
  BranchPoint,
  StepperState,
  AgentState,
  StepAction,
} from '../types'

interface StepperPanelProps {
  sessionId: string | null
}

function getBreakpointTypeColor(type: BreakpointType): string {
  switch (type) {
    case 'event_type':
      return '#8b5cf6' // violet-500
    case 'tool_name':
      return '#06b6d4' // cyan-500
    case 'confidence_threshold':
      return '#ec4899' // pink-500
    case 'safety_outcome':
      return '#f59e0b' // amber-500
    case 'custom_condition':
      return '#10b981' // emerald-500
    case 'event_id':
      return '#ef4444' // red-500
    default:
      return '#6b7280' // gray-500
  }
}

export function StepperPanel({ sessionId }: StepperPanelProps) {
  const [activeTab, setActiveTab] = useState<'breakpoints' | 'step' | 'state' | 'branches'>('breakpoints')
  const [breakpoints, setBreakpoints] = useState<Breakpoint[]>([])
  const [branches, setBranches] = useState<BranchPoint[]>([])
  const [stepperState, setStepperState] = useState<StepperState | null>(null)
  const [agentState, setAgentState] = useState<AgentState | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Breakpoint form state
  const [breakpointType, setBreakpointType] = useState<BreakpointType>('event_type')
  const [conditionValue, setConditionValue] = useState('')
  const [description, setDescription] = useState('')

  // Load initial state when session changes
  useEffect(() => {
    if (!sessionId) {
      setBreakpoints([])
      setBranches([])
      setStepperState(null)
      setAgentState(null)
      setError(null)
      return
    }

    const loadState = async () => {
      setLoading(true)
      setError(null)
      try {
        const [bpList, branchList, stateResponse] = await Promise.all([
          listBreakpoints(sessionId),
          listBranches(sessionId),
          getStepperState(sessionId)
        ])
        setBreakpoints(bpList.breakpoints)
        setBranches(branchList.branches)
        setStepperState(stateResponse.stepper_state)
        setAgentState(stateResponse.agent_state)
      } catch (err) {
        console.error('Failed to load stepper state:', err)
        setError(err instanceof Error ? err.message : 'Failed to load stepper state')
      } finally {
        setLoading(false)
      }
    }

    loadState()
  }, [sessionId])

  const handleSetBreakpoint = async () => {
    if (!sessionId) return

    setLoading(true)
    setError(null)
    try {
      const response = await setBreakpoint(sessionId, breakpointType, conditionValue, description)
      setBreakpoints(response.stepper_state.breakpoints)
      setStepperState(response.stepper_state)
      setConditionValue('')
      setDescription('')
    } catch (err) {
      console.error('Failed to set breakpoint:', err)
      setError(err instanceof Error ? err.message : 'Failed to set breakpoint')
    } finally {
      setLoading(false)
    }
  }

  const handleClearBreakpoint = async (breakpointId: string) => {
    if (!sessionId) return

    try {
      const response = await clearBreakpoint(sessionId, breakpointId)
      setBreakpoints(response.stepper_state.breakpoints)
      setStepperState(response.stepper_state)
    } catch (err) {
      console.error('Failed to clear breakpoint:', err)
      setError(err instanceof Error ? err.message : 'Failed to clear breakpoint')
    }
  }

  const handleClearAllBreakpoints = async () => {
    if (!sessionId) return

    try {
      const response = await clearAllBreakpoints(sessionId)
      setBreakpoints(response.stepper_state.breakpoints)
      setStepperState(response.stepper_state)
    } catch (err) {
      console.error('Failed to clear all breakpoints:', err)
      setError(err instanceof Error ? err.message : 'Failed to clear all breakpoints')
    }
  }

  const handleStep = async (action: StepAction) => {
    if (!sessionId) return

    setLoading(true)
    setError(null)
    try {
      const response = await stepExecution(sessionId, action)
      setStepperState(response.step_result.state)
      if (response.step_result.current_event) {
        setAgentState({
          completed: false,
          current_position: response.step_result.state?.current_event_index || 0,
          total_events: response.step_result.state?.current_event_index || 0,
          current_event: response.step_result.current_event as any,
          events_count: response.step_result.state?.current_event_index || 0,
          breakpoints_active: breakpoints.filter(bp => bp.enabled).length,
          paused: response.step_result.state?.paused || true
        })
      }
    } catch (err) {
      console.error('Failed to step execution:', err)
      setError(err instanceof Error ? err.message : 'Failed to step execution')
    } finally {
      setLoading(false)
    }
  }

  const handleRefreshState = async () => {
    if (!sessionId) return

    try {
      const response = await getStepperState(sessionId)
      setStepperState(response.stepper_state)
      setAgentState(response.agent_state)
    } catch (err) {
      console.error('Failed to refresh state:', err)
      setError(err instanceof Error ? err.message : 'Failed to refresh state')
    }
  }

  const handleCreateBranch = async () => {
    if (!sessionId || !stepperState?.current_event_id) return

    const name = prompt('Enter branch name:')
    if (!name) return

    const description = prompt('Enter branch description (optional):') || ''

    try {
      const response = await createBranch(sessionId, name, stepperState.current_event_id, description)
      setBranches([...branches, response.branch])
    } catch (err) {
      console.error('Failed to create branch:', err)
      setError(err instanceof Error ? err.message : 'Failed to create branch')
    }
  }

  const handleDeleteBranch = async (branchId: string) => {
    if (!sessionId) return

    try {
      await deleteBranch(sessionId, branchId)
      setBranches(branches.filter(b => b.branch_id !== branchId))
    } catch (err) {
      console.error('Failed to delete branch:', err)
      setError(err instanceof Error ? err.message : 'Failed to delete branch')
    }
  }

  const handleReset = async () => {
    if (!sessionId) return

    if (!confirm('Reset stepper to initial state? All breakpoints and branches will be cleared.')) {
      return
    }

    try {
      const response = await resetStepper(sessionId)
      setStepperState(response.stepper_state)
      setBreakpoints(response.stepper_state.breakpoints)
      setBranches([])
    } catch (err) {
      console.error('Failed to reset stepper:', err)
      setError(err instanceof Error ? err.message : 'Failed to reset stepper')
    }
  }

  if (!sessionId) {
    return (
      <div className="stepper-panel empty-panel">
        <p>Select a session to start debugging.</p>
      </div>
    )
  }

  if (loading && !stepperState) {
    return (
      <div className="stepper-panel loading-panel">
        <p>Loading stepper state...</p>
      </div>
    )
  }

  if (error && !stepperState) {
    return (
      <div className="stepper-panel error-panel">
        <p className="error-message">Error: {error}</p>
      </div>
    )
  }

  return (
    <div className="stepper-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Agent Debugger</p>
          <h2>Interactive Stepper</h2>
        </div>
        <button className="button-secondary" onClick={handleReset}>
          Reset
        </button>
      </div>

      {/* Status indicators */}
      {stepperState && (
        <div className="stepper-status">
          <div className="status-item">
            <span className="label">Position:</span>
            <strong>{stepperState.current_event_index + 1} / {agentState?.total_events || '?'}</strong>
          </div>
          <div className="status-item">
            <span className="label">Status:</span>
            <strong className={stepperState.paused ? 'paused' : 'running'}>
              {stepperState.paused ? 'Paused' : 'Running'}
            </strong>
          </div>
          <div className="status-item">
            <span className="label">Breakpoints:</span>
            <strong>{breakpoints.filter(bp => bp.enabled).length} active</strong>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="analysis-tabs">
        <button
          className={`tab-button ${activeTab === 'breakpoints' ? 'active' : ''}`}
          onClick={() => setActiveTab('breakpoints')}
        >
          Breakpoints
        </button>
        <button
          className={`tab-button ${activeTab === 'step' ? 'active' : ''}`}
          onClick={() => setActiveTab('step')}
        >
          Step Controls
        </button>
        <button
          className={`tab-button ${activeTab === 'state' ? 'active' : ''}`}
          onClick={() => setActiveTab('state')}
        >
          State Inspector
        </button>
        <button
          className={`tab-button ${activeTab === 'branches' ? 'active' : ''}`}
          onClick={() => setActiveTab('branches')}
        >
          Branches ({branches.length})
        </button>
      </div>

      {/* Breakpoints Tab */}
      {activeTab === 'breakpoints' && (
        <div className="breakpoints-content">
          <div className="breakpoint-form">
            <h3>Set New Breakpoint</h3>
            <div className="form-row">
              <label>Type:</label>
              <select
                value={breakpointType}
                onChange={(e) => setBreakpointType(e.target.value as BreakpointType)}
              >
                <option value="event_type">Event Type</option>
                <option value="tool_name">Tool Name</option>
                <option value="confidence_threshold">Confidence Threshold</option>
                <option value="safety_outcome">Safety Outcome</option>
                <option value="custom_condition">Custom Condition</option>
                <option value="event_id">Event ID</option>
              </select>
            </div>
            <div className="form-row">
              <label>Condition:</label>
              <input
                type="text"
                value={conditionValue}
                onChange={(e) => setConditionValue(e.target.value)}
                placeholder="e.g., decision, search_tool, 0.5, pass"
              />
            </div>
            <div className="form-row">
              <label>Description:</label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Break on all decisions"
              />
            </div>
            <button className="button-primary" onClick={handleSetBreakpoint}>
              Set Breakpoint
            </button>
          </div>

          <div className="breakpoints-list">
            <div className="list-header">
              <h3>Active Breakpoints ({breakpoints.length})</h3>
              {breakpoints.length > 0 && (
                <button className="button-secondary" onClick={handleClearAllBreakpoints}>
                  Clear All
                </button>
              )}
            </div>
            {breakpoints.length === 0 ? (
              <p className="empty-message">No breakpoints set</p>
            ) : (
              <div className="breakpoint-items">
                {breakpoints.map(bp => (
                  <div key={bp.breakpoint_id} className="breakpoint-item">
                    <div className="breakpoint-info">
                      <span
                        className="breakpoint-type-badge"
                        style={{ backgroundColor: getBreakpointTypeColor(bp.breakpoint_type) }}
                      >
                        {bp.breakpoint_type.replace('_', ' ')}
                      </span>
                      <span className="breakpoint-condition">{String(bp.condition_value)}</span>
                      <span className="breakpoint-description">{bp.description}</span>
                    </div>
                    <div className="breakpoint-meta">
                      <small>Hit count: {bp.hit_count}</small>
                      <button
                        className="button-icon"
                        onClick={() => handleClearBreakpoint(bp.breakpoint_id)}
                        title="Clear breakpoint"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Step Controls Tab */}
      {activeTab === 'step' && (
        <div className="step-controls-content">
          <h3>Step Controls</h3>
          <div className="step-buttons">
            <button
              className="step-button"
              onClick={() => handleStep('step_into')}
              disabled={loading || stepperState?.completed}
            >
              <span className="step-icon">→</span>
              <span>Step Into</span>
              <small>Next decision</small>
            </button>
            <button
              className="step-button"
              onClick={() => handleStep('step_over')}
              disabled={loading || stepperState?.completed}
            >
              <span className="step-icon">⤷</span>
              <span>Step Over</span>
              <small>Skip tool internals</small>
            </button>
            <button
              className="step-button"
              onClick={() => handleStep('step_out')}
              disabled={loading || stepperState?.completed}
            >
              <span className="step-icon">←</span>
              <span>Step Out</span>
              <small>To parent context</small>
            </button>
            <button
              className="step-button primary"
              onClick={() => handleStep('continue')}
              disabled={loading || stepperState?.completed}
            >
              <span className="step-icon">▶</span>
              <span>Continue</span>
              <small>To next breakpoint</small>
            </button>
          </div>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          {stepperState?.step_history && stepperState.step_history.length > 0 && (
            <div className="step-history">
              <h4>Step History</h4>
              <div className="history-items">
                {stepperState.step_history.slice(-5).map((step, index) => (
                  <div key={index} className="history-item">
                    <small>{new Date(step.timestamp).toLocaleTimeString()}</small>
                    <span>{step.action}</span>
                    <small>Event {step.event_index + 1}</small>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* State Inspector Tab */}
      {activeTab === 'state' && (
        <div className="state-inspector-content">
          <div className="state-header">
            <h3>Agent State</h3>
            <button className="button-secondary" onClick={handleRefreshState}>
              Refresh
            </button>
          </div>

          {agentState?.completed ? (
            <div className="completion-message">
              <p>Execution completed</p>
            </div>
          ) : agentState?.current_event ? (
            <div className="state-details">
              <div className="state-section">
                <h4>Current Event</h4>
                <div className="state-grid">
                  <div className="state-item">
                    <span className="label">Event ID:</span>
                    <strong>{agentState.current_event.event_id}</strong>
                  </div>
                  <div className="state-item">
                    <span className="label">Type:</span>
                    <strong>{agentState.current_event.event_type}</strong>
                  </div>
                  <div className="state-item">
                    <span className="label">Name:</span>
                    <strong>{agentState.current_event.name}</strong>
                  </div>
                  {agentState.current_event.timestamp && (
                    <div className="state-item">
                      <span className="label">Timestamp:</span>
                      <strong>{new Date(agentState.current_event.timestamp).toLocaleString()}</strong>
                    </div>
                  )}
                  {agentState.current_event.confidence !== undefined && (
                    <div className="state-item">
                      <span className="label">Confidence:</span>
                      <strong>{agentState.current_event.confidence.toFixed(2)}</strong>
                    </div>
                  )}
                  {agentState.current_event.tool_name && (
                    <div className="state-item">
                      <span className="label">Tool:</span>
                      <strong>{agentState.current_event.tool_name}</strong>
                    </div>
                  )}
                </div>
              </div>

              {agentState.current_event.reasoning && (
                <div className="state-section">
                  <h4>Reasoning</h4>
                  <pre className="reasoning-content">{agentState.current_event.reasoning}</pre>
                </div>
              )}

              {Object.keys(agentState.current_event.data).length > 0 && (
                <div className="state-section">
                  <h4>Event Data</h4>
                  <pre className="data-content">
                    {JSON.stringify(agentState.current_event.data, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ) : (
            <p className="empty-message">No current event state</p>
          )}

          <div className="state-summary">
            <div className="summary-item">
              <span className="label">Position:</span>
              <strong>{agentState?.current_position || 0} / {agentState?.total_events || 0}</strong>
            </div>
            <div className="summary-item">
              <span className="label">Events Processed:</span>
              <strong>{agentState?.events_count || 0}</strong>
            </div>
            <div className="summary-item">
              <span className="label">Active Breakpoints:</span>
              <strong>{agentState?.breakpoints_active || 0}</strong>
            </div>
          </div>
        </div>
      )}

      {/* Branches Tab */}
      {activeTab === 'branches' && (
        <div className="branches-content">
          <div className="branches-header">
            <h3>Branch Points ({branches.length})</h3>
            <button
              className="button-primary"
              onClick={handleCreateBranch}
              disabled={!stepperState?.current_event_id}
            >
              Create Branch
            </button>
          </div>

          {branches.length === 0 ? (
            <p className="empty-message">
              {!stepperState?.current_event_id
                ? 'Step to an event first to create a branch'
                : 'No branches created yet'}
            </p>
          ) : (
            <div className="branch-items">
              {branches.map(branch => (
                <div key={branch.branch_id} className="branch-item">
                  <div className="branch-info">
                    <h4>{branch.name}</h4>
                    <p className="branch-description">{branch.description || 'No description'}</p>
                    <div className="branch-meta">
                      <small>Parent: {branch.parent_event_id}</small>
                      <small>Events: {branch.replay_events_count}</small>
                      <small>Created: {new Date(branch.created_at).toLocaleString()}</small>
                    </div>
                  </div>
                  <button
                    className="button-icon"
                    onClick={() => handleDeleteBranch(branch.branch_id)}
                    title="Delete branch"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {error && activeTab !== 'step' && (
        <div className="error-message">
          {error}
        </div>
      )}
    </div>
  )
}