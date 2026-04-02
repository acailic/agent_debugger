import { useState, useEffect } from 'react'

/**
 * Custom hook for responsive breakpoint checking
 * Returns current breakpoint category based on window width
 */
export type Breakpoint = 'mobile' | 'tablet' | 'desktop'

export function useBreakpoint(): Breakpoint {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(() => {
    if (typeof window === 'undefined') return 'desktop'
    return getBreakpointFromWidth(window.innerWidth)
  })

  useEffect(() => {
    const handleResize = (): void => {
      setBreakpoint(getBreakpointFromWidth(window.innerWidth))
    }

    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  return breakpoint
}

function getBreakpointFromWidth(width: number): Breakpoint {
  if (width < 768) return 'mobile'
  if (width < 1024) return 'tablet'
  return 'desktop'
}
