import { CheckCircle, Loader2, Circle, XCircle, X } from 'lucide-react'
import type { StageKey } from '../../hooks/useUploadProgress'
import { ErrorTooltip } from '../common/ErrorTooltip'

interface StageTimelineProps {
  current: StageKey
  hasThumbnail: boolean
  hasComment: boolean
  stageErrors?: {
    verifying?: string
    thumbnail?: string
    comment?: string
  }
}

type StageDef = { key: Exclude<StageKey, 'failed'>; label: string }

const ALL_STAGES: StageDef[] = [
  { key: 'preparing', label: 'Preparando' },
  { key: 'uploading', label: 'Enviando' },
  { key: 'verifying', label: 'Verificando' },
  { key: 'thumbnail', label: 'Thumb' },
  { key: 'comment', label: 'Comentário' },
  { key: 'done', label: 'Concluído' },
]

export default function StageTimeline({ current, hasThumbnail, hasComment, stageErrors }: StageTimelineProps) {
  const stages = ALL_STAGES.filter(s => {
    if (s.key === 'thumbnail' && !hasThumbnail) return false
    if (s.key === 'comment' && !hasComment) return false
    return true
  })

  const failed = current === 'failed'
  const allDone = current === 'done'
  // For the 'failed' case we mark the LAST non-failed stage seen as the failure point.
  // We don't know exactly which stage failed without more context, so we pick the
  // furthest visible stage that wasn't 'done'. Simple heuristic: highlight 'uploading'
  // as failed if no other progress was tracked. For now we render every stage dim
  // and put the X on the first non-done stage.
  const currentIndex = failed
    ? Math.max(stages.findIndex(s => s.key === 'uploading'), 0)
    : stages.findIndex(s => s.key === current)

  return (
    <div className="flex items-center gap-1.5 flex-wrap" data-testid="stage-timeline">
      {stages.map((stage, idx) => {
        // When everything is done, every pill (including the 'Concluído' pill
        // itself) renders as completed/green — no indigo "current" highlight.
        const isCompleted = !failed && (allDone || currentIndex > idx)
        const isCurrent = !failed && !allDone && currentIndex === idx
        const isFailedHere = failed && currentIndex === idx
        const subStageError =
          stageErrors && (stage.key === 'verifying' || stage.key === 'thumbnail' || stage.key === 'comment')
            ? stageErrors[stage.key]
            : undefined
        const hasSubStageError = !!subStageError

        let icon
        let pillClass = 'border border-gray-700 bg-gray-800 text-gray-500'
        let labelClass = 'text-gray-500'
        let dataState: string = isFailedHere
          ? 'failed'
          : isCompleted
          ? 'completed'
          : isCurrent
          ? 'current'
          : 'pending'

        if (hasSubStageError) {
          icon = <X className="w-3.5 h-3.5 text-red-400" />
          pillClass = 'border border-red-500/40 bg-red-500/10 text-red-300'
          labelClass = 'text-red-300'
          dataState = 'error'
        } else if (isFailedHere) {
          icon = <XCircle className="w-3.5 h-3.5 text-red-400" />
          pillClass = 'border border-red-500/40 bg-red-500/10 text-red-300'
          labelClass = 'text-red-300'
        } else if (isCompleted) {
          icon = <CheckCircle className="w-3.5 h-3.5 text-green-400" />
          pillClass = 'border border-green-500/40 bg-green-500/10 text-green-300'
          labelClass = 'text-green-300'
        } else if (isCurrent) {
          icon = <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
          pillClass = 'border border-indigo-500/50 bg-indigo-500/15 text-indigo-200'
          labelClass = 'text-indigo-200'
        } else {
          icon = <Circle className="w-3.5 h-3.5 text-gray-600" />
        }

        const pillElement = (
          <div
            className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs ${pillClass}`}
            data-stage={stage.key}
            data-state={dataState}
          >
            {icon}
            <span className={labelClass}>{stage.label}</span>
          </div>
        )

        return (
          <div key={stage.key} className="flex items-center gap-1">
            {hasSubStageError && subStageError ? (
              <ErrorTooltip message={subStageError}>{pillElement}</ErrorTooltip>
            ) : (
              pillElement
            )}
            {idx < stages.length - 1 && (
              <div
                className={`w-2 h-px ${
                  !failed && (allDone || currentIndex > idx) ? 'bg-green-500/40' : 'bg-gray-700'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
