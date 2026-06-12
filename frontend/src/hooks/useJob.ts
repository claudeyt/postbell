import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getJob } from '../api/jobs'
import { getChannels } from '../api/channels'
import { resolveWebSocketBase } from '../api/client'
import { reconstructUploadState } from '../lib/reconstructUploadState'
import {
  applyUploadEvent,
  emptySeed,
  seedToJobProgress,
  type JobProgress,
  type ReducerSeed,
} from './useUploadProgress'
import type { UploadEvent } from './useWebSocket'
import type { Channel, JobDetail } from '../types'

export interface JobSummaryDerived {
  total: number
  completed: number
  failed: number
  in_flight: number
  status: 'running' | 'partial' | 'failed' | 'completed'
}

export interface UseJobResult {
  progress: JobProgress | null
  jobStartedAt: string | null
  summary: JobSummaryDerived | null
  isLoading: boolean
  isError: boolean
  refetch: () => void
  connected: boolean
}

function deriveStatus(rows: JobDetail): JobSummaryDerived['status'] {
  const statuses = rows.map(r => r.status)
  if (statuses.some(s => s === 'pending' || s === 'uploading' || s === 'processing')) {
    return 'running'
  }
  if (statuses.every(s => s === 'completed')) return 'completed'
  if (statuses.every(s => s === 'failed')) return 'failed'
  return 'partial'
}

function buildSeedFromRows(
  rows: JobDetail,
  channelsById: Map<number, Channel>,
): ReducerSeed {
  const seed = emptySeed()
  seed.total = rows.length
  let completed = 0
  let failed = 0
  for (const row of rows) {
    const ch = channelsById.get(row.channel_id)
    const channelName = ch ? ch.channel_name : ''
    const file = reconstructUploadState(row, channelName)
    seed.files.set(file.upload_id, file)
    if (file.status === 'completed') completed++
    if (file.status === 'failed') failed++
  }
  seed.succeeded = completed
  seed.failed = failed
  // isComplete only when nothing is in-flight
  seed.isComplete = rows.every(
    r =>
      r.status !== 'pending' &&
      r.status !== 'uploading' &&
      r.status !== 'processing',
  )
  return seed
}

/**
 * useJob — loads a job by id from the REST endpoint, reconstructs the
 * timeline, and (if the job is still running) layers in live websocket
 * events on top of that seed using the SAME reducer as useUploadProgress.
 *
 * Pass null to disable.
 */
export function useJob(jobId: string | null): UseJobResult {
  const jobQuery = useQuery<JobDetail>({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId as string),
    enabled: !!jobId,
  })

  const channelsQuery = useQuery({
    queryKey: ['channels'],
    queryFn: getChannels,
  })

  // Live websocket events that arrive after the REST seed.
  const [liveEvents, setLiveEvents] = useState<UploadEvent[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  // Reset live events whenever the job id changes.
  useEffect(() => {
    setLiveEvents([])
    setConnected(false)
  }, [jobId])

  const rows = jobQuery.data ?? null
  const isRunning = useMemo(() => {
    if (!rows || rows.length === 0) return false
    return deriveStatus(rows) === 'running'
  }, [rows])

  // Open WebSocket only when the job is currently running.
  useEffect(() => {
    if (!jobId || !isRunning) return

    let cancelled = false
    // resolveWebSocketBase is async (IPC round trip in Electron); defer the
    // WebSocket construction until the URL is known. If the effect cleans
    // up first, abort the in-flight resolve.
    resolveWebSocketBase().then((base) => {
      if (cancelled) return
      const ws = new WebSocket(`${base}/ws/uploads/${jobId}`)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => setConnected(false)
      ws.onmessage = (event) => {
        try {
          const data: UploadEvent = JSON.parse(event.data)
          setLiveEvents(prev => [...prev, data])
        } catch {
          // ignore malformed
        }
      }
    })

    return () => {
      cancelled = true
      wsRef.current?.close()
      wsRef.current = null
      setConnected(false)
    }
  }, [jobId, isRunning])

  const channelsById = useMemo(() => {
    const map = new Map<number, Channel>()
    for (const c of channelsQuery.data ?? []) {
      map.set(c.id, c)
    }
    return map
  }, [channelsQuery.data])

  const progress: JobProgress | null = useMemo(() => {
    if (!rows) return null
    const seed = buildSeedFromRows(rows, channelsById)
    for (const ev of liveEvents) {
      applyUploadEvent(seed, ev)
    }
    return seedToJobProgress(seed)
  }, [rows, channelsById, liveEvents])

  const summary: JobSummaryDerived | null = useMemo(() => {
    if (!rows) return null
    const completed = rows.filter(r => r.status === 'completed').length
    const failed = rows.filter(r => r.status === 'failed').length
    const in_flight = rows.filter(
      r =>
        r.status === 'pending' ||
        r.status === 'uploading' ||
        r.status === 'processing',
    ).length
    // If we have live events, recompute counts from progress for freshness.
    if (progress) {
      const liveCompleted = progress.files.filter(f => f.status === 'completed').length
      const liveFailed = progress.files.filter(f => f.status === 'failed').length
      const liveInFlight = progress.files.filter(f => f.status === 'uploading').length
      const total = progress.files.length || rows.length
      const allTerminal = liveInFlight === 0
      const status: JobSummaryDerived['status'] = !allTerminal
        ? 'running'
        : liveCompleted === total
          ? 'completed'
          : liveFailed === total
            ? 'failed'
            : 'partial'
      return {
        total,
        completed: liveCompleted,
        failed: liveFailed,
        in_flight: liveInFlight,
        status,
      }
    }
    return {
      total: rows.length,
      completed,
      failed,
      in_flight,
      status: deriveStatus(rows),
    }
  }, [rows, progress])

  const jobStartedAt = useMemo(() => {
    if (!rows || rows.length === 0) return null
    // rows are returned in created_at ASC
    return rows[0].created_at
  }, [rows])

  if (!jobId) {
    return {
      progress: null,
      jobStartedAt: null,
      summary: null,
      isLoading: false,
      isError: false,
      refetch: () => {},
      connected: false,
    }
  }

  return {
    progress,
    jobStartedAt,
    summary,
    isLoading: jobQuery.isLoading,
    isError: jobQuery.isError,
    refetch: () => {
      setLiveEvents([])
      jobQuery.refetch()
    },
    connected,
  }
}
