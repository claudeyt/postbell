import { RotateCw, X } from 'lucide-react'
import { parseBackendDate } from '../../lib/date'

interface JobHeaderProps {
  summary: {
    total: number
    completed: number
    failed: number
    in_flight: number
    started_at: string | null
    status: 'running' | 'partial' | 'failed' | 'completed'
  }
  onRefresh: () => void
  onDismiss: () => void
}

function formatStartedAt(iso: string | null): string {
  const d = parseBackendDate(iso)
  if (!d) return ''
  const time = d.toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
  })
  const date = d.toLocaleDateString('pt-BR', {
    day: 'numeric',
    month: 'numeric',
  })
  return `iniciado às ${time} de ${date}`
}

function statusLabel(status: JobHeaderProps['summary']['status']): {
  text: string
  className: string
} {
  switch (status) {
    case 'running':
      return { text: 'Em andamento', className: 'text-indigo-300' }
    case 'completed':
      return { text: 'Concluído', className: 'text-green-300' }
    case 'partial':
      return { text: 'Parcial', className: 'text-amber-300' }
    case 'failed':
      return { text: 'Falhou', className: 'text-red-300' }
  }
}

export default function JobHeader({
  summary,
  onRefresh,
  onDismiss,
}: JobHeaderProps) {
  const label = statusLabel(summary.status)
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 flex items-center gap-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm">
          <span className={`font-medium ${label.className}`}>{label.text}</span>
          <span className="text-gray-500">·</span>
          <span className="text-gray-300 truncate">
            {formatStartedAt(summary.started_at)}
          </span>
        </div>
        <div className="text-xs text-gray-400 mt-0.5">
          {summary.total} vídeo{summary.total !== 1 ? 's' : ''}
          {summary.completed > 0 && (
            <span className="text-green-400"> · ✓ {summary.completed}</span>
          )}
          {summary.failed > 0 && (
            <span className="text-red-400"> · ✗ {summary.failed}</span>
          )}
          {summary.in_flight > 0 && (
            <span className="text-indigo-300"> · {summary.in_flight} em andamento</span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={onRefresh}
        title="Atualizar"
        className="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
      >
        <RotateCw className="w-4 h-4" />
      </button>
      <button
        type="button"
        onClick={onDismiss}
        title="Fechar"
        className="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
