// Customer list query (GET /customers).
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../../lib/api-client'
import type { Customer } from '../../../types/api'

export const customersQueryKey = ['customers'] as const

/** Fetches all customers. */
export async function getCustomers(): Promise<Customer[]> {
  const { data } = await apiClient.get<Customer[]>('/customers')
  return data
}

/**
 * Query hook for the customer list.
 * Shared by the header picker, root redirect and usage page; a 60 s staleTime keeps them from refetching on every mount.
 */
export function useCustomers() {
  return useQuery({
    queryKey: customersQueryKey,
    queryFn: getCustomers,
    staleTime: 60_000,
  })
}
