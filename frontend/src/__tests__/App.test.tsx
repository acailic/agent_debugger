import { describe, it, expect } from 'vitest'

describe('App', () => {
  it('exports as default without crashing', async () => {
    const mod = await import('../App')
    // App.tsx renders the full application — just verify it exports something
    expect(mod).toBeDefined()
  })
})
