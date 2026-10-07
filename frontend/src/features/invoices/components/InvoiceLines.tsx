import type { ReactNode } from 'react'
import { Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { Link } from 'react-router-dom'
import { formatCount, formatInr, formatRate, formatRateAmount } from '../../../lib/money'
import { pluralUnit, unitForMeter } from '../../../lib/units'
import type { InvoiceLine } from '../../../types/api'

interface InvoiceLinesProps {
  customerId: string
  lines: InvoiceLine[]
  totalMinor: number
}

function explain(line: InvoiceLine, customerId: string): ReactNode {
  const unit = unitForMeter(line.meter)
  const rate = formatRateAmount(line.rate_minor)
  const extra =
    line.overage_units > 0
      ? `${formatCount(line.overage_units)} extra × ${rate} = ${formatInr(line.amount_minor)}`
      : line.overage_units < 0
        ? `${formatCount(-line.overage_units)} fewer billable × ${rate} = ${formatInr(line.amount_minor)} credit`
        : 'nothing extra to pay'

  if (line.line_type === 'adjustment') {
    return (
      <>
        Adjustment for invoice{' '}
        {line.adjusts_invoice_id ? (
          <Link to={`/customers/${customerId}/invoices/${line.adjusts_invoice_id}`}>{line.adjusts_invoice_id}</Link>
        ) : (
          'an earlier period'
        )}
        : {formatCount(line.quantity)} {pluralUnit(unit, line.quantity)} received late · {extra}
      </>
    )
  }

  return `${formatCount(line.quantity)} ${pluralUnit(unit, line.quantity)} used · ${formatCount(line.allowance)} included · ${extra}`
}

export function InvoiceLines({ customerId, lines, totalMinor }: InvoiceLinesProps) {
  const columns: TableProps<InvoiceLine>['columns'] = [
    {
      title: 'Line',
      key: 'line',
      render: (_, line) => (
        <Space>
          <span>{line.display_name}</span>
          {line.line_type === 'adjustment' && <Tag color="purple">Adjustment</Tag>}
        </Space>
      ),
    },
    {
      title: 'Quantity',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (quantity: number) => formatCount(quantity),
    },
    {
      title: 'Included',
      dataIndex: 'allowance',
      key: 'allowance',
      align: 'right',
      render: (allowance: number) => formatCount(allowance),
    },
    {
      title: 'Extra',
      dataIndex: 'overage_units',
      key: 'overage_units',
      align: 'right',
      render: (overage: number) => formatCount(overage),
    },
    {
      title: 'Rate',
      key: 'rate',
      render: (_, line) => formatRate(line.rate_minor, unitForMeter(line.meter)),
    },
    {
      title: 'Amount',
      dataIndex: 'amount_minor',
      key: 'amount_minor',
      align: 'right',
      render: (amount: number) => <Typography.Text strong>{formatInr(amount)}</Typography.Text>,
    },
  ]

  return (
    <Table
      rowKey="id"
      size="middle"
      pagination={false}
      dataSource={lines}
      columns={columns}
      expandable={{
        expandedRowKeys: lines.map((line) => line.id),
        showExpandColumn: false,
        expandedRowRender: (line) => (
          <Space direction="vertical" size={0}>
            <Typography.Text>{explain(line, customerId)}</Typography.Text>
            {line.description && <Typography.Text type="secondary">{line.description}</Typography.Text>}
          </Space>
        ),
      }}
      summary={() => (
        <Table.Summary.Row>
          <Table.Summary.Cell index={0} colSpan={5}>
            <Typography.Text strong>Total</Typography.Text>
          </Table.Summary.Cell>
          <Table.Summary.Cell index={1} align="right">
            <Typography.Text strong>{formatInr(totalMinor)}</Typography.Text>
          </Table.Summary.Cell>
        </Table.Summary.Row>
      )}
    />
  )
}
