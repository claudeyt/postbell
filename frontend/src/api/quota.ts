import { apiFetch } from './client'

export interface QuotaSummaryItem {
  project_id: number
  project_name: string
  daily_limit: number
  units_used: number
  remaining: number
  percentage_used: number
  videos_today: number
  video_limit: number
}

export interface QuotaSummaryResponse {
  projects: QuotaSummaryItem[]
}

export interface QuotaEstimateResponse {
  estimated_cost: number
  remaining_quota: number
  sufficient: boolean
}

export async function getQuotaSummary(): Promise<QuotaSummaryResponse> {
  return apiFetch<QuotaSummaryResponse>('/quota/summary')
}

export async function getQuotaEstimate(
  numVideos: number,
  hasThumbnail: boolean,
): Promise<QuotaEstimateResponse> {
  return apiFetch<QuotaEstimateResponse>('/quota/estimate', {
    method: 'POST',
    body: JSON.stringify({ file_count: numVideos, has_thumbnail: hasThumbnail }),
  })
}
