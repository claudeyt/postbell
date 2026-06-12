export interface Project {
  id: number
  name: string
  client_secret_path: string
  daily_quota_limit: number
  created_at: string
}

export interface Account {
  id: number
  email: string
  project_id: number
  token_valid: boolean
  created_at: string
}

export interface Channel {
  id: number
  account_id: number
  channel_id: string
  channel_name: string
  alias: string | null
  language_code: string
  default_description: string
  default_comment: string
  default_tags?: string | null
  thumbnail_url: string | null
  is_active: boolean
  created_at: string
  group_id?: number | null
  display_order?: number
  custom_schedule_time?: string | null
}

export interface LanguageSchedule {
  language_code: string
  time_brt: string  // 'HH:MM'
  updated_at: string
}

export interface ResolvedSchedule {
  channel_id: number
  channel_name: string
  language_code: string | null
  resolved_time: string | null
  source: 'channel' | 'language' | 'none'
  scheduled_at_brt: string | null
  scheduled_at_utc: string | null
  already_passed: boolean
  error: string | null
}

export interface ChannelGroup {
  id: number
  name: string
  display_order: number
  created_at: string
}

export interface Upload {
  id: number
  job_id: string
  channel_id: number
  file_path?: string
  file_name: string
  title: string
  description?: string
  tags?: string
  privacy?: 'public' | 'private' | 'unlisted'
  scheduled_at?: string | null
  thumbnail_path?: string | null
  detected_language?: string | null
  detection_method?: string | null
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'failed'
  youtube_video_id: string | null
  youtube_url: string | null
  progress_percent: number
  error_message: string | null
  verification_error?: string | null
  thumbnail_error?: string | null
  comment_error?: string | null
  channel_has_default_comment?: boolean
  quota_cost?: number
  created_at: string
  completed_at: string | null
}

export interface JobSummary {
  job_id: string
  started_at: string
  total: number
  completed: number
  failed: number
  in_flight: number
  status: 'running' | 'partial' | 'failed' | 'completed'
}

// JobDetail is the array shape returned by GET /api/uploads/job/{job_id}
export type JobDetail = Upload[]

export interface QuotaUsage {
  id: number
  project_id: number
  date: string
  units_used: number
}

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

export interface ChannelAnalytics {
  channel_id: number
  channel_name: string
  available: boolean
  error: string | null
  views_48h: number
  views_window_dates: string[]
  subscribers_last: number
  subscribers_last_date: string | null
  revenue_last: number | null
  revenue_last_date: string | null
}

export interface AnalyticsAverages {
  views_48h: number
  subscribers_last: number
  revenue_last: number | null
  channel_count: number
}

export interface AnalyticsSummaryResponse {
  channels: ChannelAnalytics[]
  averages: AnalyticsAverages
  note: string
}
