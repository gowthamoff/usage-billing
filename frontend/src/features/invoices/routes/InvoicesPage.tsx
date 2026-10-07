// /customers/:id/invoices — the customer's invoice list.
import { Button, Card } from 'antd'
import { Link } from 'react-router-dom'
import { useInvoices } from '../api/get-invoices'
import { InvoiceTable } from '../components/InvoiceTable'
import { LoadingState } from '../../../components/states/LoadingState'
import { ErrorState } from '../../../components/states/ErrorState'
import { EmptyState } from '../../../components/states/EmptyState'
import { useRequiredParam } from '../../../lib/router'
import { errorMessage } from '../../../lib/api-client'

export function InvoicesPage() {
  const customerId = useRequiredParam('id')
  const invoices = useInvoices(customerId)

  if (invoices.isPending) return <LoadingState title="Invoices" rows={5} />
  if (invoices.isError) {
    return (
      <ErrorState
        title="Could not load invoices"
        message={errorMessage(invoices.error)}
        onRetry={() => void invoices.refetch()}
        retrying={invoices.isFetching}
      />
    )
  }
  if (invoices.data.length === 0) {
    return (
      <EmptyState
        title="Invoices"
        description="No invoices yet for this customer. Close a cycle from the Usage page to issue the first one."
      >
        <Link to={`/customers/${customerId}/usage`}>
          <Button type="primary">Go to usage</Button>
        </Link>
      </EmptyState>
    )
  }

  return (
    <Card title="Invoices">
      <InvoiceTable customerId={customerId} invoices={invoices.data} />
    </Card>
  )
}
