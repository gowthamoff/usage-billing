// Response shapes of the billing API (/api/v1). Money: `*_minor` fields are integer paise, `rate_minor` is a
// decimal string of paise per unit. Times: plain fields are UTC ISO, `*_local` carry the customer's offset.

export type UsageState = 'within_allowance' | 'approaching_limit' | 'in_overage'

// Plan summary embedded in a customer.
export interface PlanRef {
  id: string
  name: string
}

// Customer list row.
export interface Customer {
  id: string
  name: string
  timezone: string
  // YYYY-MM-DD; billing cycles anchor on this day of the month.
  signup_date: string
  plan: PlanRef
}

// Billing period bounds. `end` is exclusive (the next cycle's midnight).
export interface Period {
  start: string
  end: string
  // ISO datetime with the customer's UTC offset, e.g. 2026-10-01T00:00:00+05:30.
  start_local: string
  end_local: string
}

// Customer with its current billing period.
export interface CustomerDetail extends Customer {
  current_period: Period
}

// Current-period usage of one meter against the plan allowance.
export interface MeterUsage {
  meter: string
  display_name: string
  unit: string
  used: number
  allowance: number
  remaining: number
  overage_units: number
  // used / allowance * 100; exceeds 100 when in overage.
  percent: number
  state: UsageState
  // Overage rate as a decimal string of paise per unit, e.g. "50.000000" = ₹0.50.
  rate_minor: string
  // Overage cost so far, in paise.
  cost_minor: number
}

// GET /customers/:id/usage.
export interface UsageResponse {
  period: Period
  currency: string
  meters: MeterUsage[]
  // Sum of meter overage costs, in paise.
  total_cost_minor: number
}

// One bucket of the daily chart.
export interface TimeseriesPoint {
  // YYYY-MM-DD in the customer's timezone.
  date: string
  quantity: number
}

// GET /customers/:id/usage/timeseries for one meter.
export interface TimeseriesResponse {
  meter: string
  bucket: string
  points: TimeseriesPoint[]
}

// A 50/80/100% allowance threshold crossing and its delivery state.
export interface ThresholdNotification {
  id: number
  meter: string
  // Percent of allowance that was crossed.
  threshold: number
  period_start: string
  usage_at_fire: number
  allowance: number
  created_at: string
  // null until the worker delivers it.
  sent_at: string | null
  attempts: number
  last_error: string | null
}

// Invoice list row.
export interface Invoice {
  id: string
  period_start: string
  period_end: string
  period_start_local: string
  period_end_local: string
  currency: string
  // Paise; may be negative when adjustments credit the customer.
  total_minor: number
  status: string
  issued_at: string
}

export type InvoiceLineType = 'usage' | 'adjustment'

// One invoice line: a meter's usage for the period, or an adjustment for late events against an earlier invoice.
export interface InvoiceLine {
  id: number
  line_type: InvoiceLineType
  meter: string
  display_name: string
  period_start: string
  period_end: string
  quantity: number
  allowance: number
  // Negative on an adjustment that reduces what was billed.
  overage_units: number
  // Decimal string of paise per unit.
  rate_minor: string
  // Paise.
  amount_minor: number
  description: string
  // Set on adjustment lines: the invoice being corrected.
  adjusts_invoice_id: string | null
}

// GET /invoices/:id.
export interface InvoiceDetail extends Invoice {
  lines: InvoiceLine[]
}

// POST /customers/:id/cycles/close body.
export interface CloseCycleRequest {
  period_start?: string
  // Close the period before it has ended (demo use).
  force?: boolean
}

// Error envelope returned by the API on 4xx/5xx.
export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details?: unknown[]
  }
}
