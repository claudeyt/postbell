import type { LanguageSchedule } from '../types'

const BASE = '/api/language-schedules'

export async function listSchedules(): Promise<LanguageSchedule[]> {
  const r = await fetch(BASE)
  if (!r.ok) throw new Error('Failed to load schedules')
  return r.json()
}

export async function upsertSchedule(lang: string, time_brt: string): Promise<LanguageSchedule> {
  const r = await fetch(`${BASE}/${encodeURIComponent(lang)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ time_brt }),
  })
  if (!r.ok) throw new Error('Failed to upsert schedule')
  return r.json()
}

export async function deleteSchedule(lang: string): Promise<void> {
  const r = await fetch(`${BASE}/${encodeURIComponent(lang)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error('Failed to delete schedule')
}
