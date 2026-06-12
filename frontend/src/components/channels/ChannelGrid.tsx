import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Wand2, Loader2 } from 'lucide-react'
import { getChannels, autoDetectLanguages } from '../../api/channels'
import { getAccounts } from '../../api/accounts'
import ChannelCard from './ChannelCard'
import type { Channel } from '../../types'

interface ChannelGridProps {
  selectable?: boolean
  selectedIds?: Set<number>
  onToggle?: (id: number) => void
}

export default function ChannelGrid({
  selectable,
  selectedIds,
  onToggle,
}: ChannelGridProps) {
  const queryClient = useQueryClient()
  const [detectResult, setDetectResult] = useState<string | null>(null)
  const { data: channels = [], isLoading } = useQuery({
    queryKey: ['channels'],
    queryFn: getChannels,
  })
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: getAccounts,
  })
  const detectMutation = useMutation({
    mutationFn: autoDetectLanguages,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['channels'] })
      if (data.updated > 0) {
        setDetectResult(`${data.updated} channel${data.updated > 1 ? 's' : ''} updated`)
      } else {
        setDetectResult('No languages detected — set them manually')
      }
      setTimeout(() => setDetectResult(null), 5000)
    },
  })

  if (isLoading) {
    return <div className="text-gray-400">Loading channels...</div>
  }

  if (channels.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <p>No channels yet. Add a Google account first.</p>
      </div>
    )
  }

  // Group channels by account
  const grouped = accounts
    .map((account) => ({
      account,
      channels: channels.filter(
        (ch: Channel) => ch.account_id === account.id,
      ),
    }))
    .filter((g) => g.channels.length > 0)

  // Ungrouped channels (account might have been deleted)
  const ungrouped = channels.filter(
    (ch: Channel) => !accounts.some((a) => a.id === ch.account_id),
  )

  const hasUnsetLanguages = channels.some((ch: Channel) => !ch.language_code)

  return (
    <div className="space-y-6">
      {!selectable && hasUnsetLanguages && (
        <div className="flex items-center gap-3">
          <button
            onClick={() => detectMutation.mutate()}
            disabled={detectMutation.isPending}
            className="flex items-center gap-2 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {detectMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Wand2 className="w-4 h-4" />
            )}
            Auto-detect languages
          </button>
          {detectResult && (
            <span className="text-sm text-gray-400">{detectResult}</span>
          )}
        </div>
      )}
      {selectable ? (
        <>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">
              {selectedIds?.size || 0} of {channels.length} channels selected
            </span>
            <button
              onClick={() => {
                if (selectedIds?.size === channels.length) {
                  channels.forEach((ch: Channel) => onToggle?.(ch.id))
                } else {
                  channels.forEach((ch: Channel) => {
                    if (!selectedIds?.has(ch.id)) onToggle?.(ch.id)
                  })
                }
              }}
              className="text-sm text-indigo-400 hover:text-indigo-300"
            >
              {selectedIds?.size === channels.length
                ? 'Deselect All'
                : 'Select All'}
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {channels.map((ch: Channel) => (
              <ChannelCard
                key={ch.id}
                channel={ch}
                selectable
                selected={selectedIds?.has(ch.id)}
                onSelect={onToggle}
              />
            ))}
          </div>
        </>
      ) : (
        <>
          {grouped.map(({ account, channels: acctChannels }) => (
            <div key={account.id}>
              <h3 className="text-sm font-medium text-gray-300 mb-3">
                {account.email.includes('@pages.plusgoogle.com')
                  ? acctChannels[0]?.channel_name || 'Brand Account'
                  : account.email}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {acctChannels.map((ch: Channel) => (
                  <ChannelCard
                    key={ch.id}
                    channel={ch}
                  />
                ))}
              </div>
            </div>
          ))}
          {ungrouped.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-300 mb-3">
                Other Channels
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {ungrouped.map((ch: Channel) => (
                  <ChannelCard
                    key={ch.id}
                    channel={ch}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
