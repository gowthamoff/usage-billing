import { Table, Tag } from 'antd'
import type { TableProps } from 'antd'
import { Link } from 'react-router-dom'
import { formatDateTime, formatPeriod } from '../../../lib/dates'
import { formatInr } from '../../../lib/money'
import type { Invoice } from '../../../types/api'

const STATUS_COLORS: Record<string, string> = {
  issued: 'blue',
  paid: 'green',
  void: 'default',
}

export function InvoiceStatusTag({ status }: { status: string }) {
  return <Tag color={STATUS_COLORS[status] ?? 'default'}>{status}</Tag>
}

interface InvoiceTableProps {
  customerId: string
  invoices: Invoice[]
}

export function InvoiceTable({ customerId, invoices }: InvoiceTableProps) {
  const detailPath = (invoiceId: string) => `/customers/${customerId}/invoices/${invoiceId}`

  const columns: TableProps<Invoice>['columns'] = [
    {
      title: 'Invoice',
      dataIndex: 'id',
      key: 'id',
      render: (id: string) => <Link to={detailPath(id)}>{id}</Link>,
    },
    {
      title: 'Period',
      key: 'period',
      render: (_, invoice) => formatPeriod(invoice.period_start_local, invoice.period_end_local),
    },
    {
      title: 'Issued',
      dataIndex: 'issued_at',
      key: 'issued_at',
      render: (issuedAt: string) => formatDateTime(issuedAt),
    },
    {
      title: 'Total',
      dataIndex: 'total_minor',
      key: 'total_minor',
      align: 'right',
      render: (totalMinor: number) => formatInr(totalMinor),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <InvoiceStatusTag status={status} />,
    },
    {
      key: 'actions',
      render: (_, invoice) => <Link to={detailPath(invoice.id)}>View</Link>,
    },
  ]

  return <Table rowKey="id" dataSource={invoices} columns={columns} pagination={{ hideOnSinglePage: true }} />
}
