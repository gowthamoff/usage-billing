// Invoice lines carry no unit field, so unit labels for known meters live here.
const METER_UNITS: Record<string, string> = {
  api_calls: 'call',
  storage_gb: 'GB',
}

/** Unit label for a meter id, 'unit' when unknown. */
export function unitForMeter(meter: string): string {
  return METER_UNITS[meter] ?? 'unit'
}

/**
 * Pluralises a unit label for a quantity.
 * All-caps units (GB) are symbols and never take an 's'.
 */
export function pluralUnit(unit: string, quantity: number): string {
  if (quantity === 1 || unit === unit.toUpperCase()) return unit
  return `${unit}s`
}
