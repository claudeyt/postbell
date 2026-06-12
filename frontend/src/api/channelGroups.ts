import type { ChannelGroup } from '../types'

const BASE = '/api/channel-groups'

export async function listGroups(): Promise<ChannelGroup[]> {
  const r = await fetch(BASE)
  if (!r.ok) throw new Error('Failed to load groups')
  return r.json()
}

export async function createGroup(name: string): Promise<ChannelGroup> {
  const r = await fetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!r.ok) throw new Error('Failed to create group')
  return r.json()
}

export async function updateGroup(
  id: number,
  data: { name?: string; display_order?: number },
): Promise<ChannelGroup> {
  const r = await fetch(`${BASE}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!r.ok) throw new Error('Failed to update group')
  return r.json()
}

export async function deleteGroup(id: number): Promise<void> {
  const r = await fetch(`${BASE}/${id}`, { method: 'DELETE' })
  if (!r.ok) throw new Error('Failed to delete group')
}

export async function reorderGroups(ids: number[]): Promise<void> {
  const r = await fetch(`${BASE}/reorder`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  })
  if (!r.ok) throw new Error('Failed to reorder groups')
}
