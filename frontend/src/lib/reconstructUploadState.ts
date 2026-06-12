import type { Upload } from '../types'
import type { UploadFileStatus, StageKey } from '../hooks/useUploadProgress'

/**
 * Reconstruct a single UploadFileStatus row from a persisted Upload row
 * returned by GET /api/uploads/job/{job_id}. The shape matches what
 * useUploadProgress produces from live websocket events, so the same UI
 * (UploadProgressView) can render either source uniformly.
 */
export function reconstructUploadState(
  row: Upload,
  channelName: string,
): UploadFileStatus {
  const stage: StageKey =
    row.status === 'completed'
      ? 'done'
      : row.status === 'failed'
        ? 'failed'
        : row.status === 'uploading' || row.status === 'processing'
          ? 'uploading'
          : 'preparing'

  const stage_errors: UploadFileStatus['stage_errors'] = {}
  if (row.verification_error) stage_errors.verifying = row.verification_error
  if (row.thumbnail_error) stage_errors.thumbnail = row.thumbnail_error
  if (row.comment_error) stage_errors.comment = row.comment_error

  return {
    upload_id: row.id,
    file_name: row.file_name,
    channel_name: channelName,
    percent: row.status === 'completed' ? 100 : (row.progress_percent ?? 0),
    status:
      row.status === 'processing'
        ? 'uploading'
        : (row.status as UploadFileStatus['status']),
    youtube_url: row.youtube_url,
    thumbnail_error: row.thumbnail_error ?? null,
    error: row.error_message ?? null,
    stage,
    has_thumbnail: !!row.thumbnail_path,
    has_comment: !!row.channel_has_default_comment,
    verify_parts_processed: null,
    verify_parts_total: null,
    verify_percent: null,
    stage_errors,
  }
}
