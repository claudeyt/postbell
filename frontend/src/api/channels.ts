import { apiFetch } from './client'
import type { Channel } from '../types'

export async function getChannels(): Promise<Channel[]> {
  return apiFetch<Channel[]>('/channels')
}

export async function getChannelsByLanguage(): Promise<
  Record<string, Channel[]>
> {
  return apiFetch<Record<string, Channel[]>>('/channels/by-language')
}

export async function updateChannel(
  id: number,
  data: Partial<Pick<Channel, 'language_code' | 'alias' | 'is_active' | 'default_description' | 'default_comment' | 'default_tags' | 'custom_schedule_time'>>,
): Promise<Channel> {
  return apiFetch<Channel>(`/channels/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function pullYoutubeTagsForChannel(id: number): Promise<Channel> {
  return apiFetch<Channel>(`/channels/${id}/pull-youtube-tags`, {
    method: 'POST',
  })
}

export interface PullYoutubeTagsResult {
  channel_id: number
  channel_name: string
  ok: boolean
  error?: string
  tag_count?: number
}

export interface PullYoutubeTagsAllResponse {
  updated: number
  failed: number
  results: PullYoutubeTagsResult[]
}

export async function pullYoutubeTagsForAll(): Promise<PullYoutubeTagsAllResponse> {
  return apiFetch<PullYoutubeTagsAllResponse>('/channels/pull-youtube-tags/all', {
    method: 'POST',
  })
}

export async function autoDetectLanguages(): Promise<{
  total_checked: number
  updated: number
  results: { channel: string; language: string | null }[]
}> {
  return apiFetch('/channels/auto-detect-languages', { method: 'POST' })
}

export interface AutoDetectResult {
  channel_id: number
  channel_name: string
  detected_language: string | null
  method: string
  set: boolean
}

export interface AutoDetectResponse {
  updated: number
  skipped_unknown: number
  skipped_already_set: number
  results: AutoDetectResult[]
}

export async function autoDetectChannelLanguages(): Promise<AutoDetectResponse> {
  const r = await fetch('/api/channels/auto-detect-languages', { method: 'POST' })
  if (!r.ok) throw new Error('Failed to auto-detect channel languages')
  return r.json()
}

export async function syncChannels(
  accountId: number,
): Promise<{ synced: number }> {
  return apiFetch<{ synced: number }>(`/channels/${accountId}/sync`, {
    method: 'POST',
  })
}

export async function moveChannelToGroup(
  channelId: number,
  group_id: number | null,
): Promise<Channel> {
  const r = await fetch(`/api/channels/${channelId}/group`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_id }),
  })
  if (!r.ok) throw new Error('Failed to move channel')
  return r.json()
}

export async function reorderChannels(
  ids: number[],
  group_id: number | null,
): Promise<void> {
  const r = await fetch(`/api/channels/reorder`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, group_id }),
  })
  if (!r.ok) throw new Error('Failed to reorder channels')
}
