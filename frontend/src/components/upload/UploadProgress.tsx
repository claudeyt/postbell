import { useState, useEffect, useRef } from 'react'
import { CheckCircle, XCircle, Loader2, ExternalLink, AlertTriangle } from 'lucide-react'
import type { JobProgress, UploadFileStatus } from '../../hooks/useUploadProgress'
import { getVideoProcessingStatus } from '../../api/uploads'
import StageTimeline from './StageTimeline'

function stageLabel(file: UploadFileStatus): string {
  switch (file.stage) {
    case 'preparing':
      return 'Preparando…'
    case 'uploading':
      return `Enviando: ${Math.round(file.percent)}%`
    case 'verifying':
      if (file.verify_parts_total && file.verify_parts_processed != null) {
        return `Verificando no YouTube (${file.verify_parts_processed}/${file.verify_parts_total} partes)`
      }
      return 'Verificando no YouTube'
    case 'thumbnail':
      return 'Aplicando thumbnail'
    case 'comment':
      return 'Postando comentário'
    case 'done':
      return 'Concluído'
    case 'failed':
      return 'Falhou'
    default:
      return ''
  }
}

function ProcessingBadge({ uploadId }: { uploadId: number }) {
  const [processingStatus, setProcessingStatus] = useState<string>('unknown')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      try {
        const result = await getVideoProcessingStatus(uploadId)
        if (cancelled) return
        const status = result.processing_status ?? 'unknown'
        setProcessingStatus(status)

        if (status === 'succeeded' || status === 'terminated') {
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
        }
      } catch {
        // Ignore errors, keep polling
      }
    }

    poll()
    intervalRef.current = setInterval(poll, 10000)

    return () => {
      cancelled = true
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [uploadId])

  if (processingStatus === 'succeeded' || processingStatus === 'terminated') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-400">
        <CheckCircle className="w-3 h-3" />
        Available
      </span>
    )
  }

  if (processingStatus === 'processing' || processingStatus === 'unknown') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-yellow-400">
        <Loader2 className="w-3 h-3 animate-spin" />
        Processing...
      </span>
    )
  }

  return null
}

interface UploadProgressProps {
  progress: JobProgress
  /** Optional — when omitted, the trailing "Done" button is hidden. This lets
   * the same component render both the live-upload flow (Dashboard passes
   * onDone to reset the form) and the auto-restored job view (no reset, the
   * user dismisses via JobHeader's X). */
  onDone?: () => void
}

export default function UploadProgress({ progress, onDone }: UploadProgressProps) {
  const overallPercent = progress.total > 0
    ? Math.round(((progress.succeeded + progress.failed) / progress.total) * 100)
    : 0

  return (
    <div className="space-y-4">
      {/* Overall progress */}
      <div className="bg-gray-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-white flex items-center gap-2">
            {progress.isComplete ? 'Upload Complete' : progress.total === 0 ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Connecting...
              </>
            ) : 'Uploading...'}
          </span>
          <span className="text-sm text-gray-400">
            {progress.succeeded + progress.failed}/{progress.total}
          </span>
        </div>
        <div className="w-full bg-gray-700 rounded-full h-2">
          <div
            className="bg-indigo-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${overallPercent}%` }}
          />
        </div>
        {progress.isComplete && (
          <div className="mt-3 flex items-center justify-between">
            <div className="flex gap-4 text-sm">
              {progress.succeeded > 0 && (
                <span className="text-green-400">{progress.succeeded} succeeded</span>
              )}
              {progress.failed > 0 && (
                <span className="text-red-400">{progress.failed} failed</span>
              )}
            </div>
            {onDone && (
              <button
                onClick={onDone}
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-md transition-colors"
              >
                Done
              </button>
            )}
          </div>
        )}
      </div>

      {/* Per-file progress */}
      <div className="bg-gray-800 rounded-lg overflow-hidden divide-y divide-gray-700">
        {progress.files.map((file) => (
          <div key={file.upload_id} className="px-4 py-3">
            <div className="flex items-center gap-3 mb-1">
              {file.status === 'uploading' && <Loader2 className="w-4 h-4 text-indigo-400 animate-spin shrink-0" />}
              {file.status === 'completed' && !file.thumbnail_error && <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />}
              {file.status === 'completed' && file.thumbnail_error && <AlertTriangle className="w-4 h-4 text-yellow-400 shrink-0" />}
              {file.status === 'failed' && <XCircle className="w-4 h-4 text-red-400 shrink-0" />}
              <span className="text-sm text-white truncate flex-1">{file.file_name}</span>
              <span className="text-xs text-gray-400 shrink-0">{file.channel_name}</span>
              {file.youtube_url && (
                <a
                  href={file.youtube_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-indigo-400 hover:text-indigo-300 shrink-0"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              )}
              {file.status === 'completed' && file.upload_id && (
                <ProcessingBadge uploadId={file.upload_id} />
              )}
            </div>
            {(file.status === 'uploading' || file.status === 'failed') && (
              <div className="mt-2 space-y-1.5">
                <StageTimeline
                  current={file.stage}
                  hasThumbnail={file.has_thumbnail}
                  hasComment={file.has_comment}
                  stageErrors={file.stage_errors}
                />
                <div className="text-xs text-gray-400">{stageLabel(file)}</div>
                {file.status === 'uploading' && file.stage !== 'done' && (
                  <div className="w-full bg-gray-700 rounded-full h-1.5">
                    {file.stage === 'uploading' ? (
                      <div
                        className="bg-indigo-500 h-1.5 rounded-full transition-all duration-300"
                        style={{ width: `${file.percent}%` }}
                      />
                    ) : file.stage === 'verifying' ? (
                      file.verify_percent != null ? (
                        <div
                          className="bg-yellow-500 h-1.5 rounded-full transition-all duration-300"
                          style={{ width: `${file.verify_percent}%` }}
                        />
                      ) : (
                        <div className="bg-yellow-500/60 h-1.5 rounded-full animate-pulse w-full" />
                      )
                    ) : (
                      <div className="bg-indigo-500/60 h-1.5 rounded-full animate-pulse w-full" />
                    )}
                  </div>
                )}
              </div>
            )}
            {file.error && (
              <p className="text-xs text-red-400 mt-1">{file.error}</p>
            )}
            {file.status === 'completed' && file.thumbnail_error && (
              <div className="mt-1">
                <p className="text-xs text-yellow-400">Video uploaded — thumbnail failed</p>
                <p className="text-xs text-gray-500 mt-0.5">{file.thumbnail_error}</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
