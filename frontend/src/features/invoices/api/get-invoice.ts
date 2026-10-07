// Single invoice query with lines (GET /invoices/:id).
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../../lib/api-client'
import type { InvoiceDetail } from '../../../types/api'

export const invoiceQueryKey = (invoiceId: string) => ['invoices', invoiceId] as const

/** Fetches one invoice with its lines. */
export async function getInvoice(invoiceId: string): Promise<InvoiceDetail> {
  const { data } = await apiClient.get<InvoiceDetail>(`/invoices/${encodeURIComponent(invoiceId)}`)
  return data
}

/** Query hook for one invoice. */
export function useInvoice(invoiceId: string) {
  return useQuery({
    queryKey: invoiceQueryKey(invoiceId),
    queryFn: () => getInvoice(invoiceId),
  })
}
