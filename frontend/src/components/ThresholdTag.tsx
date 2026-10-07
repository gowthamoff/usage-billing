import { Tag } from 'antd'
import type { UsageState } from '../types/api'

const STATE_META: Record<UsageState, { color: string; label: string }> = {
  within_allowance: { color: 'green', label: 'Within allowance' },
  approaching_limit: { color: 'orange', label: 'Approaching limit' },
  in_overage: { color: 'red', label: 'In overage' },
}

/** Colour-coded tag for a meter's usage state (within allowance / approaching limit / in overage). */
export function ThresholdTag({ state }: { state: UsageState }) {
  const meta = STATE_META[state] ?? { color: 'default', label: state }
  return <Tag color={meta.color}>{meta.label}</Tag>
}
