// Invoice list query (GET /customers/:id/invoices).
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../../lib/api-client'
import type { Invoice } from '../../../types/api'

export const invoicesQueryKey = (customerId: string) => ['customers', customerId, 'invoices'] as const

/** Fetches a customer's invoices. */
export async function getInvoices(customerId: string): Promise<Invoice[]> {
  const { data } = await apiClient.get<Invoice[]>(`/customers/${encodeURIComponent(customerId)}/invoices`)
  return data
}

/** Query hook for a customer's invoice list. */
export function useInvoices(customerId: string) {
  return useQuery({
    queryKey: invoicesQueryKey(customerId),
    queryFn: () => getInvoices(customerId),
  })
}
