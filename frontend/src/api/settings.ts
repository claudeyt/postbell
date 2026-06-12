import { apiFetch } from './client'

export interface SettingsResponse {
  gemini_api_key: string
  upload_chunk_size_mb: number
  youtube_daily_quota: number
  default_privacy: string
  default_description: string
  default_tags: string[]
}

export interface SettingsUpdate {
  gemini_api_key?: string
  upload_chunk_size_mb?: number
  youtube_daily_quota?: number
  default_privacy?: string
  default_description?: string
  default_tags?: string[]
}

export function getSettings(): Promise<SettingsResponse> {
  return apiFetch<SettingsResponse>('/settings')
}

export function updateSettings(data: SettingsUpdate): Promise<SettingsResponse> {
  return apiFetch<SettingsResponse>('/settings', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function getGeminiKey(): Promise<{ gemini_api_key: string }> {
  return apiFetch('/settings/gemini-key')
}

export function testGeminiKey(): Promise<{ success: boolean; response?: string; error?: string }> {
  return apiFetch('/settings/test-gemini', { method: 'POST' })
}
