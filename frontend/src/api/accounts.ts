import { apiFetch } from './client'
import type { Account, Channel } from '../types'

export async function getAccounts(): Promise<Account[]> {
  return apiFetch<Account[]>('/accounts')
}

export async function startAuth(
  projectId: number,
): Promise<{ auth_url: string; state: string }> {
  return apiFetch('/accounts/auth/start', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId }),
  })
}

/**
 * Kick off the installed-app OAuth flow (Electron mode).
 *
 * The backend BLOCKS this request for up to 5 minutes while it spawns a
 * temporary loopback listener and waits for the user to complete the consent
 * screen in their default browser. There is no popup window — Python's
 * ``webbrowser.open`` opens it directly. The response arrives only once the
 * full handshake completes, so callers should set their UI to a "waiting"
 * state for the duration.
 */
export async function startInstalledAuth(projectId: number): Promise<{
  email: string
  account_id: number
  project_id: number
  channels_added: number
  total_channels: number
}> {
  return apiFetch('/accounts/auth/start_installed', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId }),
  })
}

export async function deleteAccount(id: number): Promise<void> {
  await apiFetch(`/accounts/${id}`, { method: 'DELETE' })
}

export async function getAccountChannels(
  accountId: number,
): Promise<Channel[]> {
  return apiFetch<Channel[]>(`/accounts/${accountId}/channels`)
}

export async function getAccountStatus(
  accountId: number,
): Promise<{ token_valid: boolean }> {
  return apiFetch(`/accounts/${accountId}/status`)
}

export function syncChannels(
  accountId: number,
): Promise<{ synced: number; new_channels: number }> {
  return apiFetch(`/accounts/${accountId}/sync-channels`, { method: 'POST' })
}
