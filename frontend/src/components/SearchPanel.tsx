import { useMemo } from 'react'
import { searchTraces } from '../api/client'
import { formatEventHeadline, SEARCHABLE_EVENT_TYPES } from '../utils/formatting'
import { useSessionStore } from '../stores/sessionStore'
import type { SearchScope, TraceEvent } from '../types'
import './SearchPanel.css'

export function SearchPanel() {
  const {
    searchQuery,
    searchEventType,
    searchScope,
    searchResponse,
    searchLoading,
    searchError,
    selectedSessionId,
    sessions,
    setSearchQuery,
    setSearchEventType,
    setSearchScope,
    setSearchResponse,
    setSearchError,
    setSearchLoading,
    setReplayMode,
    setSelectedSessionId,
    setSelectedEventId,
  } = useSessionStore()

  const searchSessionLookup = useMemo(
    () => new Map(sessions.map((session) => [session.id, session])),
    [sessions],
  )

  async function runTraceSearch() {
    const trimmedQuery = searchQuery.trim()
    if (!trimmedQuery) {
      setSearchResponse(null)
      setSearchError(null)
      return
    }

    setSearchLoading(true)
    setSearchError(null)
    try {
      const response = await searchTraces({
        query: trimmedQuery,
        sessionId: searchScope === 'current' ? selectedSessionId : null,
        eventType: searchEventType || null,
        limit: 18,
      })
      setSearchResponse(response)
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Failed to search traces')
    } finally {
      setSearchLoading(false)
    }
  }

  function jumpToSearchResult(result: TraceEvent) {
    setReplayMode('full')
    if (result.session_id !== selectedSessionId) {
      setSelectedSessionId(result.session_id)
      setSelectedEventId(result.id)
      return
    }
    setSelectedEventId(result.id)
  }

  return (
    <section className="panel panel--secondary search-panel">
      <div className="search-head">
        <div>
          <p className="eyebrow">Trace Search</p>
          <h2>Find the exact moment</h2>
        </div>
        <button type="button" className="search-submit" onClick={() => void runTraceSearch()} disabled={searchLoading}>
          {searchLoading ? 'Searching...' : 'Search'}
        </button>
      </div>
      <div className="search-controls">
        <label>
          Query
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                void runTraceSearch()
              }
            }}
            id="search-input"
            placeholder="Belgrade, missing token, critic turn..."
          />
        </label>
        <label>
          Event type
          <select value={searchEventType} onChange={(event) => setSearchEventType(event.target.value as '' | import('../types').EventType)}>
            {SEARCHABLE_EVENT_TYPES.map((option: { value: '' | import('../types').EventType; label: string }) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mode-switches search-scope-switches">
        {(['current', 'all'] as SearchScope[]).map((scope) => (
          <button key={scope} type="button" className={searchScope === scope ? 'active' : ''} onClick={() => setSearchScope(scope)}>
            {scope === 'current' ? 'Current session' : 'All sessions'}
          </button>
        ))}
      </div>
      {searchError ? <p className="search-status error">{searchError}</p> : null}
      {!searchError && searchResponse ? (
        <p className="search-status">
          {searchResponse.total} result{searchResponse.total === 1 ? '' : 's'} for "{searchResponse.query}"
        </p>
      ) : null}
      <div className="search-results">
        {searchResponse?.results.length ? (
          searchResponse.results.map((result) => {
            const resultSession = searchSessionLookup.get(result.session_id)
            return (
              <button key={result.id} type="button" className="search-result" onClick={() => jumpToSearchResult(result)}>
                <div className="search-result-topline">
                  <span className={`event-chip ${result.event_type}`}>{result.event_type.replaceAll('_', ' ')}</span>
                  <span>{new Date(result.timestamp).toLocaleTimeString()}</span>
                </div>
                <strong>{formatEventHeadline(result)}</strong>
                <p>{resultSession?.agent_name ?? result.session_id}</p>
              </button>
            )
          })
        ) : (
          <div className="search-empty">
            {searchResponse ? (
              <div className="empty-state">
                <div className="empty-state-icon">🔭</div>
                <h3>No results found</h3>
                <p>Try adjusting your search terms or filters</p>
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state-icon">🔍</div>
                <h3>Search your traces</h3>
                <p>Find events by name, payload content, or metadata</p>
                <div className="search-suggestions">
                  <small>Try:</small>
                  <div className="suggestion-chips">
                    <span>error messages</span>
                    <span>function names</span>
                    <span>agent IDs</span>
                    <span>tool calls</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
