import { Navigate } from 'react-router-dom'
import { useCustomers } from '../features/customers/api/get-customers'
import { useUiStore } from '../stores/ui-store'
import { LoadingState } from '../components/states/LoadingState'
import { ErrorState } from '../components/states/ErrorState'
import { EmptyState } from '../components/states/EmptyState'
import { errorMessage } from '../lib/api-client'

/** Sends / to the usage page of the last-selected customer, or the first customer. */
export function RootRedirect() {
  const { data, isPending, isError, error, refetch, isFetching } = useCustomers()
  const selectedCustomerId = useUiStore((state) => state.selectedCustomerId)

  if (isPending) return <LoadingState title="Loading customers" />
  if (isError) {
    return (
      <ErrorState
        title="Could not load customers"
        message={errorMessage(error)}
        onRetry={() => void refetch()}
        retrying={isFetching}
      />
    )
  }
  if (data.length === 0) {
    return (
      <EmptyState
        title="No customers"
        description="No customers exist yet. Run the backend seed command (python -m app.cli seed) and refresh."
      />
    )
  }

  const target = data.find((customer) => customer.id === selectedCustomerId) ?? data[0]
  return <Navigate to={`/customers/${target.id}/usage`} replace />
}
