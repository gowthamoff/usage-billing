import { Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { NOTIFICATION_MAX_ATTEMPTS } from '../../../config'
import { formatDateTime } from '../../../lib/dates'
import { formatCount } from '../../../lib/money'
import type { ThresholdNotification } from '../../../types/api'

type Delivery = 'sent' | 'pending' | 'failed'

function deliveryOf(notification: ThresholdNotification): Delivery {
  if (notification.sent_at) return 'sent'
  if (notification.attempts >= NOTIFICATION_MAX_ATTEMPTS) return 'failed'
  return 'pending'
}

const DELIVERY_META: Record<Delivery, { color: string; label: string }> = {
  sent: { color: 'green', label: 'Sent' },
  pending: { color: 'blue', label: 'Pending' },
  failed: { color: 'red', label: 'Failed' },
}

function thresholdColor(threshold: number): string {
  if (threshold >= 100) return 'red'
  if (threshold >= 80) return 'orange'
  return 'blue'
}

interface NotificationsTableProps {
  notifications: ThresholdNotification[]
  meterNames: Record<string, string>
}

export function NotificationsTable({ notifications, meterNames }: NotificationsTableProps) {
  const columns: TableProps<ThresholdNotification>['columns'] = [
    {
      title: 'Threshold',
      dataIndex: 'threshold',
      key: 'threshold',
      render: (threshold: number) => <Tag color={thresholdColor(threshold)}>{threshold}%</Tag>,
    },
    {
      title: 'Meter',
      dataIndex: 'meter',
      key: 'meter',
      render: (meter: string) => meterNames[meter] ?? meter,
    },
    {
      title: 'Usage when fired',
      key: 'usage',
      render: (_, notification) => `${formatCount(notification.usage_at_fire)} / ${formatCount(notification.allowance)}`,
    },
    {
      title: 'Fired at',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (createdAt: string) => formatDateTime(createdAt),
    },
    {
      title: 'Delivery',
      key: 'delivery',
      render: (_, notification) => {
        const delivery = deliveryOf(notification)
        const meta = DELIVERY_META[delivery]
        const detail =
          delivery === 'sent'
            ? formatDateTime(notification.sent_at)
            : notification.attempts > 0
              ? `${notification.attempts} attempt${notification.attempts === 1 ? '' : 's'}`
              : 'awaiting worker'
        return (
          <Space>
            <Tag color={meta.color}>{meta.label}</Tag>
            <Typography.Text type="secondary">{detail}</Typography.Text>
            {notification.last_error && (
              <Tooltip title={notification.last_error}>
                <Typography.Text type="danger">last error</Typography.Text>
              </Tooltip>
            )}
          </Space>
        )
      },
    },
  ]

  return <Table rowKey="id" size="small" pagination={false} dataSource={notifications} columns={columns} />
}
