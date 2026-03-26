import { useCallback, useRef, useState } from 'react'
import { searchSessions } from '../api/client'
import type { SearchResult } from '../types'

interface SearchBarProps {
  onSelectSession: (sessionId: string) => void
}

export default function SearchBar({ onSelectSession }: SearchBarProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const doSearch = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([])
      return
    }
    setIsSearching(true)
    try {
      const resp = await searchSessions({ q, limit: 10 })
      setResults(resp.results)
    } catch {
      setResults([])
    } finally {
      setIsSearching(false)
    }
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => doSearch(value), 300)
  }

  const handleSelect = (sessionId: string) => {
    setResults([])
    setQuery('')
    onSelectSession(sessionId)
  }

  const formatPercent = (n: number) => `${Math.round(n * 100)}%`

  return (
    <div className="search-bar">
      <input
        type="text"
        className="search-input"
        placeholder="Search past failures..."
        value={query}
        onChange={handleChange}
      />
      {isSearching && <span className="search-loading">Searching...</span>}
      {results.length > 0 && (
        <div className="search-results">
          {results.map(r => (
            <button
              key={r.session_id}
              className="search-result-item"
              onClick={() => handleSelect(r.session_id)}
            >
              <div className="search-result-header">
                <span className="search-result-agent">{r.agent_name}</span>
                <span className="search-result-similarity">{formatPercent(r.similarity)} match</span>
              </div>
              <div className="search-result-meta">
                <span className={`search-result-status status-${r.status}`}>{r.status}</span>
                <span>{r.errors} errors</span>
                <span>${r.total_cost_usd.toFixed(4)}</span>
                <span>{new Date(r.started_at).toLocaleDateString()}</span>
              </div>
              {r.fix_note && (
                <div className="search-result-fix">Fix: {r.fix_note}</div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
