// INR and number formatting. Amounts arrive as integer paise (`*_minor`); rates as a decimal string of paise per unit.
const inrFormat = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const rateFormat = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

const countFormat = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

/** Formats paise as rupees, e.g. 123456 → ₹1,234.56. */
export function formatInr(minor: number): string {
  const sign = minor < 0 ? '-' : ''
  return `${sign}₹${inrFormat.format(Math.abs(minor) / 100)}`
}

/**
 * Formats a per-unit rate as rupees with up to 4 decimals.
 * rate_minor is paise per unit as a decimal string (e.g. "50.000000" = ₹0.50).
 */
export function formatRateAmount(rateMinor: string | number): string {
  const rupeesPerUnit = Number(rateMinor) / 100
  return Number.isFinite(rupeesPerUnit) ? `₹${rateFormat.format(rupeesPerUnit)}` : String(rateMinor)
}

/** Rate with its unit, e.g. ₹0.50 / call. */
export function formatRate(rateMinor: string | number, unit: string): string {
  return `${formatRateAmount(rateMinor)} / ${unit}`
}

/** Whole-number quantity with en-IN grouping. */
export function formatCount(value: number): string {
  return countFormat.format(value)
}

/**
 * Clamps to 0–100 for progress bars.
 * API percent exceeds 100 in overage; pair with formatPercent so the real value is still shown.
 */
export function clampPercent(percent: number): number {
  if (!Number.isFinite(percent)) return 0
  return Math.min(100, Math.max(0, percent))
}

/** Percent to one decimal, unclamped. */
export function formatPercent(percent: number): string {
  if (!Number.isFinite(percent)) return '0%'
  return `${Math.round(percent * 10) / 10}%`
}
