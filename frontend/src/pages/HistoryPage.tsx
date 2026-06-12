import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, ChevronLeft, ChevronRight, Pencil, X } from 'lucide-react'
import { getUploads, updateYoutubeVideo } from '../api/uploads'
import { getChannels } from '../api/channels'
import type { Upload } from '../types'

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'uploading', label: 'Uploading' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

const STATUS_BADGE: Record<string, string> = {
  completed: 'bg-green-900/40 text-green-400 border border-green-800',
  failed: 'bg-red-900/40 text-red-400 border border-red-800',
  uploading: 'bg-yellow-900/40 text-yellow-400 border border-yellow-800',
  pending: 'bg-gray-700 text-gray-400 border border-gray-600',
  processing: 'bg-blue-900/40 text-blue-400 border border-blue-800',
}

const PER_PAGE = 20

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_BADGE[status] ?? 'bg-gray-700 text-gray-400 border border-gray-600'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${cls}`}>
      {status}
    </span>
  )
}

function EditVideoModal({ upload, onClose }: { upload: Upload; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(upload.title)
  const [description, setDescription] = useState(upload.description ?? '')
  const [tags, setTags] = useState(upload.tags ?? '')
  const [privacy, setPrivacy] = useState(upload.privacy)

  const mutation = useMutation({
    mutationFn: () => updateYoutubeVideo(upload.id, { title, description, tags, privacy }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['uploads'] })
      onClose()
    },
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-800 border border-gray-700 rounded-lg w-full max-w-lg shadow-xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-white">Edit Video</h2>
          <button
            onClick={onClose}
            className="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Title</label>
            <input
              type="text"
              value={title}
              maxLength={100}
              onChange={e => setTitle(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Description</label>
            <textarea
              value={description}
              rows={4}
              onChange={e => setDescription(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Tags (comma-separated)</label>
            <input
              type="text"
              value={tags}
              onChange={e => setTags(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Privacy</label>
            <select
              value={privacy}
              onChange={e => setPrivacy(e.target.value as Upload['privacy'])}
              className="w-full bg-gray-900 border border-gray-700 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="public">Public</option>
              <option value="private">Private</option>
              <option value="unlisted">Unlisted</option>
            </select>
          </div>

          {mutation.isError && (
            <p className="text-sm text-red-400">
              {mutation.error instanceof Error ? mutation.error.message : 'Failed to update video.'}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700">
          <button
            onClick={onClose}
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-lg text-sm font-medium text-gray-300 hover:text-white hover:bg-gray-700 disabled:opacity-40 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {mutation.isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function HistoryPage() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [channelFilter, setChannelFilter] = useState<number | undefined>(undefined)
  const [editingUpload, setEditingUpload] = useState<Upload | null>(null)

  const { data: channelsData = [] } = useQuery({
    queryKey: ['channels'],
    queryFn: getChannels,
  })

  const { data, isLoading, isError } = useQuery({
    queryKey: ['uploads', page, statusFilter, channelFilter],
    queryFn: () =>
      getUploads({
        page,
        per_page: PER_PAGE,
        status: statusFilter || undefined,
        channel_id: channelFilter,
      }),
    placeholderData: (prev) => prev,
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PER_PAGE)) : 1

  const handleStatusChange = (value: string) => {
    setStatusFilter(value)
    setPage(1)
  }

  const handleChannelChange = (value: string) => {
    setChannelFilter(value ? Number(value) : undefined)
    setPage(1)
  }

  function formatDate(dateStr: string) {
    const hasTz = /[+-]\d{2}:?\d{2}$|Z$/.test(dateStr)
    const d = new Date(hasTz ? dateStr : dateStr + 'Z')
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">History</h1>
        <p className="text-sm text-gray-400 mt-1">Upload history and logs</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={statusFilter}
          onChange={e => handleStatusChange(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {STATUS_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        <select
          value={channelFilter ?? ''}
          onChange={e => handleChannelChange(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-sm text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All Channels</option>
          {channelsData.map(ch => (
            <option key={ch.id} value={ch.id}>
              {ch.alias ?? ch.channel_name}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-gray-400">Loading...</div>
        ) : isError ? (
          <div className="p-8 text-center text-red-400">Failed to load upload history.</div>
        ) : !data || data.items.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No uploads found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-left">
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">File</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Channel</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">YouTube</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Date</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {data.items.map((upload: Upload) => {
                const channel = channelsData.find(ch => ch.id === upload.channel_id)
                return (
                  <tr key={upload.id} className="hover:bg-gray-700/50 transition-colors">
                    <td className="px-4 py-3 text-white max-w-xs">
                      <span className="truncate block" title={upload.file_name}>
                        {upload.file_name}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-300">
                      {channel ? (channel.alias ?? channel.channel_name) : `Channel ${upload.channel_id}`}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={upload.status} />
                    </td>
                    <td className="px-4 py-3">
                      {upload.youtube_url ? (
                        <a
                          href={upload.youtube_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 transition-colors"
                        >
                          Watch
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      ) : (
                        <span className="text-gray-600">&mdash;</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-400 whitespace-nowrap">
                      {formatDate(upload.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      {upload.status === 'completed' && upload.youtube_video_id ? (
                        <button
                          onClick={() => setEditingUpload(upload)}
                          className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 transition-colors"
                          aria-label="Edit video"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                          Edit
                        </button>
                      ) : (
                        <span className="text-gray-600">&mdash;</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {data && data.total > PER_PAGE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-400">
            Showing {((page - 1) * PER_PAGE) + 1}&ndash;{Math.min(page * PER_PAGE, data.total)} of {data.total}
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              aria-label="Previous page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              let pageNum: number
              if (totalPages <= 7) {
                pageNum = i + 1
              } else if (page <= 4) {
                pageNum = i + 1
              } else if (page >= totalPages - 3) {
                pageNum = totalPages - 6 + i
              } else {
                pageNum = page - 3 + i
              }
              return (
                <button
                  key={pageNum}
                  onClick={() => setPage(pageNum)}
                  className={`min-w-[32px] px-2 py-1 rounded-lg text-sm font-medium transition-colors ${
                    pageNum === page
                      ? 'bg-indigo-600 text-white'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700'
                  }`}
                >
                  {pageNum}
                </button>
              )
            })}

            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              aria-label="Next page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {editingUpload && (
        <EditVideoModal upload={editingUpload} onClose={() => setEditingUpload(null)} />
      )}
    </div>
  )
}
