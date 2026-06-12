import { X, Upload } from 'lucide-react'
import type { RoutingEntry } from '../../api/uploads'
import type { QueuedFile } from './DropZone'
import { LANGUAGES } from '../channels/LanguageSelector'

interface ConfirmUploadDialogProps {
  open: boolean
  onConfirm: () => void
  onCancel: () => void
  routing: RoutingEntry[]
  thumbnails: QueuedFile[]
  thumbnailMap: Record<string, number>
  privacy: string
  publishMode: string
  scheduledAt?: string
}

export default function ConfirmUploadDialog({
  open,
  onConfirm,
  onCancel,
  routing,
  thumbnails,
  thumbnailMap,
  privacy,
  publishMode,
  scheduledAt,
}: ConfirmUploadDialogProps) {
  if (!open) return null

  const getLangInfo = (code: string | null) => {
    if (!code) return { flag: '?', name: 'Unknown' }
    const lang = LANGUAGES.find(l => l.code === code)
    return lang || { flag: '', name: code.toUpperCase() }
  }

  const uniqueChannels = new Set(routing.map(r => r.channel_name).filter(Boolean))

  const privacyLabel =
    publishMode === 'schedule'
      ? `Scheduled${scheduledAt ? ` — ${new Date(scheduledAt).toLocaleString()}` : ''}`
      : privacy === 'public'
        ? 'Public'
        : 'Private'

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={onCancel}
    >
      <div
        className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Upload className="w-5 h-5 text-green-400" />
            Confirmar Upload
          </h2>
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-5 py-4 space-y-4 flex-1">
          {/* Video list */}
          <div className="space-y-2">
            {routing.map((entry, idx) => {
              const langInfo = getLangInfo(entry.detected_language)
              const thumbName =
                thumbnails.length > 0
                  ? thumbnails[thumbnailMap[entry.file_name] ?? 0]?.file.name ?? null
                  : null

              return (
                <div
                  key={idx}
                  className="bg-gray-900 rounded-lg px-3 py-2 space-y-1"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-white truncate flex-1">
                      {entry.title || entry.file_name}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300 shrink-0">
                      {langInfo.flag} {entry.detected_language?.toUpperCase() || '??'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-gray-400">
                    <span>
                      &rarr; <span className="text-indigo-400">{entry.channel_name}</span>
                    </span>
                    {thumbName && (
                      <span className="text-gray-500">| Thumbnail: {thumbName}</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Summary */}
          <div className="bg-gray-900 rounded-lg px-3 py-2 space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">Privacy</span>
              <span className="text-white">{privacyLabel}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">Total</span>
              <span className="text-white">
                {routing.length} v&iacute;deo{routing.length !== 1 ? 's' : ''} para{' '}
                {uniqueChannels.size} cana{uniqueChannels.size !== 1 ? 'is' : 'l'}
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-gray-700">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-white bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 text-sm text-white bg-green-600 hover:bg-green-500 rounded-lg transition-colors flex items-center gap-2"
          >
            <Upload className="w-4 h-4" />
            Confirmar Upload
          </button>
        </div>
      </div>
    </div>
  )
}
