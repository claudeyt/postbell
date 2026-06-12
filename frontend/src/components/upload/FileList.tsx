import { X, FileVideo } from 'lucide-react'
import type { QueuedFile } from './DropZone'

interface FileListProps {
  files: QueuedFile[]
  onRemove: (index: number) => void
  onTitleChange: (index: number, title: string) => void
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export default function FileList({ files, onRemove, onTitleChange }: FileListProps) {
  const videos = files.filter(f => f.type === 'video')

  if (videos.length === 0) return null

  return (
    <div className="bg-gray-800 rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-700">
        <h3 className="text-sm font-medium text-gray-300">
          {videos.length} video{videos.length !== 1 ? 's' : ''} queued
        </h3>
      </div>
      <div className="divide-y divide-gray-700">
        {videos.map((qf, idx) => {
          const originalIdx = files.indexOf(qf)
          return (
            <div key={idx} className="flex items-center gap-3 px-4 py-3">
              <FileVideo className="w-5 h-5 text-gray-500 shrink-0" />
              <input
                type="text"
                value={qf.title}
                onChange={(e) => onTitleChange(originalIdx, e.target.value)}
                className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                maxLength={100}
              />
              <span className="text-xs text-gray-500 shrink-0">{formatSize(qf.file.size)}</span>
              <span className={`text-xs shrink-0 ${qf.title.length >= 100 ? 'text-red-400' : qf.title.length >= 90 ? 'text-yellow-400' : 'text-gray-600'}`}>
                {qf.title.length}/100
              </span>
              <button
                onClick={() => onRemove(originalIdx)}
                className="text-gray-500 hover:text-red-400 shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
