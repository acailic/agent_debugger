import { afterEach, describe, expect, it, vi } from 'vitest'
import { compareScenarios, createBranch, getReplayEvents, setBreakpoint, stepExecution } from '../api/client'

afterEach(() => vi.unstubAllGlobals())

describe('API URLs with query parameters', () => {
  it.each([
    {
      call: () => getReplayEvents('session-a', 'event one', 'branch-a', false),
      path: '/api/sessions/session-a/reasoning/replay',
      query: 'from_event_id=event+one&branch_id=branch-a&include_branch_edits=false',
      method: 'GET',
    },
    {
      call: () => compareScenarios('session-a', ['branch one', 'branch-two']),
      path: '/api/sessions/session-a/reasoning/scenarios/compare',
      query: 'branch_ids=branch+one&branch_ids=branch-two',
      method: 'GET',
    },
    {
      call: () => setBreakpoint('session-a', 'confidence_threshold', 0.5, 'pause here'),
      path: '/api/sessions/session-a/breakpoints',
      query: 'breakpoint_type=confidence_threshold&condition_value=0.5&description=pause+here',
      method: 'POST',
    },
    {
      call: () => stepExecution('session-a', 'run_to', 'event one'),
      path: '/api/sessions/session-a/step',
      query: 'action=run_to&target_event_id=event+one',
      method: 'POST',
    },
    {
      call: () => createBranch('session-a', 'new branch', 'event one', 'try again'),
      path: '/api/sessions/session-a/branch',
      query: 'name=new+branch&parent_event_id=event+one&description=try+again',
      method: 'POST',
    },
  ])('resolves $path against the page origin and reaches fetch', async ({ call, path, query, method }) => {
    const payload = { result: 'ok' }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)))
    vi.stubGlobal('fetch', fetchMock)

    expect(await call()).toEqual(payload)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      `${window.location.origin}${path}?${query}`,
      method === 'GET' ? {} : { method },
    )
  })
})
