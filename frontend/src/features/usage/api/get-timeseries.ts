// Daily usage series query for one meter (GET /customers/:id/usage/timeseries).
import { skipToken, useQuery } from '@tanstack/react-query'
import { apiClient } from '../../../lib/api-client'
import { USAGE_POLL_INTERVAL_MS } from '../../../config'
import type { TimeseriesResponse } from '../../../types/api'

export const timeseriesQueryKey = (customerId: string, meter: string | null) =>
  ['customers', customerId, 'usage', 'timeseries', meter] as const

/** Fetches the current period's daily usage points for one meter. */
export async function getTimeseries(customerId: string, meter: string): Promise<TimeseriesResponse> {
  const { data } = await apiClient.get<TimeseriesResponse>(
    `/customers/${encodeURIComponent(customerId)}/usage/timeseries`,
    { params: { meter } },
  )
  return data
}

/**
 * Query hook for the daily chart; idle (skipToken) until a meter is selected.
 * Polls on the usage interval so the chart stays in step with the cards.
 */
export function useTimeseries(customerId: string, meter: string | null) {
  return useQuery({
    queryKey: timeseriesQueryKey(customerId, meter),
    queryFn: meter ? () => getTimeseries(customerId, meter) : skipToken,
    refetchInterval: USAGE_POLL_INTERVAL_MS,
  })
}
