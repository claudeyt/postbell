import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { updateChannel, pullYoutubeTagsForChannel } from '../../api/channels'
import { listSchedules } from '../../api/languageSchedules'
import LanguageSelector from './LanguageSelector'
import type { Channel, LanguageSchedule } from '../../types'

const HHMM_RE = /^([01]\d|2[0-3]):[0-5]\d$/

interface ChannelCardProps {
  channel: Channel
  selectable?: boolean
  selected?: boolean
  onSelect?: (id: number) => void
}

export default function ChannelCard({
  channel,
  selectable,
  selected,
  onSelect,
}: ChannelCardProps) {
  const [desc, setDesc] = useState(channel.default_description || '')
  const [comment, setComment] = useState(channel.default_comment || '')
  const [tagsValue, setTagsValue] = useState(channel.default_tags || '')
  const [pullingTags, setPullingTags] = useState(false)
  const [scheduleTime, setScheduleTime] = useState(channel.custom_schedule_time || '')

  // Re-sync local state whenever the channel prop changes (e.g. bulk pull, refetch).
  // The textarea is uncontrolled-ish via useState; without this it would stay
  // pinned to the value at first mount even after the parent re-fetched channels.
  useEffect(() => {
    setDesc(channel.default_description || '')
  }, [channel.default_description])
  useEffect(() => {
    setComment(channel.default_comment || '')
  }, [channel.default_comment])
  useEffect(() => {
    setTagsValue(channel.default_tags || '')
  }, [channel.default_tags])
  useEffect(() => {
    setScheduleTime(channel.custom_schedule_time || '')
  }, [channel.custom_schedule_time])
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (data: { language_code?: string; default_description?: string; default_comment?: string; default_tags?: string | null; custom_schedule_time?: string | null }) =>
      updateChannel(channel.id, data),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['channels'] }),
  })

  async function handlePullTags() {
    if (pullingTags) return
    setPullingTags(true)
    try {
      const updated = await pullYoutubeTagsForChannel(channel.id)
      setTagsValue(updated.default_tags || '')
      queryClient.invalidateQueries({ queryKey: ['channels'] })
    } catch (e) {
      console.error('Failed to pull tags from YouTube', e)
    } finally {
      setPullingTags(false)
    }
  }

  const { data: schedules = [] } = useQuery<LanguageSchedule[]>({
    queryKey: ['languageSchedules'],
    queryFn: listSchedules,
    enabled: !selectable,
  })

  const langDefault = channel.language_code
    ? schedules.find((s) => s.language_code === channel.language_code)?.time_brt
    : undefined

  const scheduleInvalid = scheduleTime.length > 0 && !HHMM_RE.test(scheduleTime)

  function buildScheduleHint(): string {
    const lang = (channel.language_code || '').toUpperCase()
    if (channel.custom_schedule_time) {
      const fallback = langDefault ? `${langDefault} (${lang})` : 'do padrão do idioma'
      return `Override ativo. Este canal publica às ${channel.custom_schedule_time} BRT ao invés de ${fallback}.`
    }
    if (langDefault) {
      return `Vazio = usa o horário do idioma (${lang} · ${langDefault}).`
    }
    return 'Vazio = sem horário configurado para este idioma.'
  }

  function handleScheduleBlur() {
    const raw = scheduleTime.trim()
    if (raw === '') {
      if (channel.custom_schedule_time) {
        mutation.mutate({ custom_schedule_time: null })
      }
      return
    }
    if (!HHMM_RE.test(raw)) return
    if (raw === (channel.custom_schedule_time || '')) return
    mutation.mutate({ custom_schedule_time: raw })
  }

  return (
    <div
      className={`bg-gray-800 rounded-lg p-4 border ${selected ? 'border-indigo-500 ring-1 ring-indigo-500' : 'border-gray-700'} transition-all ${selectable ? 'cursor-pointer hover:border-gray-600' : ''}`}
      onClick={() => selectable && onSelect?.(channel.id)}
    >
      <div className="flex items-center gap-3">
        {selectable && (
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onSelect?.(channel.id)}
            className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-indigo-500 focus:ring-indigo-500"
            onClick={(e) => e.stopPropagation()}
          />
        )}
        {channel.thumbnail_url ? (
          <img
            src={channel.thumbnail_url}
            alt=""
            className="w-10 h-10 rounded-full flex-shrink-0"
          />
        ) : (
          <div className="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center text-gray-400 text-sm flex-shrink-0">
            {channel.channel_name.charAt(0)}
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-white font-medium truncate">
            {channel.channel_name}
          </p>
          {channel.alias && (
            <p className="text-xs text-gray-400">{channel.alias}</p>
          )}
        </div>
      </div>
      {!channel.language_code && (
        <div className="mt-2 flex items-center gap-1.5 text-amber-400">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="text-xs">Set language for auto-routing</span>
        </div>
      )}
      <div className="mt-3">
        <LanguageSelector
          value={channel.language_code}
          onChange={(code) => mutation.mutate({ language_code: code })}
          compact
        />
      </div>
      {!selectable && (
        <div className="mt-3">
          <label className="text-xs text-gray-400 mb-1 block">Default Description</label>
          <textarea
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            onBlur={() => {
              if (desc !== (channel.default_description || '')) {
                mutation.mutate({ default_description: desc })
              }
            }}
            placeholder="Description applied to uploads on this channel"
            rows={2}
            className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>
      )}
      {!selectable && (
        <div className="mt-3">
          <label className="text-xs text-gray-400 mb-1 block">Default Comment</label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onBlur={() => {
              if (comment !== (channel.default_comment || '')) {
                mutation.mutate({ default_comment: comment })
              }
            }}
            placeholder="Auto-posted as the first comment after upload"
            rows={2}
            className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 resize-none"
          />
        </div>
      )}
      {!selectable && (
        <div className="mt-3">
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs text-gray-400 block">Default Tags</label>
            <button
              type="button"
              onClick={handlePullTags}
              disabled={pullingTags}
              className="text-[10px] px-2 py-0.5 rounded bg-amber-700 hover:bg-amber-600 text-white disabled:bg-gray-700 disabled:text-gray-500"
            >
              {pullingTags ? '...' : 'Puxar do YT'}
            </button>
          </div>
          <textarea
            value={tagsValue}
            onChange={(e) => setTagsValue(e.target.value)}
            onBlur={() => {
              const next = tagsValue.trim()
              const current = (channel.default_tags || '').trim()
              if (next === current) return
              mutation.mutate({ default_tags: next === '' ? null : tagsValue })
            }}
            placeholder="comma, separated, tags"
            rows={3}
            className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 resize-none font-mono"
          />
        </div>
      )}
      {!selectable && (
        <div className="mt-3">
          <label className="text-xs text-gray-400 mb-1 block">Horário personalizado</label>
          <input
            type="text"
            inputMode="numeric"
            maxLength={5}
            placeholder="HH:MM"
            value={scheduleTime}
            onChange={(e) => setScheduleTime(e.target.value)}
            onBlur={handleScheduleBlur}
            className={`w-24 bg-gray-700 border ${scheduleInvalid ? 'border-red-600' : 'border-gray-600'} rounded px-2 py-1.5 text-sm text-white font-mono text-center placeholder-gray-500 focus:outline-none focus:border-indigo-500`}
          />
          <p className="text-xs text-gray-500 mt-1">{buildScheduleHint()}</p>
        </div>
      )}
    </div>
  )
}
