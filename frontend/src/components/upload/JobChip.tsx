import { Clock, Check, AlertTriangle, X } from 'lucide-react'
import type { JobSummary } from '../../types'
import { parseBackendDate } from '../../lib/date'

interface JobChipProps {
  summary: JobSummary
  selected: boolean
  onClick: () => void
}

function relativeLabel(iso: string): string {
  const d = parseBackendDate(iso)
  if (!d) return ''
  const then = d.getTime()
  const now = Date.now()
  const diffSec = Math.max(0, Math.floor((now - then) / 1000))
  if (diffSec < 60) return 'agora'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `há ${diffMin} min`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `há ${diffH}h`
  // Else: date short form pt-BR
  return d.toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
  })
}

function statusIcon(status: JobSummary['status']) {
  switch (status) {
    case 'running':
      return <Clock className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
    case 'completed':
      return <Check className="w-3.5 h-3.5 text-green-400 shrink-0" />
    case 'partial':
      return <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
    case 'failed':
      return <X className="w-3.5 h-3.5 text-red-400 shrink-0" />
  }
}

export default function JobChip({ summary, selected, onClick }: JobChipProps) {
  const bottomLine =
    summary.status === 'running'
      ? `${summary.in_flight} em andamento`
      : `${summary.total} vídeo${summary.total !== 1 ? 's' : ''}` +
        (summary.completed ? ` · ✓ ${summary.completed}` : '') +
        (summary.failed ? ` · ✗ ${summary.failed}` : '')

  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'flex flex-col items-start gap-1 text-left',
        'min-w-[180px] px-3 py-2 rounded-lg border transition-colors',
        'bg-gray-800 hover:bg-gray-700',
        selected
          ? 'border-indigo-500 shadow-[0_0_0_1px_rgba(99,102,241,0.35)]'
          : 'border-gray-700',
      ].join(' ')}
    >
      <div className="flex items-center gap-1.5 text-xs text-gray-300">
        {statusIcon(summary.status)}
        <span>{relativeLabel(summary.started_at)}</span>
      </div>
      <div className="text-xs text-gray-400 truncate w-full">{bottomLine}</div>
    </button>
  )
}
