import { useEffect, useRef, useCallback, useState } from 'react'
import { resolveWebSocketBase } from '../api/client'

export interface UploadEvent {
  type:
    | 'job_started'
    | 'upload_started'
    | 'upload_progress'
    | 'upload_completed'
    | 'thumbnail_applying'
    | 'thumbnail_set'
    | 'comment_posting'
    | 'comment_posted'
    | 'youtube_processing_started'
    | 'youtube_processing_progress'
    | 'youtube_processing_completed'
    | 'verification_failed'
    | 'thumbnail_failed'
    | 'comment_failed'
    | 'upload_failed'
    | 'job_completed'
    | 'pong'
  job_id?: string
  upload_id?: number
  file_name?: string
  channel_name?: string
  percent?: number
  youtube_url?: string
  thumbnail_error?: string
  error?: string
  total_files?: number
  succeeded?: number
  failed?: number
  upload_status?: string
  processing_status?: string
  parts_processed?: number
  parts_total?: number
  final_status?: string | null
  has_thumbnail?: boolean
  has_comment?: boolean
}

export function useUploadWebSocket(jobId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const [events, setEvents] = useState<UploadEvent[]>([])
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    if (!jobId) return

    let cancelled = false
    // The WebSocket constructor is synchronous, but the backend base URL is
    // resolved asynchronously when running inside Electron (an IPC round
    // trip). Defer the construction until the URL is ready, and abort it
    // if the effect re-runs before we get there.
    resolveWebSocketBase().then((base) => {
      if (cancelled) return
      const ws = new WebSocket(`${base}/ws/uploads/${jobId}`)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => setConnected(false)
      ws.onmessage = (event) => {
        try {
          const data: UploadEvent = JSON.parse(event.data)
          setEvents((prev) => [...prev, data])
        } catch {}
      }
    })

    return () => {
      cancelled = true
    }
  }, [jobId])

  useEffect(() => {
    const cleanup = connect()
    return () => {
      cleanup?.()
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  const reset = useCallback(() => {
    setEvents([])
  }, [])

  return { events, connected, reset }
}
