import { useMemo } from 'react'
import type { UploadEvent } from './useWebSocket'

export type StageKey =
  | 'preparing'
  | 'uploading'
  | 'verifying'
  | 'thumbnail'
  | 'comment'
  | 'done'
  | 'failed'

export interface StageErrors {
  verifying?: string
  thumbnail?: string
  comment?: string
}

export interface UploadFileStatus {
  upload_id: number
  file_name: string
  channel_name: string
  percent: number
  status: 'pending' | 'uploading' | 'completed' | 'failed'
  youtube_url: string | null
  thumbnail_error: string | null
  error: string | null
  stage: StageKey
  has_thumbnail: boolean
  has_comment: boolean
  verify_parts_processed: number | null
  verify_parts_total: number | null
  verify_percent: number | null
  stage_errors: StageErrors
}

export interface JobProgress {
  total: number
  succeeded: number
  failed: number
  uploading: number
  isComplete: boolean
  files: UploadFileStatus[]
}

export interface ReducerSeed {
  files: Map<number, UploadFileStatus>
  total: number
  succeeded: number
  failed: number
  isComplete: boolean
}

export function emptySeed(): ReducerSeed {
  return {
    files: new Map<number, UploadFileStatus>(),
    total: 0,
    succeeded: 0,
    failed: 0,
    isComplete: false,
  }
}

/**
 * Apply a single websocket event to a ReducerSeed, mutating it in place.
 * Shared by both the live useUploadProgress hook (which folds events arriving
 * in real time) and useJob (which seeds from REST then folds in WS events
 * once a running job is selected).
 */
export function applyUploadEvent(state: ReducerSeed, event: UploadEvent): void {
  const { files } = state
  switch (event.type) {
    case 'job_started':
      state.total = event.total_files || 0
      break
    case 'upload_started':
      if (event.upload_id != null) {
        files.set(event.upload_id, {
          upload_id: event.upload_id,
          file_name: event.file_name || '',
          channel_name: event.channel_name || '',
          percent: 0,
          status: 'uploading',
          youtube_url: null,
          thumbnail_error: null,
          error: null,
          stage: 'preparing',
          has_thumbnail: !!event.has_thumbnail,
          has_comment: !!event.has_comment,
          verify_parts_processed: null,
          verify_parts_total: null,
          verify_percent: null,
          stage_errors: {},
        })
      }
      break
    case 'upload_progress':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.percent = event.percent || 0
        if (file.stage === 'preparing' && (event.percent || 0) > 0) {
          file.stage = 'uploading'
        }
      }
      break
    case 'youtube_processing_started':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.stage = 'verifying'
      }
      break
    case 'youtube_processing_progress':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.stage = 'verifying'
        file.verify_parts_processed = event.parts_processed ?? null
        file.verify_parts_total = event.parts_total ?? null
        file.verify_percent = event.percent ?? null
      }
      break
    case 'youtube_processing_completed':
      // Stage remains 'verifying' until the next stage event arrives.
      break
    case 'verification_failed':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.stage_errors = {
          ...file.stage_errors,
          verifying: event.error || 'unknown',
        }
      }
      break
    case 'thumbnail_failed':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.stage_errors = {
          ...file.stage_errors,
          thumbnail: event.error || 'unknown',
        }
      }
      break
    case 'comment_failed':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.stage_errors = {
          ...file.stage_errors,
          comment: event.error || 'unknown',
        }
      }
      break
    case 'thumbnail_applying':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.stage = 'thumbnail'
        file.has_thumbnail = true
      }
      break
    case 'thumbnail_set':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.has_thumbnail = true
      }
      break
    case 'comment_posting':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.stage = 'comment'
        file.has_comment = true
      }
      break
    case 'comment_posted':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.has_comment = true
      }
      break
    case 'upload_completed':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.status = 'completed'
        file.percent = 100
        file.youtube_url = event.youtube_url || null
        file.thumbnail_error = event.thumbnail_error || null
        file.stage = 'done'
      }
      break
    case 'upload_failed':
      if (event.upload_id != null && files.has(event.upload_id)) {
        const file = files.get(event.upload_id)!
        file.status = 'failed'
        file.error = event.error || 'Unknown error'
        file.stage = 'failed'
      }
      break
    case 'job_completed':
      state.succeeded = event.succeeded || 0
      state.failed = event.failed || 0
      state.isComplete = true
      break
  }
}

export function seedToJobProgress(seed: ReducerSeed): JobProgress {
  return {
    total: seed.total,
    succeeded: seed.succeeded,
    failed: seed.failed,
    uploading: Array.from(seed.files.values()).filter(f => f.status === 'uploading').length,
    isComplete: seed.isComplete,
    files: Array.from(seed.files.values()),
  }
}

export function useUploadProgress(events: UploadEvent[]): JobProgress {
  return useMemo(() => {
    const seed = emptySeed()
    for (const event of events) {
      applyUploadEvent(seed, event)
    }
    return seedToJobProgress(seed)
  }, [events])
}
