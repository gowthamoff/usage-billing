// /customers/:id/invoices/:invoiceId — invoice header and its lines.
import { Button, Card, Descriptions, Empty, Space, Typography } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'
import { useInvoice } from '../api/get-invoice'
import { InvoiceLines } from '../components/InvoiceLines'
import { InvoiceStatusTag } from '../components/InvoiceTable'
import { LoadingState } from '../../../components/states/LoadingState'
import { ErrorState } from '../../../components/states/ErrorState'
import { useRequiredParam } from '../../../lib/router'
import { errorMessage } from '../../../lib/api-client'
import { formatDateTime, formatPeriod } from '../../../lib/dates'
import { formatInr } from '../../../lib/money'

export function InvoiceDetailPage() {
  const customerId = useRequiredParam('id')
  const invoiceId = useRequiredParam('invoiceId')
  const invoice = useInvoice(invoiceId)

  if (invoice.isPending) return <LoadingState title={`Invoice ${invoiceId}`} rows={6} />
  if (invoice.isError) {
    return (
      <ErrorState
        title={`Could not load invoice ${invoiceId}`}
        message={errorMessage(invoice.error)}
        onRetry={() => void invoice.refetch()}
        retrying={invoice.isFetching}
      />
    )
  }

  const { data } = invoice

  return (
    <Space direction="vertical" size="large" style={{ display: 'flex' }}>
      <Card
        title={
          <Space>
            <Link to={`/customers/${customerId}/invoices`}>
              <Button type="text" icon={<ArrowLeftOutlined />} aria-label="Back to invoices" />
            </Link>
            <span>Invoice {data.id}</span>
          </Space>
        }
        extra={<InvoiceStatusTag status={data.status} />}
      >
        <Descriptions
          size="small"
          column={{ xs: 1, md: 2 }}
          items={[
            { key: 'period', label: 'Billing period', children: formatPeriod(data.period_start_local, data.period_end_local) },
            { key: 'issued', label: 'Issued', children: formatDateTime(data.issued_at) },
            { key: 'currency', label: 'Currency', children: data.currency },
            {
              key: 'total',
              label: 'Total',
              children: <Typography.Text strong>{formatInr(data.total_minor)}</Typography.Text>,
            },
          ]}
        />
      </Card>
      <Card title="Lines">
        {data.lines.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="This invoice has no lines: nothing was used in the period."
          />
        ) : (
          <InvoiceLines customerId={customerId} lines={data.lines} totalMinor={data.total_minor} />
        )}
      </Card>
    </Space>
  )
}
