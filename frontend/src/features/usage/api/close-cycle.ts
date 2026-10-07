// Close-cycle mutation (POST /customers/:id/cycles/close), which issues the period's invoice.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../../lib/api-client'
import type { CloseCycleRequest, Invoice } from '../../../types/api'

export interface CloseCycleResult {
  invoice: Invoice
  created: boolean
}

/**
 * Closes the customer's cycle and returns the invoice.
 * The endpoint is idempotent: 201 means newly issued, 200 means the cycle was already closed (`created` = false).
 */
export async function closeCycle(customerId: string, body: CloseCycleRequest): Promise<CloseCycleResult> {
  const response = await apiClient.post<Invoice>(`/customers/${encodeURIComponent(customerId)}/cycles/close`, body)
  return { invoice: response.data, created: response.status === 201 }
}

/**
 * Mutation hook for closing a cycle.
 * Invalidates everything under the customer so usage, notifications and invoices refetch together.
 */
export function useCloseCycle(customerId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CloseCycleRequest) => closeCycle(customerId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['customers', customerId] }),
  })
}
