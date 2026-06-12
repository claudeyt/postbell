import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload } from 'lucide-react'

const VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv']
const IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png']
const ALL_ACCEPT = {
  'video/*': VIDEO_EXTENSIONS,
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
}

export interface QueuedFile {
  file: File
  type: 'video' | 'image'
  title: string // derived from filename without extension
}

interface DropZoneProps {
  onFilesAdded: (files: QueuedFile[]) => void
  disabled?: boolean
}

export default function DropZone({ onFilesAdded, disabled }: DropZoneProps) {
  const onDrop = useCallback((acceptedFiles: File[]) => {
    const queued: QueuedFile[] = acceptedFiles.map(file => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase()
      const isImage = IMAGE_EXTENSIONS.includes(ext)
      const title = file.name.replace(/\.[^.]+$/, '')
      return { file, type: isImage ? 'image' : 'video', title }
    })
    onFilesAdded(queued)
  }, [onFilesAdded])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ALL_ACCEPT,
    disabled,
    multiple: true,
  })

  return (
    <div
      {...getRootProps()}
      className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer
        ${isDragActive ? 'border-indigo-500 bg-indigo-500/10' : 'border-gray-700 hover:border-gray-600'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <input {...getInputProps()} />
      <Upload className="w-10 h-10 text-gray-500 mx-auto mb-3" />
      {isDragActive ? (
        <p className="text-indigo-400 font-medium">Drop files here...</p>
      ) : (
        <>
          <p className="text-gray-300 font-medium">Drag & drop videos and thumbnail here</p>
          <p className="text-sm text-gray-500 mt-1">or click to browse files</p>
          <p className="text-xs text-gray-600 mt-2">
            Videos: MP4, MKV, AVI, MOV, WebM · Thumbnail: JPG, PNG
          </p>
        </>
      )}
    </div>
  )
}
