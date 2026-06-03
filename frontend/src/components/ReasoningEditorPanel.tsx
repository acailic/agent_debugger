import { useState, useEffect } from 'react'
import {
  editReasoning,
  createScenarioBranch,
  getHierarchicalReasoning,
  listScenarios,
  compareScenarios,
  exportScenario
} from '../api/client'
import type {
  EditOperation,
  ReasoningEdit,
  ScenarioBranch,
  HierarchicalReasoning,
  ScenarioComparison,
  TraceEvent
} from '../types'

interface ReasoningEditorPanelProps {
  sessionId: string | null
  events: TraceEvent[]
  onError?: (error: string) => void
  onSuccess?: (message: string) => void
}

type EditorTab = 'edit' | 'scenarios' | 'hierarchy' | 'compare' | 'replay'

function getOperationLabel(operation: EditOperation): string {
  return operation.charAt(0).toUpperCase() + operation.slice(1)
}

function getOperationColor(operation: EditOperation): string {
  switch (operation) {
    case 'modify':
      return '#3b82f6' // blue-500
    case 'insert':
      return '#22c55e' // green-500
    case 'delete':
      return '#ef4444' // red-500
    case 'replace':
      return '#f59e0b' // amber-500
    default:
      return '#6b7280' // gray-500
  }
}

export function ReasoningEditorPanel({
  sessionId,
  events,
  onError,
  onSuccess
}: ReasoningEditorPanelProps) {
  const [activeTab, setActiveTab] = useState<EditorTab>('edit')
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [selectedOperation, setSelectedOperation] = useState<EditOperation>('modify')
  const [fieldName, setFieldName] = useState('reasoning')
  const [newValue, setNewValue] = useState('')
  const [position, setPosition] = useState(-1)
  const [branchName, setBranchName] = useState('')
  const [branchDescription, setBranchDescription] = useState('')
  const [parentEventId, setParentEventId] = useState<string | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioBranch[]>([])
  const [hierarchicalReasoning, setHierarchicalReasoning] = useState<HierarchicalReasoning | null>(null)
  const [comparisonResults, setComparisonResults] = useState<ScenarioComparison | null>(null)
  const [selectedBranchIds, setSelectedBranchIds] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [editHistory, setEditHistory] = useState<ReasoningEdit[]>([])

  // Load scenarios when session is available
  useEffect(() => {
    if (!sessionId) {
      setScenarios([])
      return
    }

    const loadScenarios = async () => {
      try {
        const result = await listScenarios(sessionId)
        setScenarios(result.scenarios)
      } catch (err) {
        console.error('Failed to load scenarios:', err)
        setError(err instanceof Error ? err.message : 'Failed to load scenarios')
      }
    }

    loadScenarios()
  }, [sessionId])

  // Handle reasoning edit
  const handleEditReasoning = async () => {
    if (!sessionId || !selectedEventId) {
      setError('Please select an event to edit')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const result = await editReasoning(
        sessionId,
        selectedEventId,
        selectedOperation,
        fieldName,
        newValue,
        position
      )

      setEditHistory([result.edit, ...editHistory])
      setSuccessMessage(`Successfully edited event ${selectedEventId}`)
      setNewValue('')

      if (onSuccess) {
        onSuccess(`Reasoning edit applied: ${result.edit.operation} on ${result.edit.field_name}`)
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to edit reasoning'
      setError(errorMsg)
      if (onError) {
        onError(errorMsg)
      }
    } finally {
      setLoading(false)
    }
  }

  // Handle scenario branch creation
  const handleCreateBranch = async () => {
    if (!sessionId || !parentEventId) {
      setError('Please select a parent event for the branch')
      return
    }

    if (!branchName.trim()) {
      setError('Please enter a branch name')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const edits = editHistory.map(edit => ({
        event_id: edit.event_id,
        operation: edit.operation,
        field_name: edit.field_name,
        new_value: edit.new_value,
        position: edit.position
      }))

      const result = await createScenarioBranch(
        sessionId,
        branchName,
        parentEventId,
        branchDescription,
        edits
      )

      setScenarios([result.branch, ...scenarios])
      setSuccessMessage(`Scenario branch "${result.branch.name}" created successfully`)
      setBranchName('')
      setBranchDescription('')
      setEditHistory([])

      if (onSuccess) {
        onSuccess(`Scenario branch "${result.branch.name}" created`)
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to create branch'
      setError(errorMsg)
      if (onError) {
        onError(errorMsg)
      }
    } finally {
      setLoading(false)
    }
  }

  // Handle hierarchical reasoning view
  const handleLoadHierarchy = async () => {
    if (!sessionId || !selectedEventId) {
      setError('Please select an event to view hierarchical reasoning')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const result = await getHierarchicalReasoning(sessionId, selectedEventId)
      setHierarchicalReasoning(result.hierarchical_reasoning)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to load hierarchical reasoning'
      setError(errorMsg)
      if (onError) {
        onError(errorMsg)
      }
    } finally {
      setLoading(false)
    }
  }

  // Handle scenario comparison
  const handleCompareScenarios = async () => {
    if (!sessionId || selectedBranchIds.length < 2) {
      setError('Please select at least 2 scenarios to compare')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const result = await compareScenarios(sessionId, selectedBranchIds)
      setComparisonResults(result.comparison)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to compare scenarios'
      setError(errorMsg)
      if (onError) {
        onError(errorMsg)
      }
    } finally {
      setLoading(false)
    }
  }

  // Handle scenario export
  const handleExportScenario = async (branchId: string) => {
    if (!sessionId) return

    try {
      const result = await exportScenario(sessionId, branchId)
      const dataStr = JSON.stringify(result.exported_scenario, null, 2)
      const blob = new Blob([dataStr], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `scenario-${branchId}.json`
      a.click()
      URL.revokeObjectURL(url)

      if (onSuccess) {
        onSuccess(`Scenario ${branchId} exported successfully`)
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to export scenario'
      setError(errorMsg)
      if (onError) {
        onError(errorMsg)
      }
    }
  }

  if (!sessionId) {
    return (
      <div className="reasoning-editor-panel empty-panel">
        <p>Select a session to edit reasoning and manage scenarios.</p>
      </div>
    )
  }

  return (
    <div className="reasoning-editor-panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Reasoning Editor</p>
          <h2>Interactive CoT Editing</h2>
        </div>
      </div>

      {/* Editor Tabs */}
      <div className="editor-tabs">
        <button
          className={`tab-button ${activeTab === 'edit' ? 'active' : ''}`}
          onClick={() => setActiveTab('edit')}
        >
          Edit Reasoning
        </button>
        <button
          className={`tab-button ${activeTab === 'scenarios' ? 'active' : ''}`}
          onClick={() => setActiveTab('scenarios')}
        >
          Scenarios ({scenarios.length})
        </button>
        <button
          className={`tab-button ${activeTab === 'hierarchy' ? 'active' : ''}`}
          onClick={() => setActiveTab('hierarchy')}
        >
          Hierarchy
        </button>
        <button
          className={`tab-button ${activeTab === 'compare' ? 'active' : ''}`}
          onClick={() => setActiveTab('compare')}
        >
          Compare
        </button>
      </div>

      {/* Edit Tab */}
      {activeTab === 'edit' && (
        <div className="edit-content">
          <div className="edit-controls">
            <div className="control-group">
              <label>Select Event:</label>
              <select
                value={selectedEventId || ''}
                onChange={(e) => setSelectedEventId(e.target.value || null)}
              >
                <option value="">Select an event...</option>
                {events.map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.name || event.id} - {event.event_type}
                  </option>
                ))}
              </select>
            </div>

            <div className="control-group">
              <label>Operation:</label>
              <select
                value={selectedOperation}
                onChange={(e) => setSelectedOperation(e.target.value as EditOperation)}
              >
                <option value="modify">Modify</option>
                <option value="insert">Insert</option>
                <option value="delete">Delete</option>
                <option value="replace">Replace</option>
              </select>
            </div>

            <div className="control-group">
              <label>Field Name:</label>
              <input
                type="text"
                value={fieldName}
                onChange={(e) => setFieldName(e.target.value)}
                placeholder="reasoning"
              />
            </div>

            {selectedOperation === 'insert' && (
              <div className="control-group">
                <label>Position:</label>
                <input
                  type="number"
                  value={position}
                  onChange={(e) => setPosition(parseInt(e.target.value) || -1)}
                  placeholder="-1 for end, -2 for beginning"
                />
              </div>
            )}

            {selectedOperation !== 'delete' && (
              <div className="control-group">
                <label>New Value:</label>
                <textarea
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  placeholder="Enter new reasoning content..."
                  rows={4}
                />
              </div>
            )}

            <button
              className="btn-primary"
              onClick={handleEditReasoning}
              disabled={loading || !selectedEventId}
            >
              {loading ? 'Applying Edit...' : 'Apply Edit'}
            </button>
          </div>

          {/* Edit History */}
          {editHistory.length > 0 && (
            <div className="edit-history">
              <h3>Edit History</h3>
              <div className="edit-list">
                {editHistory.map((edit) => (
                  <div key={edit.edit_id} className="edit-item">
                    <span
                      className="operation-badge"
                      style={{ backgroundColor: getOperationColor(edit.operation) }}
                    >
                      {getOperationLabel(edit.operation)}
                    </span>
                    <span className="event-id">{edit.event_id}</span>
                    <span className="field-name">{edit.field_name}</span>
                    <span className="timestamp">{new Date(edit.created_at).toLocaleTimeString()}</span>
                  </div>
                ))}
              </div>

              {/* Create Branch from Edits */}
              <div className="branch-creation">
                <h4>Create Scenario Branch from Edits</h4>
                <div className="control-group">
                  <label>Branch Name:</label>
                  <input
                    type="text"
                    value={branchName}
                    onChange={(e) => setBranchName(e.target.value)}
                    placeholder="Enter branch name..."
                  />
                </div>
                <div className="control-group">
                  <label>Parent Event ID:</label>
                  <select
                    value={parentEventId || ''}
                    onChange={(e) => setParentEventId(e.target.value || null)}
                  >
                    <option value="">Select parent event...</option>
                    {events.map((event) => (
                      <option key={event.id} value={event.id}>
                        {event.name || event.id}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="control-group">
                  <label>Description:</label>
                  <textarea
                    value={branchDescription}
                    onChange={(e) => setBranchDescription(e.target.value)}
                    placeholder="Describe what this branch changes..."
                    rows={2}
                  />
                </div>
                <button
                  className="btn-secondary"
                  onClick={handleCreateBranch}
                  disabled={loading || !branchName || !parentEventId}
                >
                  {loading ? 'Creating Branch...' : 'Create Branch'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Scenarios Tab */}
      {activeTab === 'scenarios' && (
        <div className="scenarios-content">
          <h3>Scenario Branches</h3>
          {scenarios.length === 0 ? (
            <p className="empty-state">No scenario branches created yet. Create one from the Edit tab.</p>
          ) : (
            <div className="scenario-list">
              {scenarios.map((scenario) => (
                <div key={scenario.branch_id} className="scenario-item">
                  <div className="scenario-header">
                    <h4>{scenario.name}</h4>
                    <button
                      className="btn-small"
                      onClick={() => handleExportScenario(scenario.branch_id)}
                    >
                      Export
                    </button>
                  </div>
                  <p className="scenario-description">{scenario.description}</p>
                  <div className="scenario-meta">
                    <span>Parent Event: {scenario.parent_event_id}</span>
                    <span>Edits: {scenario.edits.length}</span>
                    <span>Created: {new Date(scenario.created_at).toLocaleString()}</span>
                  </div>
                  {scenario.edits.length > 0 && (
                    <div className="scenario-edits">
                      <strong>Applied Edits:</strong>
                      {scenario.edits.map((edit) => (
                        <div key={edit.edit_id} className="edit-summary">
                          <span
                            className="operation-badge"
                            style={{ backgroundColor: getOperationColor(edit.operation) }}
                          >
                            {getOperationLabel(edit.operation)}
                          </span>
                          <span>{edit.field_name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Hierarchy Tab */}
      {activeTab === 'hierarchy' && (
        <div className="hierarchy-content">
          <div className="hierarchy-controls">
            <button
              className="btn-primary"
              onClick={handleLoadHierarchy}
              disabled={loading || !selectedEventId}
            >
              {loading ? 'Loading Hierarchy...' : 'Load Hierarchy'}
            </button>
          </div>

          {hierarchicalReasoning && (
            <div className="hierarchical-display">
              <h3>Hierarchical Reasoning Structure</h3>
              {hierarchicalReasoning.topics.length > 0 ? (
                <div className="topics-tree">
                  {hierarchicalReasoning.topics.map((topic, index) => (
                    <div key={index} className="topic-node">
                      <h4>{topic.title}</h4>
                      {topic.content.length > 0 && (
                        <div className="topic-content">
                          {topic.content.map((line, lineIndex) => (
                            <p key={lineIndex}>{line}</p>
                          ))}
                        </div>
                      )}
                      {topic.subtopics.length > 0 && (
                        <div className="subtopics">
                          <strong>Subtopics:</strong>
                          {topic.subtopics.map((subtopic, subIndex) => (
                            <div key={subIndex} className="subtopic-item">
                              {JSON.stringify(subtopic)}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty-state">
                  No hierarchical structure found. Raw reasoning available.
                </p>
              )}
              <div className="raw-reasoning">
                <h4>Raw Reasoning</h4>
                <pre>{hierarchicalReasoning.raw}</pre>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Compare Tab */}
      {activeTab === 'compare' && (
        <div className="compare-content">
          <h3>Compare Scenarios</h3>
          <div className="compare-controls">
            <label>Select Scenarios to Compare:</label>
            <div className="scenario-selector">
              {scenarios.map((scenario) => (
                <label key={scenario.branch_id} className="scenario-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedBranchIds.includes(scenario.branch_id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedBranchIds([...selectedBranchIds, scenario.branch_id])
                      } else {
                        setSelectedBranchIds(selectedBranchIds.filter(id => id !== scenario.branch_id))
                      }
                    }}
                  />
                  {scenario.name}
                </label>
              ))}
            </div>
            <button
              className="btn-primary"
              onClick={handleCompareScenarios}
              disabled={loading || selectedBranchIds.length < 2}
            >
              {loading ? 'Comparing...' : 'Compare Selected'}
            </button>
          </div>

          {comparisonResults && (
            <div className="comparison-results">
              <h4>Comparison Results</h4>
              <div className="branches-summary">
                <strong>Branches Compared:</strong>
                {comparisonResults.branches.map((branch) => (
                  <div key={branch.id} className="branch-summary">
                    <span>{branch.name}</span>
                    <span>{branch.edit_count} edits</span>
                  </div>
                ))}
              </div>

              {comparisonResults.differences.length > 0 && (
                <div className="differences-list">
                  <strong>Differences:</strong>
                  {comparisonResults.differences.map((diff, index) => (
                    <div key={index} className="difference-item">
                      <span>Branch A: {diff.branch_a}</span>
                      <span>Branch B: {diff.branch_b}</span>
                      <span>Edit Difference: {diff.edit_difference}</span>
                      <span>Shared Parent: {diff.shared_parent ? 'Yes' : 'No'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Status Messages */}
      {error && (
        <div className="error-message">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {successMessage && (
        <div className="success-message">
          {successMessage}
          <button onClick={() => setSuccessMessage(null)}>×</button>
        </div>
      )}
    </div>
  )
}