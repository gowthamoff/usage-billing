// App-wide constants: API location/key and the polling and retry tunables the UI reads.
export const API_BASE_URL = '/api/v1'
export const API_KEY: string = import.meta.env.VITE_API_KEY ?? 'dev-key'
// Usage, timeseries and notification queries refetch on this interval.
export const USAGE_POLL_INTERVAL_MS = 10_000
// Mirrors the backend worker's retry limit; a notification with this many attempts and no sent_at is shown as failed.
export const NOTIFICATION_MAX_ATTEMPTS = 8
