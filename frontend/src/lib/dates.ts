// Date formatting for API timestamps. `*_local` values are the customer's wall-clock time and are
// rendered as-is; absolute timestamps (created_at, issued_at) are rendered in the browser's timezone.
const dateFormat = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
const shortDateFormat = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' })
const dateTimeFormat = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

const LOCAL_DATE = /^(\d{4})-(\d{2})-(\d{2})/

// Local ISO strings carry the customer's wall-clock date; parse the date part
// directly so the browser timezone cannot shift it to another day.
function localDateOf(isoLocal: string): Date | null {
  const match = LOCAL_DATE.exec(isoLocal)
  if (!match) return null
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
}

/** Customer-local ISO datetime → "1 Oct 2026". */
export function formatLocalDate(isoLocal: string): string {
  const date = localDateOf(isoLocal)
  return date ? dateFormat.format(date) : isoLocal
}

/** Customer-local ISO datetime → "1 Oct" (chart axis). */
export function formatShortLocalDate(isoLocal: string): string {
  const date = localDateOf(isoLocal)
  return date ? shortDateFormat.format(date) : isoLocal
}

/**
 * Billing period as "1 Oct 2026 → 31 Oct 2026".
 * end_local is the exclusive boundary (next cycle's midnight); the last included day is shown instead.
 */
export function formatPeriod(startLocal: string, endLocal: string): string {
  const end = localDateOf(endLocal)
  const lastDay = end ? dateFormat.format(new Date(end.getFullYear(), end.getMonth(), end.getDate() - 1)) : endLocal
  return `${formatLocalDate(startLocal)} → ${lastDay}`
}

/** Absolute ISO timestamp → local date and time; '—' when missing. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : dateTimeFormat.format(date)
}
