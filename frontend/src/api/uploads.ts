import { apiFetch } from './client'
import type { Upload, ResolvedSchedule } from '../types'

export interface UploadsListResponse {
  items: Upload[]
  total: number
  page: number
  per_page: number
}

export interface GetUploadsParams {
  page?: number
  per_page?: number
  status?: string
  channel_id?: number
}

export async function getUploads(params: GetUploadsParams = {}): Promise<UploadsListResponse> {
  const query = new URLSearchParams()
  if (params.page !== undefined) query.set('page', String(params.page))
  if (params.per_page !== undefined) query.set('per_page', String(params.per_page))
  if (params.status) query.set('status', params.status)
  if (params.channel_id !== undefined) query.set('channel_id', String(params.channel_id))
  const qs = query.toString()
  return apiFetch<UploadsListResponse>(`/uploads${qs ? `?${qs}` : ''}`)
}

interface FileInfo {
  name: string
  size: number
  path: string
}

interface RoutingEntry {
  file_name: string
  file_path: string
  detected_language: string | null
  detection_method: string | null
  channel_id: number | null
  channel_name: string | null
  thumbnail_path?: string | null
  title?: string
  scheduled_at?: string | null
}

interface PrepareResponse {
  routing: RoutingEntry[]
  unroutable: RoutingEntry[]
}

export type { RoutingEntry, PrepareResponse }

export async function prepareUpload(
  files: FileInfo[],
  selectedChannelIds: number[],
): Promise<PrepareResponse> {
  return apiFetch<PrepareResponse>('/uploads/prepare', {
    method: 'POST',
    body: JSON.stringify({
      files,
      selected_channel_ids: selectedChannelIds,
    }),
  })
}

export interface StartUploadData {
  job_id: string
  routing: RoutingEntry[]
  thumbnail_path: string | null
  privacy: string
  description: string
  tags: string
  scheduled_at: string | null
  stagger_minutes: number | null
}

export interface JobStatusUpload {
  id: number
  file_name: string
  status: string
  progress_percent: number
  youtube_url: string | null
  error_message: string | null
}

export interface JobStatusResponse {
  job_id: string
  total: number
  completed: number
  failed: number
  uploading: number
  pending: number
  uploads: JobStatusUpload[]
}

export async function startUpload(data: StartUploadData): Promise<{ job_id: string }> {
  return apiFetch<{ job_id: string }>('/uploads/start', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  return apiFetch<JobStatusResponse>(`/uploads/job/${jobId}`)
}

export async function cancelJob(jobId: string): Promise<void> {
  await apiFetch(`/uploads/job/${jobId}/cancel`, { method: 'POST' })
}

export interface ScheduledUpload {
  id: number
  job_id: string
  file_name: string
  title: string
  channel_id: number
  privacy: string
  scheduled_at: string | null
  status: string
}

export interface ScheduledUploadsResponse {
  items: ScheduledUpload[]
}

export async function getScheduledUploads(): Promise<ScheduledUploadsResponse> {
  return apiFetch<ScheduledUploadsResponse>('/uploads/scheduled')
}

export interface VideoProcessingStatus {
  upload_status: string
  privacy_status: string
  processing_status: string
}

export async function getVideoProcessingStatus(uploadId: number): Promise<VideoProcessingStatus> {
  return apiFetch<VideoProcessingStatus>(`/uploads/video-status/${uploadId}`)
}

export interface YoutubeEditData {
  title?: string
  description?: string
  tags?: string
  privacy?: string
}

export async function updateYoutubeVideo(uploadId: number, data: YoutubeEditData): Promise<Upload> {
  return apiFetch<Upload>(`/uploads/${uploadId}/youtube`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function resolveSchedule(
  channel_ids: number[],
  target_date?: string,
): Promise<ResolvedSchedule[]> {
  const body: Record<string, unknown> = { channel_ids }
  if (target_date) body.target_date = target_date
  const r = await fetch('/api/uploads/resolve-schedule', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error('Failed to resolve schedule')
  return r.json()
}

// Threshold above which we switch from the single-request XHR upload to the
// chunked upload path. 100MB is a safe boundary: small enough to never hit
// most proxy/server timeouts, large enough to avoid the per-chunk overhead
// for everyday small files. See backend/api/uploads.py for the receiving end.
const CHUNKED_UPLOAD_THRESHOLD_BYTES = 100 * 1024 * 1024 // 100 MB
const CHUNK_SIZE_BYTES = 50 * 1024 * 1024 // 50 MB per chunk

/**
 * Upload a single File to the backend in 50MB chunks via /upload-chunk + /finalize-chunked.
 *
 * Chunks are sent SEQUENTIALLY (not in parallel) because:
 *   * the upload-bandwidth bottleneck is usually the client's link, so parallelism
 *     buys nothing,
 *   * sequential keeps progress monotonic and the retry story trivial,
 *   * the backend dup-detection only meaningfully helps for re-sends of the
 *     same index, which only happen on sequential retries.
 *
 * `onProgress` (if provided) is called once after each successful chunk with
 * the cumulative percent (0-100), then once more on finalize success.
 */
export async function uploadFileChunked(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<{ path: string; name: string }> {
  const uploadId = crypto.randomUUID()
  const total = Math.max(1, Math.ceil(file.size / CHUNK_SIZE_BYTES))

  for (let i = 0; i < total; i++) {
    const start = i * CHUNK_SIZE_BYTES
    const end = Math.min(start + CHUNK_SIZE_BYTES, file.size)
    // file.slice returns a Blob view — no copy until fetch reads the body.
    const chunk = file.slice(start, end)

    const resp = await fetch('/api/uploads/upload-chunk', {
      method: 'POST',
      body: chunk,
      headers: {
        'X-Upload-Id': uploadId,
        'X-Chunk-Index': String(i),
        'X-Total-Chunks': String(total),
        'X-Filename': file.name,
      },
    })
    if (!resp.ok) {
      let detail = `status ${resp.status}`
      try {
        const j = await resp.json()
        if (j && typeof j.detail === 'string') detail = j.detail
      } catch {
        // body wasn't JSON; fall through with the status-only message
      }
      throw new Error(`Chunk ${i} upload failed: ${detail}`)
    }
    if (onProgress) {
      onProgress(Math.round(((i + 1) / total) * 100))
    }
  }

  const finalizeResp = await fetch('/api/uploads/finalize-chunked', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      upload_id: uploadId,
      filename: file.name,
      total_chunks: total,
    }),
  })
  if (!finalizeResp.ok) {
    let detail = `status ${finalizeResp.status}`
    try {
      const j = await finalizeResp.json()
      if (j && typeof j.detail === 'string') detail = j.detail
    } catch {
      // body wasn't JSON; keep status-only message
    }
    throw new Error(`Finalize failed: ${detail}`)
  }
  return finalizeResp.json()
}

export async function uploadFileToServer(
  file: File,
  onProgress?: (percent: number) => void
): Promise<{ path: string; name: string }> {
  // Dispatch: large files use the chunked path so we avoid a single
  // long-lived HTTP connection (proxy timeouts, transient drops) and so the
  // user sees more responsive progress. Small files keep the existing XHR
  // path — same payload shape, fewer round trips.
  if (file.size > CHUNKED_UPLOAD_THRESHOLD_BYTES) {
    return uploadFileChunked(file, onProgress)
  }

  const formData = new FormData()
  formData.append('file', file)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/uploads/upload-file')

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100))
        }
      }
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText))
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`))
      }
    }

    xhr.onerror = () => reject(new Error('Upload failed'))
    xhr.send(formData)
  })
}
