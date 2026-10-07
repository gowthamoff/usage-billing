// Current-period usage query (GET /customers/:id/usage).
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../../lib/api-client'
import { USAGE_POLL_INTERVAL_MS } from '../../../config'
import type { UsageResponse } from '../../../types/api'

export const usageQueryKey = (customerId: string) => ['customers', customerId, 'usage'] as const

/** Fetches current-period usage for every meter on the customer's plan. */
export async function getUsage(customerId: string): Promise<UsageResponse> {
  const { data } = await apiClient.get<UsageResponse>(`/customers/${encodeURIComponent(customerId)}/usage`)
  return data
}

/**
 * Query hook for current usage.
 * Polls every 10 s so the cards and threshold tags update after an ingest without a reload.
 */
export function useUsage(customerId: string) {
  return useQuery({
    queryKey: usageQueryKey(customerId),
    queryFn: () => getUsage(customerId),
    refetchInterval: USAGE_POLL_INTERVAL_MS,
  })
}
