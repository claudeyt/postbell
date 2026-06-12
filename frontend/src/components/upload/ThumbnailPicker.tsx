import { Image, X } from 'lucide-react'
import type { QueuedFile } from './DropZone'
import { useMemo } from 'react'

interface ThumbnailPickerProps {
  thumbnails: QueuedFile[]
  onRemove: (index: number) => void
}

export default function ThumbnailPicker({ thumbnails, onRemove }: ThumbnailPickerProps) {
  const previewUrls = useMemo(() => {
    return thumbnails.map(t => URL.createObjectURL(t.file))
  }, [thumbnails])

  if (thumbnails.length === 0) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
        <div className="flex items-center gap-2 text-gray-400">
          <Image className="w-5 h-5" />
          <span className="text-sm">No thumbnail — drop an image with your videos to use as thumbnail</span>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="flex gap-3 flex-wrap">
        {thumbnails.map((thumb, idx) => (
          <div key={idx} className="flex items-center gap-3 bg-gray-750 rounded-lg p-2 border border-gray-700">
            <div className="relative">
              {previewUrls[idx] && (
                <img
                  src={previewUrls[idx]}
                  alt="Thumbnail preview"
                  className="w-32 h-18 object-cover rounded"
                  style={{ aspectRatio: '16/9' }}
                />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-sm text-white font-medium truncate">{thumb.file.name}</p>
                {idx === 0 && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-600 text-white shrink-0">Default</span>
                )}
              </div>
              <p className="text-xs text-gray-500">{(thumb.file.size / 1024).toFixed(0)} KB</p>
            </div>
            <button onClick={() => onRemove(idx)} className="text-gray-500 hover:text-red-400 shrink-0">
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
