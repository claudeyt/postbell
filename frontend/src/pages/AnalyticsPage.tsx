import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Clock,
  DollarSign,
  Eye,
  Loader2,
  RotateCw,
  Users,
} from 'lucide-react'
import { getChannels } from '../api/channels'
import { getAnalyticsSummary } from '../api/analytics'
import type { ChannelAnalytics } from '../types'

function formatCount(value: number): string {
  return Math.round(value).toLocaleString()
}

function formatRevenue(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return `$${value.toFixed(2)}`
}

function formatDateBR(iso: string | null | undefined): string | null {
  if (!iso) return null
  // ISO date YYYY-MM-DD -> DD/MM (Brazilian short form)
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  return m ? `${m[3]}/${m[2]}` : iso
}

function MetricCard({
  icon: Icon,
  label,
  value,
  dateLabel,
}: {
  icon: typeof Eye
  label: string
  value: string
  dateLabel?: string | null
}) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-5">
      <div className="flex items-center gap-2 text-gray-400 mb-3">
        <Icon className="w-4 h-4" />
        <span className="text-xs font-semibold uppercase tracking-wider">
          {label}
        </span>
      </div>
      <p className="text-3xl font-bold text-white">{value}</p>
      {dateLabel && (
        <p className="text-xs text-gray-500 mt-2">{dateLabel}</p>
      )}
    </div>
  )
}

function StatusBadge({ channel }: { channel: ChannelAnalytics }) {
  if (channel.available) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
        OK
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-900/40 text-amber-400 border border-amber-800"
      title={channel.error ?? undefined}
    >
      Unavailable
    </span>
  )
}

export default function AnalyticsPage() {
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [initialized, setInitialized] = useState(false)

  const {
    data: channels = [],
    isLoading: channelsLoading,
  } = useQuery({
    queryKey: ['channels'],
    queryFn: getChannels,
  })

  // Default to ALL channels selected once channels load.
  useEffect(() => {
    if (!initialized && channels.length > 0) {
      setSelectedIds(channels.map((c) => c.id))
      setInitialized(true)
    }
  }, [channels, initialized])

  const queryClient = useQueryClient()

  const {
    data,
    isLoading: summaryLoading,
    isFetching: summaryFetching,
    isError: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['analytics', selectedIds],
    queryFn: () => getAnalyticsSummary(selectedIds),
    enabled: channels.length > 0 && selectedIds.length > 0,
    placeholderData: (prev) => prev,
    // Only refetch when the channel selection changes or the user clicks
    // "Atualizar" — never on window-focus or remount-with-fresh-cache.
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: Infinity,
  })

  const handleRefresh = () => {
    // Bust any cached page for these channels and force re-fetch
    queryClient.invalidateQueries({ queryKey: ['analytics'] })
    refetchSummary()
  }

  const toggleChannel = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const selectAll = () => setSelectedIds(channels.map((c) => c.id))
  const clearAll = () => setSelectedIds([])

  const allUnavailable =
    !!data &&
    data.channels.length > 0 &&
    data.channels.every((c) => !c.available)

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Analytics</h1>
        <p className="text-sm text-gray-400 mt-1">
          Views, subscribers and revenue across your channels
        </p>
      </div>

      {channelsLoading ? (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-gray-400">
          Loading...
        </div>
      ) : channels.length === 0 ? (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-gray-400">
          No channels. Add an account first on the Accounts page.
        </div>
      ) : (
        <>
          {/* Re-auth banner */}
          {allUnavailable && (
            <div className="bg-amber-900/30 border border-amber-700 rounded-lg p-4 flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-amber-300">
                  Analytics not enabled yet
                </p>
                <p className="text-sm text-amber-200/80 mt-1">
                  Re-authenticate your accounts on the Accounts page to grant
                  the YouTube Analytics permissions. Once re-authenticated, your
                  real numbers will appear here automatically.
                </p>
              </div>
            </div>
          )}

          {/* Channel selection */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Channels
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={selectAll}
                  className="px-2.5 py-1 rounded text-xs font-medium text-gray-300 hover:text-white hover:bg-gray-700 transition-colors"
                >
                  Select all
                </button>
                <button
                  onClick={clearAll}
                  className="px-2.5 py-1 rounded text-xs font-medium text-gray-300 hover:text-white hover:bg-gray-700 transition-colors"
                >
                  Clear
                </button>
                <button
                  onClick={handleRefresh}
                  disabled={summaryFetching || selectedIds.length === 0}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium border transition-colors ${
                    summaryFetching || selectedIds.length === 0
                      ? 'bg-gray-800 text-gray-500 border-gray-700 cursor-not-allowed'
                      : 'bg-indigo-600 hover:bg-indigo-500 text-white border-indigo-500'
                  }`}
                  title={selectedIds.length === 0 ? 'Selecione canais primeiro' : 'Buscar dados novos do YouTube Analytics'}
                >
                  {summaryFetching ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <RotateCw className="w-3.5 h-3.5" />
                  )}
                  Atualizar
                </button>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {channels.map((ch) => {
                const active = selectedIds.includes(ch.id)
                return (
                  <button
                    key={ch.id}
                    onClick={() => toggleChannel(ch.id)}
                    className={`px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                      active
                        ? 'bg-indigo-600 text-white border-indigo-500'
                        : 'bg-gray-900 text-gray-400 border-gray-700 hover:text-white hover:border-gray-600'
                    }`}
                  >
                    {ch.alias ?? ch.channel_name}
                  </button>
                )
              })}
            </div>
          </div>

          {selectedIds.length === 0 ? (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-gray-400">
              Select at least one channel to see analytics.
            </div>
          ) : summaryLoading && !data ? (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-gray-400">
              Loading...
            </div>
          ) : summaryError ? (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center text-red-400">
              Failed to load analytics.
            </div>
          ) : data ? (
            <>
              {/* Summed metric cards across the selected available channels */}
              {(() => {
                const avail = data.channels.filter((ch) => ch.available)
                // Latest date among the channels for each metric
                const viewsDates = avail.flatMap((ch) => ch.views_window_dates || [])
                const latestViewsDate = viewsDates.length
                  ? viewsDates.slice().sort().reverse()[0]
                  : null
                const subsDates = avail
                  .map((ch) => ch.subscribers_last_date)
                  .filter((d): d is string => !!d)
                const latestSubsDate = subsDates.length
                  ? subsDates.slice().sort().reverse()[0]
                  : null
                const revDates = avail
                  .map((ch) => ch.revenue_last_date)
                  .filter((d): d is string => !!d)
                const latestRevDate = revDates.length
                  ? revDates.slice().sort().reverse()[0]
                  : null

                const sumViews = avail.reduce((s, ch) => s + ch.views_48h, 0)
                const sumSubs = avail.reduce((s, ch) => s + ch.subscribers_last, 0)
                const revVals = avail
                  .filter((ch) => ch.revenue_last != null)
                  .map((ch) => ch.revenue_last as number)
                const sumRev = revVals.length ? revVals.reduce((a, b) => a + b, 0) : null

                return (
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <MetricCard
                      icon={Clock}
                      label="Total Views (48h)"
                      value={formatCount(sumViews)}
                      dateLabel={
                        latestViewsDate
                          ? `Dados até ${formatDateBR(latestViewsDate)}`
                          : null
                      }
                    />
                    <MetricCard
                      icon={Users}
                      label="Inscritos (último dia)"
                      value={formatCount(sumSubs)}
                      dateLabel={
                        latestSubsDate
                          ? `Dados de ${formatDateBR(latestSubsDate)}`
                          : null
                      }
                    />
                    <MetricCard
                      icon={DollarSign}
                      label="Receita (último dia)"
                      value={formatRevenue(sumRev)}
                      dateLabel={
                        latestRevDate
                          ? `Dados de ${formatDateBR(latestRevDate)}`
                          : null
                      }
                    />
                  </div>
                )
              })()}
              <p className="text-xs text-gray-500">
                Totalizado em {data.averages.channel_count}{' '}
                {data.averages.channel_count === 1 ? 'canal' : 'canais'}.
              </p>

              {/* Per-channel breakdown */}
              <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-700 text-left">
                      <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                        Channel
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider text-right">
                        Views 48h
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider text-right">
                        Inscritos (último)
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider text-right">
                        Receita (último)
                      </th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-700">
                    {data.channels.map((ch) => (
                      <tr
                        key={ch.channel_id}
                        className="hover:bg-gray-700/50 transition-colors"
                      >
                        <td className="px-4 py-3 text-white">
                          {ch.channel_name}
                        </td>
                        <td className="px-4 py-3 text-gray-300 text-right">
                          {ch.available ? (
                            <div>
                              <div>{formatCount(ch.views_48h)}</div>
                              {ch.views_window_dates?.length ? (
                                <div className="text-[10px] text-gray-500 mt-0.5">
                                  {ch.views_window_dates.length === 2
                                    ? `${formatDateBR(ch.views_window_dates[1])} + ${formatDateBR(ch.views_window_dates[0])}`
                                    : formatDateBR(ch.views_window_dates[0])}
                                </div>
                              ) : null}
                            </div>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-300 text-right">
                          {ch.available ? (
                            <div>
                              <div>{formatCount(ch.subscribers_last)}</div>
                              {ch.subscribers_last_date && (
                                <div className="text-[10px] text-gray-500 mt-0.5">
                                  {formatDateBR(ch.subscribers_last_date)}
                                </div>
                              )}
                            </div>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-300 text-right">
                          {ch.available ? (
                            <div>
                              <div>{formatRevenue(ch.revenue_last)}</div>
                              {ch.revenue_last_date && (
                                <div className="text-[10px] text-gray-500 mt-0.5">
                                  {formatDateBR(ch.revenue_last_date)}
                                </div>
                              )}
                            </div>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <StatusBadge channel={ch} />
                            {!ch.available && ch.error && (
                              <span
                                className="text-xs text-gray-500 truncate max-w-[180px]"
                                title={ch.error}
                              >
                                {ch.error}
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {data.note && (
                <p className="text-xs text-gray-600">{data.note}</p>
              )}
            </>
          ) : null}
        </>
      )}
    </div>
  )
}
