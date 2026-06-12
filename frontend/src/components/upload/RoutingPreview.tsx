import { ArrowRight, AlertTriangle, Wand2 } from 'lucide-react'
import { useMemo } from 'react'
import { LANGUAGES } from '../channels/LanguageSelector'
import type { QueuedFile } from './DropZone'

interface RoutingEntry {
  file_name: string
  file_path: string
  detected_language: string | null
  detection_method: string | null
  channel_id: number | null
  channel_name: string | null
  title?: string
}

interface RoutingPreviewProps {
  routing: RoutingEntry[]
  unroutable: RoutingEntry[]
  onOverride: (fileIndex: number, channelId: number) => void
  availableChannels: { id: number; channel_name: string; language_code: string }[]
  thumbnails: QueuedFile[]
  thumbnailMap: Record<string, number>
  onThumbnailAssign: (fileName: string, thumbIndex: number) => void
  onAutoMatch?: () => void
  onTitleChange?: (fileName: string, newTitle: string) => void
}

function ThumbnailSelector({
  fileName,
  thumbnails,
  thumbnailMap,
  onThumbnailAssign,
  previewUrls,
}: {
  fileName: string
  thumbnails: QueuedFile[]
  thumbnailMap: Record<string, number>
  onThumbnailAssign: (fileName: string, thumbIndex: number) => void
  previewUrls: string[]
}) {
  if (thumbnails.length === 0) return null

  if (thumbnails.length === 1) {
    return (
      <div className="shrink-0">
        {previewUrls[0] && (
          <img
            src={previewUrls[0]}
            alt="Thumbnail"
            className="w-10 h-6 object-cover rounded"
            style={{ aspectRatio: '16/9' }}
          />
        )}
      </div>
    )
  }

  const currentIndex = thumbnailMap[fileName] ?? 0

  return (
    <select
      value={currentIndex}
      onChange={(e) => onThumbnailAssign(fileName, parseInt(e.target.value))}
      className="bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 shrink-0 max-w-[140px]"
    >
      {thumbnails.map((thumb, idx) => (
        <option key={idx} value={idx}>
          {idx === 0 ? `★ ${thumb.file.name}` : thumb.file.name}
        </option>
      ))}
    </select>
  )
}

export default function RoutingPreview({
  routing,
  unroutable,
  onOverride,
  availableChannels,
  thumbnails,
  thumbnailMap,
  onThumbnailAssign,
  onAutoMatch,
  onTitleChange,
}: RoutingPreviewProps) {
  const getLangInfo = (code: string | null) => {
    if (!code) return { flag: '?', name: 'Unknown' }
    const lang = LANGUAGES.find(l => l.code === code)
    return lang || { flag: '', name: code.toUpperCase() }
  }

  const previewUrls = useMemo(() => {
    return thumbnails.map(t => URL.createObjectURL(t.file))
  }, [thumbnails])

  return (
    <div className="space-y-4">
      {routing.length > 0 && (
        <div className="bg-gray-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
            <h3 className="text-sm font-medium text-green-400">
              {routing.length} file{routing.length !== 1 ? 's' : ''} routed
            </h3>
            {thumbnails.length >= 2 && onAutoMatch && (
              <button
                onClick={onAutoMatch}
                className="flex items-center gap-1.5 px-2.5 py-1 bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium rounded-lg transition-colors"
              >
                <Wand2 className="w-3.5 h-3.5" />
                Auto-match thumbnails
              </button>
            )}
          </div>
          <div className="divide-y divide-gray-700">
            {routing.map((entry, idx) => {
              const langInfo = getLangInfo(entry.detected_language)
              const titleValue = entry.title ?? entry.file_name.replace(/\.[^.]+$/, '')
              return (
                <div key={idx} className="flex items-center gap-3 px-4 py-3">
                  <input
                    type="text"
                    value={titleValue}
                    onChange={e => onTitleChange?.(entry.file_name, e.target.value)}
                    maxLength={100}
                    className="bg-transparent border-b border-gray-600 focus:border-indigo-500 text-sm text-white px-1 py-0.5 outline-none truncate flex-1"
                  />
                  <span className={`text-xs shrink-0 ${titleValue.length >= 100 ? 'text-red-400' : titleValue.length >= 90 ? 'text-yellow-400' : 'text-gray-600'}`}>
                    {titleValue.length}/100
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">
                    {langInfo.flag} {entry.detected_language?.toUpperCase()}
                  </span>
                  <span className="text-xs text-gray-500">via {entry.detection_method}</span>
                  <ArrowRight className="w-4 h-4 text-gray-600 shrink-0" />
                  <span className="text-sm text-indigo-400 shrink-0">{entry.channel_name}</span>
                  <ThumbnailSelector
                    fileName={entry.file_name}
                    thumbnails={thumbnails}
                    thumbnailMap={thumbnailMap}
                    onThumbnailAssign={onThumbnailAssign}
                    previewUrls={previewUrls}
                  />
                </div>
              )
            })}
          </div>
        </div>
      )}

      {unroutable.length > 0 && (
        <div className="bg-gray-800 rounded-lg overflow-hidden border border-yellow-800">
          <div className="px-4 py-3 border-b border-gray-700">
            <h3 className="text-sm font-medium text-yellow-400 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              {unroutable.length} file{unroutable.length !== 1 ? 's' : ''} need manual assignment
            </h3>
          </div>
          <div className="divide-y divide-gray-700">
            {unroutable.map((entry, idx) => {
              const langInfo = getLangInfo(entry.detected_language)
              const titleValue = entry.title ?? entry.file_name.replace(/\.[^.]+$/, '')
              return (
                <div key={idx} className="flex items-center gap-3 px-4 py-3">
                  <input
                    type="text"
                    value={titleValue}
                    onChange={e => onTitleChange?.(entry.file_name, e.target.value)}
                    maxLength={100}
                    className="bg-transparent border-b border-gray-600 focus:border-indigo-500 text-sm text-white px-1 py-0.5 outline-none truncate flex-1"
                  />
                  <span className={`text-xs shrink-0 ${titleValue.length >= 100 ? 'text-red-400' : titleValue.length >= 90 ? 'text-yellow-400' : 'text-gray-600'}`}>
                    {titleValue.length}/100
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300">
                    {langInfo.flag} {entry.detected_language?.toUpperCase() || '??'}
                  </span>
                  <ArrowRight className="w-4 h-4 text-gray-600 shrink-0" />
                  <select
                    onChange={(e) => onOverride(idx, parseInt(e.target.value))}
                    className="bg-gray-900 border border-gray-600 rounded px-2 py-1 text-sm text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    defaultValue=""
                  >
                    <option value="" disabled>Assign channel...</option>
                    {availableChannels.map(ch => (
                      <option key={ch.id} value={ch.id}>
                        {ch.channel_name} ({ch.language_code})
                      </option>
                    ))}
                  </select>
                  <ThumbnailSelector
                    fileName={entry.file_name}
                    thumbnails={thumbnails}
                    thumbnailMap={thumbnailMap}
                    onThumbnailAssign={onThumbnailAssign}
                    previewUrls={previewUrls}
                  />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
