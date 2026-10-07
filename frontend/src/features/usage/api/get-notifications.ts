// Threshold notification query (GET /customers/:id/notifications).
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../../lib/api-client'
import { USAGE_POLL_INTERVAL_MS } from '../../../config'
import type { ThresholdNotification } from '../../../types/api'

export const notificationsQueryKey = (customerId: string, all: boolean) =>
  ['customers', customerId, 'notifications', { all }] as const

/** Fetches the current period's threshold notifications, or every period's when `all` is true. */
export async function getNotifications(customerId: string, all = false): Promise<ThresholdNotification[]> {
  const { data } = await apiClient.get<ThresholdNotification[]>(
    `/customers/${encodeURIComponent(customerId)}/notifications`,
    { params: all ? { all: 'true' } : undefined },
  )
  return data
}

/**
 * Query hook for threshold notifications.
 * Polls so delivery moves from Pending to Sent as the worker runs.
 */
export function useNotifications(customerId: string, all = false) {
  return useQuery({
    queryKey: notificationsQueryKey(customerId, all),
    queryFn: () => getNotifications(customerId, all),
    refetchInterval: USAGE_POLL_INTERVAL_MS,
  })
}
