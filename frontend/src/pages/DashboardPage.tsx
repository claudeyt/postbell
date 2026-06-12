import { useState, useCallback, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Calendar, Clock, Loader2, Zap } from 'lucide-react'
import ChannelsSection from '../components/channels/ChannelsSection'
import DropZone from '../components/upload/DropZone'
import type { QueuedFile } from '../components/upload/DropZone'
import FileList from '../components/upload/FileList'
import ThumbnailPicker from '../components/upload/ThumbnailPicker'
import RoutingPreview from '../components/upload/RoutingPreview'
import ConfirmUploadDialog from '../components/upload/ConfirmUploadDialog'
import UploadProgress from '../components/upload/UploadProgress'
import { useUploadWebSocket } from '../hooks/useWebSocket'
import { useUploadProgress } from '../hooks/useUploadProgress'
import { getChannels } from '../api/channels'
import { prepareUpload, startUpload, uploadFileToServer, resolveSchedule } from '../api/uploads'
import type { RoutingEntry } from '../api/uploads'
import type { Channel, ResolvedSchedule } from '../types'

const LAST_JOB_KEY = 'postbell:lastJobId'

type FlowStep = 'select' | 'preview' | 'uploading'
type PublishMode = 'now' | 'private' | 'schedule' | 'auto_lang'

function getMinDatetimeLocal(): string {
  const d = new Date(Date.now() + 15 * 60 * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    d.getFullYear() +
    '-' +
    pad(d.getMonth() + 1) +
    '-' +
    pad(d.getDate()) +
    'T' +
    pad(d.getHours()) +
    ':' +
    pad(d.getMinutes())
  )
}

// Returns "today" in America/Sao_Paulo as a 'YYYY-MM-DD' string.
// Built via Intl so we never get UTC drift around midnight BRT.
function todayBrtDateString(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Sao_Paulo',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const y = parts.find((p) => p.type === 'year')!.value
  const m = parts.find((p) => p.type === 'month')!.value
  const d = parts.find((p) => p.type === 'day')!.value
  return `${y}-${m}-${d}`
}

// Format a 'YYYY-MM-DD' picked-date string for display, e.g. '10 jun'.
// Builds a local Date for display-only purposes (no TZ conversion).
function formatPickedDate(ymd: string): string {
  const [y, m, d] = ymd.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short' }).format(dt)
}

export default function DashboardPage() {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [files, setFiles] = useState<QueuedFile[]>([])
  const [thumbnails, setThumbnails] = useState<QueuedFile[]>([])
  const [thumbnailMap, setThumbnailMap] = useState<Record<string, number>>({})
  const [routing, setRouting] = useState<RoutingEntry[]>([])
  const [unroutable, setUnroutable] = useState<RoutingEntry[]>([])
  const [step, setStep] = useState<FlowStep>('select')
  const [analyzing, setAnalyzing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [showConfirm, setShowConfirm] = useState(false)
  const [titleOverrides, setTitleOverrides] = useState<Record<string, string>>({})
  const titleFor = (entry: RoutingEntry) =>
    titleOverrides[entry.file_name] || entry.file_name.replace(/\.[^.]+$/, '')
  const renderLangBadge = (code: string | null | undefined) => (
    <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-300 font-mono whitespace-nowrap shrink-0">
      {code?.toUpperCase() || '??'}
    </span>
  )
  const [serverPaths, setServerPaths] = useState<Record<string, string>>({})
  const [uploadingToServer, setUploadingToServer] = useState(false)
  const [serverUploadProgress, setServerUploadProgress] = useState<Record<string, number>>({})

  const [publishMode, setPublishMode] = useState<PublishMode>('now')
  const [scheduledAt, setScheduledAt] = useState<string>('')
  const [staggerEnabled, setStaggerEnabled] = useState(false)
  const [staggerMinutes, setStaggerMinutes] = useState<number>(30)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [autoLangResolved, setAutoLangResolved] = useState<ResolvedSchedule[]>([])
  const [autoLangLoading, setAutoLangLoading] = useState(false)
  const [autoLangError, setAutoLangError] = useState<string | null>(null)
  const [autoLangDate, setAutoLangDate] = useState<string>(todayBrtDateString())

  const { events } = useUploadWebSocket(activeJobId)
  const progress = useUploadProgress(events)

  // Keep localStorage in sync whenever the user starts a brand-new live
  // upload — that way, opening /uploads-recent (or refreshing it) auto-selects
  // the most recent job via the same key.
  useEffect(() => {
    if (activeJobId) {
      try {
        localStorage.setItem(LAST_JOB_KEY, activeJobId)
      } catch {
        // ignore
      }
    }
  }, [activeJobId])

  useEffect(() => {
    if (publishMode !== 'auto_lang') {
      return
    }
    const ids = routing
      .map((e) => e.channel_id)
      .filter((id): id is number => typeof id === 'number')
    if (ids.length === 0) {
      setAutoLangResolved([])
      return
    }
    let cancelled = false
    setAutoLangLoading(true)
    setAutoLangError(null)
    resolveSchedule(ids, autoLangDate)
      .then((data) => {
        if (!cancelled) setAutoLangResolved(data)
      })
      .catch((err) => {
        if (!cancelled) setAutoLangError(err instanceof Error ? err.message : 'Failed to resolve schedule')
      })
      .finally(() => {
        if (!cancelled) setAutoLangLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [publishMode, routing, autoLangDate])

  const { data: channels = [] } = useQuery({
    queryKey: ['channels'],
    queryFn: getChannels,
  })

  const handleToggle = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleToggleMany = (ids: number[], select: boolean) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (select) {
        ids.forEach(id => next.add(id))
      } else {
        ids.forEach(id => next.delete(id))
      }
      return next
    })
  }

  const handleFilesAdded = useCallback((newFiles: QueuedFile[]) => {
    const images = newFiles.filter(f => f.type === 'image')
    const videos = newFiles.filter(f => f.type === 'video')

    if (images.length > 0) {
      setThumbnails(prev => [...prev, ...images])
    }

    setFiles(prev => [...prev, ...videos])
    setRouting([])
    setUnroutable([])
    setStep('select')
  }, [])

  const handleRemoveFile = useCallback((index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
    setRouting([])
    setUnroutable([])
    setStep('select')
  }, [])

  const handleTitleChange = useCallback((index: number, title: string) => {
    setFiles(prev => prev.map((f, i) => i === index ? { ...f, title } : f))
  }, [])

  const handleRemoveThumbnail = useCallback((index: number) => {
    setThumbnails(prev => prev.filter((_, i) => i !== index))
    setThumbnailMap(prev => {
      const next: Record<string, number> = {}
      for (const [fileName, thumbIdx] of Object.entries(prev)) {
        if (thumbIdx === index) {
          // This video was using the removed thumbnail — fall back to default (0)
          // Don't add to map; missing key means default
        } else if (thumbIdx > index) {
          next[fileName] = thumbIdx - 1
        } else {
          next[fileName] = thumbIdx
        }
      }
      return next
    })
  }, [])

  const handleThumbnailAssign = useCallback((fileName: string, thumbIndex: number) => {
    setThumbnailMap(prev => ({ ...prev, [fileName]: thumbIndex }))
  }, [])

  const handleAutoMatchThumbnails = useCallback(() => {
    const newMap: Record<string, number> = { ...thumbnailMap }

    // Build a map of language code → thumbnail index
    const langToThumbIdx: Record<string, number> = {}
    thumbnails.forEach((thumb, idx) => {
      const stem = thumb.file.name.replace(/\.[^.]+$/, '')
      const match = stem.match(/[_\-]([a-z]{2})$/i)
      if (match) {
        langToThumbIdx[match[1].toLowerCase()] = idx
      } else if (/^[a-z]{2}$/i.test(stem)) {
        langToThumbIdx[stem.toLowerCase()] = idx
      }
    })

    // Match routing entries to thumbnails by language
    routing.forEach(entry => {
      if (entry.detected_language && langToThumbIdx[entry.detected_language] !== undefined) {
        newMap[entry.file_name] = langToThumbIdx[entry.detected_language]
      }
    })

    setThumbnailMap(newMap)
  }, [thumbnails, routing, thumbnailMap])

  const handleRoutingTitleChange = useCallback((fileName: string, newTitle: string) => {
    setTitleOverrides(prev => ({ ...prev, [fileName]: newTitle }))
  }, [])

  const handleAnalyze = async () => {
    if (files.length === 0 || selectedIds.size === 0) return

    setAnalyzing(true)
    setError(null)

    try {
      // Step 1: Upload video files to server (if not already uploaded)
      const newServerPaths = { ...serverPaths }
      const filesToUpload = files.filter(f => f.type === 'video' && !serverPaths[f.file.name])

      if (filesToUpload.length > 0) {
        setUploadingToServer(true)
        for (const qf of filesToUpload) {
          try {
            const result = await uploadFileToServer(qf.file, (percent) => {
              setServerUploadProgress(prev => ({ ...prev, [qf.file.name]: percent }))
            })
            newServerPaths[qf.file.name] = result.path
          } catch (err) {
            setError(`Failed to upload ${qf.file.name} to server`)
            setAnalyzing(false)
            setUploadingToServer(false)
            return
          }
        }
        setServerPaths(newServerPaths)
        setUploadingToServer(false)
      }

      // Step 2: Also upload thumbnail files to server
      for (const thumb of thumbnails) {
        if (!newServerPaths[thumb.file.name]) {
          try {
            const result = await uploadFileToServer(thumb.file)
            newServerPaths[thumb.file.name] = result.path
          } catch {
            // Thumbnail upload failure is non-fatal
          }
        }
      }
      setServerPaths(newServerPaths)

      // Step 3: Prepare routing with server paths
      const fileInfos = files.filter(f => f.type === 'video').map(f => ({
        name: f.file.name,
        size: f.file.size,
        path: newServerPaths[f.file.name] || f.file.name,
      }))

      const result = await prepareUpload(fileInfos, Array.from(selectedIds))
      setRouting(result.routing)
      setUnroutable(result.unroutable)
      setStep('preview')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setAnalyzing(false)
      setUploadingToServer(false)
    }
  }

  const handleStartUpload = async () => {
    if (routing.length === 0) return

    setUploading(true)
    setError(null)

    let privacy: string
    let scheduled_at: string | null = null

    if (publishMode === 'now') {
      privacy = 'public'
    } else if (publishMode === 'private') {
      privacy = 'private'
    } else if (publishMode === 'auto_lang') {
      privacy = 'private'
    } else {
      privacy = 'private'
      scheduled_at = scheduledAt ? new Date(scheduledAt).toISOString() : null
    }

    const stagger_minutes =
      publishMode === 'schedule' && staggerEnabled && routing.length > 1
        ? staggerMinutes
        : null

    const resolvedByChannel = new Map<number, ResolvedSchedule>()
    if (publishMode === 'auto_lang') {
      for (const r of autoLangResolved) {
        resolvedByChannel.set(r.channel_id, r)
      }
    }

    const routingWithThumbs = routing.map(entry => {
      const perEntryScheduled =
        publishMode === 'auto_lang' && entry.channel_id != null
          ? resolvedByChannel.get(entry.channel_id)?.scheduled_at_utc ?? null
          : null
      return {
        ...entry,
        title: titleOverrides[entry.file_name] || entry.file_name.replace(/\.[^.]+$/, ''),
        thumbnail_path: thumbnails.length > 0
          ? serverPaths[thumbnails[thumbnailMap[entry.file_name] ?? 0]?.file.name] ?? null
          : null,
        scheduled_at: perEntryScheduled,
      }
    })

    const jobId = crypto.randomUUID()
    setActiveJobId(jobId)
    setStep('uploading')

    await new Promise(resolve => setTimeout(resolve, 500))

    try {
      await startUpload({
        job_id: jobId,
        routing: routingWithThumbs,
        thumbnail_path: null,
        privacy,
        description: '',
        tags: '',
        scheduled_at,
        stagger_minutes,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed to start')
      setStep('preview')
      setActiveJobId(null)
    } finally {
      setUploading(false)
    }
  }

  const handleOverride = useCallback((fileIndex: number, channelId: number) => {
    const entry = unroutable[fileIndex]
    if (!entry) return

    const channel = channels.find((ch: Channel) => ch.id === channelId)
    if (!channel) return

    const routedEntry: RoutingEntry = {
      ...entry,
      channel_id: channelId,
      channel_name: channel.channel_name,
    }

    setUnroutable(prev => prev.filter((_, i) => i !== fileIndex))
    setRouting(prev => [...prev, routedEntry])
  }, [unroutable, channels])

  const videoCount = files.filter(f => f.type === 'video').length
  const canAnalyze = videoCount > 0 && selectedIds.size > 0 && !analyzing

  const selectedChannels = channels.filter((ch: Channel) => selectedIds.has(ch.id))

  const minDatetime = getMinDatetimeLocal()

  const autoLangBlocked =
    publishMode === 'auto_lang' &&
    autoLangResolved.length > 0 &&
    autoLangResolved.some((r) => r.already_passed || r.source === 'none')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-sm text-gray-400 mt-1">Select channels and upload videos</p>
      </div>

      <section>
        <h2 className="text-lg font-semibold text-white mb-4">Channels</h2>
        <ChannelsSection
          selectedIds={selectedIds}
          onToggle={handleToggle}
          onToggleMany={handleToggleMany}
        />
      </section>

      <section className="border-t border-gray-800 pt-6">
        <h2 className="text-lg font-semibold text-white mb-4">Upload</h2>

        {selectedIds.size === 0 ? (
          <p className="text-sm text-gray-500">Select at least one channel above to begin.</p>
        ) : (
          <div className="space-y-4">
            <DropZone onFilesAdded={handleFilesAdded} disabled={step === 'uploading'} />

            <FileList
              files={files}
              onRemove={handleRemoveFile}
              onTitleChange={handleTitleChange}
            />

            <ThumbnailPicker
              thumbnails={thumbnails}
              onRemove={handleRemoveThumbnail}
            />

            {error && (
              <div className="bg-red-900/30 border border-red-800 rounded-lg px-4 py-3">
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            {step === 'select' && videoCount > 0 && uploadingToServer && (
              <div className="bg-gray-800 rounded-lg p-4 space-y-2">
                <h3 className="text-sm font-medium text-white">Uploading files to server...</h3>
                {files.filter(f => f.type === 'video').map(f => (
                  <div key={f.file.name} className="flex items-center gap-3">
                    <span className="text-xs text-gray-400 truncate flex-1">{f.file.name}</span>
                    <div className="w-32 bg-gray-700 rounded-full h-1.5">
                      <div
                        className="bg-indigo-500 h-1.5 rounded-full transition-all duration-300"
                        style={{ width: `${serverUploadProgress[f.file.name] || 0}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 w-10 text-right">
                      {serverUploadProgress[f.file.name] || 0}%
                    </span>
                  </div>
                ))}
              </div>
            )}

            {step === 'select' && videoCount > 0 && (
              <button
                onClick={handleAnalyze}
                disabled={!canAnalyze}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {analyzing ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {uploadingToServer ? 'Uploading files to server...' : 'Analyzing...'}
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4" />
                    Analyze & Route ({videoCount} video{videoCount !== 1 ? 's' : ''} to {selectedIds.size} channel{selectedIds.size !== 1 ? 's' : ''})
                  </>
                )}
              </button>
            )}

            {step === 'preview' && (
              <>
                <RoutingPreview
                  routing={routing.map(entry => ({
                    ...entry,
                    title: titleOverrides[entry.file_name] ?? undefined,
                  }))}
                  unroutable={unroutable.map(entry => ({
                    ...entry,
                    title: titleOverrides[entry.file_name] ?? undefined,
                  }))}
                  onOverride={handleOverride}
                  availableChannels={selectedChannels.map((ch: Channel) => ({
                    id: ch.id,
                    channel_name: ch.channel_name,
                    language_code: ch.language_code,
                  }))}
                  thumbnails={thumbnails}
                  thumbnailMap={thumbnailMap}
                  onThumbnailAssign={handleThumbnailAssign}
                  onAutoMatch={handleAutoMatchThumbnails}
                  onTitleChange={handleRoutingTitleChange}
                />

                {/* Scheduling section */}
                <div className="bg-gray-800 rounded-lg p-4 space-y-4">
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-indigo-400" />
                    Publish Settings
                  </h3>

                  <div className="flex flex-col gap-2">
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input
                        type="radio"
                        name="publishMode"
                        value="now"
                        checked={publishMode === 'now'}
                        onChange={() => setPublishMode('now')}
                        className="accent-indigo-500"
                      />
                      <span className="text-sm text-white">Publish Now</span>
                      <span className="text-xs text-gray-500">— public immediately</span>
                    </label>

                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input
                        type="radio"
                        name="publishMode"
                        value="private"
                        checked={publishMode === 'private'}
                        onChange={() => setPublishMode('private')}
                        className="accent-indigo-500"
                      />
                      <span className="text-sm text-white">Upload as Private</span>
                      <span className="text-xs text-gray-500">— stays private, publish manually later</span>
                    </label>

                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input
                        type="radio"
                        name="publishMode"
                        value="schedule"
                        checked={publishMode === 'schedule'}
                        onChange={() => setPublishMode('schedule')}
                        className="accent-indigo-500"
                      />
                      <span className="text-sm text-white">Schedule</span>
                      <span className="text-xs text-gray-500">— set a publish date/time</span>
                    </label>

                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input
                        type="radio"
                        name="publishMode"
                        value="auto_lang"
                        checked={publishMode === 'auto_lang'}
                        onChange={() => setPublishMode('auto_lang')}
                        className="accent-indigo-500"
                      />
                      <span className="text-sm text-white">Auto-agendar por idioma</span>
                      <span className="text-xs text-gray-500">— cada vídeo no horário do canal/idioma hoje</span>
                    </label>
                  </div>

                  {publishMode === 'auto_lang' && (
                    <div className="space-y-2 border-t border-gray-700 pt-3">
                      <div className="flex items-center gap-2 mb-2">
                        <label className="text-xs text-gray-400">Data de publicação</label>
                        <input
                          type="date"
                          min={todayBrtDateString()}
                          value={autoLangDate}
                          onChange={(e) => setAutoLangDate(e.target.value)}
                          className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                      {autoLangLoading && (
                        <p className="text-xs text-gray-400 flex items-center gap-2">
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          Calculando horários...
                        </p>
                      )}
                      {autoLangError && (
                        <p className="text-xs text-red-400">{autoLangError}</p>
                      )}
                      {!autoLangLoading && !autoLangError && autoLangResolved.length > 0 && (
                        <ul className="space-y-1.5">
                          {routing.map((entry) => {
                            const resolved =
                              entry.channel_id != null
                                ? autoLangResolved.find((r) => r.channel_id === entry.channel_id)
                                : undefined
                            if (!resolved) return null
                            const baseRow =
                              'flex items-center justify-between gap-2 text-xs rounded px-2 py-1.5 border'
                            if (resolved.source === 'none' || resolved.error) {
                              return (
                                <li
                                  key={entry.file_name}
                                  className={`${baseRow} bg-red-900/30 border-red-800 text-red-300`}
                                >
                                  <span className="flex items-center gap-2 truncate">
                                    {renderLangBadge(entry.detected_language)}
                                    <span className="truncate">{titleFor(entry)} → {resolved.channel_name}</span>
                                  </span>
                                  <span className="font-medium">
                                    {resolved.error || 'sem horário configurado'}
                                  </span>
                                </li>
                              )
                            }
                            const isToday = autoLangDate === todayBrtDateString()
                            const dateLabel = isToday
                              ? 'hoje'
                              : formatPickedDate(autoLangDate)
                            if (resolved.already_passed) {
                              return (
                                <li
                                  key={entry.file_name}
                                  className={`${baseRow} bg-amber-900/30 border-amber-800 text-amber-200`}
                                >
                                  <span className="flex items-center gap-2 truncate">
                                    {renderLangBadge(entry.detected_language)}
                                    <span className="truncate">{titleFor(entry)} → {resolved.channel_name} · {dateLabel} {resolved.resolved_time} BRT</span>
                                  </span>
                                  <span className="font-medium whitespace-nowrap">⚠️ horário passado</span>
                                </li>
                              )
                            }
                            return (
                              <li
                                key={entry.file_name}
                                className={`${baseRow} bg-gray-900/40 border-gray-700 text-gray-200`}
                              >
                                <span className="flex items-center gap-2 truncate">
                                  {renderLangBadge(entry.detected_language)}
                                  <span className="truncate">{titleFor(entry)} → {resolved.channel_name} · {dateLabel} {resolved.resolved_time} BRT</span>
                                </span>
                                <span className="text-gray-500 text-[10px] uppercase">{resolved.source}</span>
                              </li>
                            )
                          })}
                        </ul>
                      )}
                      {autoLangBlocked && (
                        <p className="text-xs text-amber-300">
                          Configure horários em Settings ou escolha outra opção.
                        </p>
                      )}
                    </div>
                  )}

                  {publishMode === 'schedule' && (
                    <div className="space-y-3 border-t border-gray-700 pt-3">
                      <div className="space-y-1">
                        <label className="flex items-center gap-2 text-xs font-medium text-gray-300">
                          <Clock className="w-3.5 h-3.5 text-indigo-400" />
                          Publish date &amp; time
                        </label>
                        <input
                          type="datetime-local"
                          value={scheduledAt}
                          min={minDatetime}
                          onChange={e => setScheduledAt(e.target.value)}
                          className="w-full bg-gray-700 border border-gray-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent [color-scheme:dark]"
                        />
                        <p className="text-xs text-gray-500">
                          Times are in your local timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone}).
                          Minimum: 15 minutes from now.
                        </p>
                      </div>

                      {routing.length > 1 && (
                        <div className="space-y-2">
                          <label className="flex items-center gap-3 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={staggerEnabled}
                              onChange={e => setStaggerEnabled(e.target.checked)}
                              className="accent-indigo-500 w-4 h-4"
                            />
                            <span className="text-sm text-white">Stagger uploads</span>
                          </label>

                          {staggerEnabled && (
                            <div className="flex items-center gap-2 pl-7">
                              <span className="text-xs text-gray-400">Each subsequent video gets</span>
                              <input
                                type="number"
                                min={1}
                                max={1440}
                                value={staggerMinutes}
                                onChange={e => setStaggerMinutes(Math.max(1, Number(e.target.value)))}
                                className="w-16 bg-gray-700 border border-gray-600 text-white text-sm rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                              />
                              <span className="text-xs text-gray-400">minutes added to the base time.</span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <button
                  onClick={() => setShowConfirm(true)}
                  disabled={
                    uploading ||
                    routing.length === 0 ||
                    (publishMode === 'schedule' && !scheduledAt) ||
                    (publishMode === 'auto_lang' && (autoLangLoading || autoLangBlocked || autoLangResolved.length === 0))
                  }
                  className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {uploading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Starting upload...
                    </>
                  ) : publishMode === 'schedule' ? (
                    <>
                      <Calendar className="w-4 h-4" />
                      Schedule Upload{routing.length !== 1 ? 's' : ''}
                    </>
                  ) : publishMode === 'auto_lang' ? (
                    <>
                      <Calendar className="w-4 h-4" />
                      Auto-agendar ({routing.length})
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4" />
                      Start Upload{routing.length !== 1 ? 's' : ''} ({routing.length})
                    </>
                  )}
                </button>

                <ConfirmUploadDialog
                  open={showConfirm}
                  onConfirm={() => {
                    setShowConfirm(false)
                    handleStartUpload()
                  }}
                  onCancel={() => setShowConfirm(false)}
                  routing={routing.map(entry => ({
                    ...entry,
                    title: titleOverrides[entry.file_name] || entry.file_name.replace(/\.[^.]+$/, ''),
                  }))}
                  thumbnails={thumbnails}
                  thumbnailMap={thumbnailMap}
                  privacy={publishMode === 'now' ? 'public' : 'private'}
                  publishMode={publishMode}
                  scheduledAt={publishMode === 'schedule' ? scheduledAt : undefined}
                />
              </>
            )}

            {step === 'uploading' && activeJobId && (
              <UploadProgress
                progress={progress}
                onDone={() => {
                  setStep('select')
                  setFiles([])
                  setThumbnails([])
                  setThumbnailMap({})
                  setRouting([])
                  setUnroutable([])
                  setActiveJobId(null)
                }}
              />
            )}
          </div>
        )}
      </section>
    </div>
  )
}
