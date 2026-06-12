import { apiFetch } from './client'
import type { Project } from '../types'

export interface CreateProjectPayload {
  name: string
  client_secret_path: string
  daily_quota_limit: number
}

export function getProjects(): Promise<Project[]> {
  return apiFetch<Project[]>('/projects')
}

export function createProject(payload: CreateProjectPayload): Promise<Project> {
  return apiFetch<Project>('/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteProject(projectId: number): Promise<void> {
  return apiFetch(`/projects/${projectId}`, { method: 'DELETE' })
}

export async function uploadClientSecret(file: File): Promise<{ path: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch('/api/projects/upload-secret', {
    method: 'POST',
    body: formData,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(body.detail || 'Upload failed')
  }
  return response.json()
}
