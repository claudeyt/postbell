import { apiFetch } from './client'
import type { AnalyticsSummaryResponse } from '../types'

export async function getAnalyticsSummary(
  channelIds?: number[],
): Promise<AnalyticsSummaryResponse> {
  const qs =
    channelIds && channelIds.length
      ? `?channel_ids=${channelIds.join(',')}`
      : ''
  return apiFetch<AnalyticsSummaryResponse>(`/analytics/summary${qs}`)
}
