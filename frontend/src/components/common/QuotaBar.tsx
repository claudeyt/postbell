interface QuotaBarProps {
  projectName: string
  used: number
  limit: number
  /**
   * Optional sub-label rendered under the project name. Used to distinguish
   * the multiple meters per project (e.g. "créditos" vs "vídeos").
   */
  label?: string
}

export default function QuotaBar({ projectName, used, limit, label }: QuotaBarProps) {
  const percentage = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0

  const barColor =
    percentage > 85
      ? 'bg-red-500'
      : percentage > 60
        ? 'bg-yellow-500'
        : 'bg-green-500'

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-300 truncate" title={projectName}>
          {label ? `${projectName} · ${label}` : projectName}
        </span>
        <span className="text-xs text-gray-400 ml-2 shrink-0">
          {used.toLocaleString()} / {limit.toLocaleString()} ({percentage}%)
        </span>
      </div>
      <div className="h-2 w-full bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}
