/**
 * Centralized logging utility for the frontend.
 *
 * All console output goes through here so we can:
 * - Control verbosity in production builds
 * - Add structured metadata (component, severity)
 * - Swap to a remote logger without touching components
 */

interface LogOptions {
  component?: string
  silent?: boolean
}

function formatMessage(message: string, options: LogOptions): string {
  const prefix = options.component ? `[${options.component}] ` : ""
  return `${prefix}${message}`
}

export const logger = {
  debug(message: string, ...data: unknown[]): void {
    if (import.meta.env.PROD) return
    console.debug(message, ...data)
  },

  info(message: string, ...data: unknown[]): void {
    console.log(message, ...data)
  },

  warn(message: string, options?: LogOptions, ...data: unknown[]): void {
    console.warn(formatMessage(message, options ?? {}), ...data)
  },

  error(message: string, options?: LogOptions, ...data: unknown[]): void {
    console.error(formatMessage(message, options ?? {}), ...data)
  },
}
