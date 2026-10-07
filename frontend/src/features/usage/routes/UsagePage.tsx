// /customers/:id/usage — period summary, per-meter cards, daily chart and threshold notifications.
import { useEffect } from 'react'
import { Card, Descriptions, Empty, Skeleton, Space, Typography } from 'antd'
import { SyncOutlined } from '@ant-design/icons'
import { useCustomers } from '../../customers/api/get-customers'
import { useUsage } from '../api/get-usage'
import { useNotifications } from '../api/get-notifications'
import { UsageCards } from '../components/UsageCards'
import { UsageChart } from '../components/UsageChart'
import { NotificationsTable } from '../components/NotificationsTable'
import { CloseCycleButton } from '../components/CloseCycleButton'
import { LoadingState } from '../../../components/states/LoadingState'
import { ErrorState } from '../../../components/states/ErrorState'
import { EmptyState } from '../../../components/states/EmptyState'
import { useUiStore } from '../../../stores/ui-store'
import { useRequiredParam } from '../../../lib/router'
import { errorMessage } from '../../../lib/api-client'
import { formatPeriod } from '../../../lib/dates'
import { formatInr } from '../../../lib/money'

export function UsagePage() {
  const customerId = useRequiredParam('id')
  const customers = useCustomers()
  const usage = useUsage(customerId)
  const notifications = useNotifications(customerId)
  const selectedMeter = useUiStore((state) => state.selectedMeter)
  const setSelectedMeter = useUiStore((state) => state.setSelectedMeter)

  const customer = customers.data?.find((candidate) => candidate.id === customerId)
  const meters = usage.data?.meters ?? []
  const activeMeter = meters.some((meter) => meter.meter === selectedMeter)
    ? selectedMeter
    : meters.length > 0
      ? meters[0].meter
      : null

  // Persist the fallback so the shown meter survives navigating to Invoices and back.
  useEffect(() => {
    if (activeMeter !== selectedMeter) setSelectedMeter(activeMeter)
  }, [activeMeter, selectedMeter, setSelectedMeter])

  const renderSummary = () => {
    if (usage.isPending) return <Skeleton active paragraph={{ rows: 1 }} />
    if (usage.isError) return <Typography.Text type="secondary">Billing period unavailable.</Typography.Text>
    const { period, total_cost_minor } = usage.data
    return (
      <Descriptions
        size="small"
        column={{ xs: 1, md: 2 }}
        items={[
          { key: 'period', label: 'Current billing period', children: formatPeriod(period.start_local, period.end_local) },
          { key: 'timezone', label: 'Timezone', children: customer?.timezone ?? '—' },
          { key: 'plan', label: 'Plan', children: customer?.plan.name ?? '—' },
          {
            key: 'total',
            label: 'Overage cost so far',
            children: <Typography.Text strong>{formatInr(total_cost_minor)}</Typography.Text>,
          },
        ]}
      />
    )
  }

  const renderUsage = () => {
    if (usage.isPending) return <LoadingState title="Usage" rows={6} />
    if (usage.isError) {
      return (
        <ErrorState
          title="Could not load usage"
          message={errorMessage(usage.error)}
          onRetry={() => void usage.refetch()}
          retrying={usage.isFetching}
        />
      )
    }
    if (meters.length === 0 || activeMeter === null) {
      return (
        <EmptyState
          title="Usage"
          description="No meters are priced for this customer's plan, so there is nothing to meter yet."
        />
      )
    }
    return (
      <Space direction="vertical" size="large" style={{ display: 'flex' }}>
        <UsageCards meters={meters} selectedMeter={activeMeter} onSelectMeter={setSelectedMeter} />
        <UsageChart customerId={customerId} meters={meters} selectedMeter={activeMeter} onSelectMeter={setSelectedMeter} />
      </Space>
    )
  }

  const renderNotifications = () => {
    if (notifications.isPending) return <Skeleton active paragraph={{ rows: 3 }} />
    if (notifications.isError) {
      return (
        <ErrorState
          title="Could not load notifications"
          message={errorMessage(notifications.error)}
          onRetry={() => void notifications.refetch()}
          retrying={notifications.isFetching}
        />
      )
    }
    if (notifications.data.length === 0) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="No thresholds crossed yet this period. Notifications appear here at 50%, 80% and 100% of a meter's allowance."
        />
      )
    }
    const meterNames = Object.fromEntries(meters.map((meter) => [meter.meter, meter.display_name] as const))
    return <NotificationsTable notifications={notifications.data} meterNames={meterNames} />
  }

  return (
    <Space direction="vertical" size="large" style={{ display: 'flex' }}>
      <Card
        title={
          <Space>
            <span>{customer?.name ?? customerId}</span>
            <Typography.Text type="secondary">{customerId}</Typography.Text>
          </Space>
        }
        extra={
          <Space size="middle">
            <Typography.Text type="secondary">
              <SyncOutlined spin={usage.isFetching} /> Auto-refreshes every 10 s
            </Typography.Text>
            <CloseCycleButton customerId={customerId} />
          </Space>
        }
      >
        {renderSummary()}
      </Card>
      {renderUsage()}
      <Card title="Threshold notifications" extra={<Typography.Text type="secondary">Current period</Typography.Text>}>
        {renderNotifications()}
      </Card>
    </Space>
  )
}
