import { Card, Empty, Segmented, Skeleton } from 'antd'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useTimeseries } from '../api/get-timeseries'
import { ErrorState } from '../../../components/states/ErrorState'
import { errorMessage } from '../../../lib/api-client'
import { formatLocalDate, formatShortLocalDate } from '../../../lib/dates'
import { formatCount } from '../../../lib/money'
import { pluralUnit } from '../../../lib/units'
import type { MeterUsage } from '../../../types/api'

interface UsageChartProps {
  customerId: string
  meters: MeterUsage[]
  selectedMeter: string
  onSelectMeter: (meter: string) => void
}

export function UsageChart({ customerId, meters, selectedMeter, onSelectMeter }: UsageChartProps) {
  const timeseries = useTimeseries(customerId, selectedMeter)
  const meter = meters.find((candidate) => candidate.meter === selectedMeter)
  const unit = meter?.unit ?? 'unit'
  const title = meter ? `Daily ${meter.display_name.toLowerCase()}` : 'Daily usage'

  const renderBody = () => {
    if (timeseries.isPending) return <Skeleton active paragraph={{ rows: 6 }} />
    if (timeseries.isError) {
      return (
        <ErrorState
          title="Could not load the daily chart"
          message={errorMessage(timeseries.error)}
          onRetry={() => void timeseries.refetch()}
          retrying={timeseries.isFetching}
        />
      )
    }
    const points = timeseries.data.points
    if (points.length === 0) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="No usage recorded yet in this billing period. Send some events to see the daily breakdown."
        />
      )
    }
    return (
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
          <XAxis
            dataKey="date"
            tickFormatter={formatShortLocalDate}
            tickLine={false}
            axisLine={{ stroke: '#d9d9d9' }}
            minTickGap={24}
          />
          <YAxis tickFormatter={(value: number) => formatCount(value)} tickLine={false} axisLine={false} width={64} />
          <Tooltip
            cursor={{ fill: 'rgba(0, 0, 0, 0.04)' }}
            labelFormatter={(label) => formatLocalDate(String(label))}
            formatter={(value) => [formatCount(Number(value)), pluralUnit(unit, Number(value))]}
          />
          <Bar dataKey="quantity" fill="#1677ff" radius={[4, 4, 0, 0]} maxBarSize={32} />
        </BarChart>
      </ResponsiveContainer>
    )
  }

  return (
    <Card
      title={title}
      extra={
        <Segmented
          options={meters.map((candidate) => ({ label: candidate.display_name, value: candidate.meter }))}
          value={selectedMeter}
          onChange={(value) => onSelectMeter(String(value))}
        />
      }
    >
      {renderBody()}
    </Card>
  )
}
