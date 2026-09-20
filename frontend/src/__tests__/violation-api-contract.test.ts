import { afterEach, describe, expect, it, vi } from 'vitest'
import { clusterSessions, findSimilarSessions, searchViolations } from '../api/client'

afterEach(() => vi.unstubAllGlobals())

describe('violation API methods', () => {
  it.each([
    {
      call: () => clusterSessions({ agentName: 'agent one', sessionIds: ['a', 'b'], similarityThreshold: 0.8, minClusterSize: 2 }),
      path: '/api/violations/cluster',
      query: 'agent_name=agent+one&similarity_threshold=0.8&min_cluster_size=2&session_ids=a&session_ids=b',
    },
    {
      call: () => searchViolations({ nlQuery: 'tool failure', agentName: 'agent one', sessionIds: ['a', 'b'], maxResults: 5 }),
      path: '/api/violations/search',
      query: 'nl_query=tool+failure&agent_name=agent+one&max_results=5&session_ids=a&session_ids=b',
    },
    {
      call: () => findSimilarSessions({ sessionId: 'session-a', limit: 3 }),
      path: '/api/violations/session/session-a/similar',
      query: 'limit=3',
    },
  ])('uses POST and preserves query parameters for $path', async ({ call, path, query }) => {
    const payload = { result: 'ok' }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)))
    vi.stubGlobal('fetch', fetchMock)
    expect(await call()).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith(`${path}?${query}`, { method: 'POST' })
  })

  it('rejects unsuccessful responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 400, statusText: 'Bad Request' })))
    await expect(findSimilarSessions({ sessionId: 'session-a' })).rejects.toThrow('API error: 400 Bad Request')
  })
})
