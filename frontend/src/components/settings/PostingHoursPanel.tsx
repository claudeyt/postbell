import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Clock } from 'lucide-react'
import { getChannels } from '../../api/channels'
import { listSchedules, upsertSchedule } from '../../api/languageSchedules'
import { LANGUAGES } from '../channels/LanguageSelector'
import type { Channel, LanguageSchedule } from '../../types'

const HHMM_RE = /^([01]\d|2[0-3]):[0-5]\d$/

const LANG_INFO: Record<string, { name: string; flag: string }> = LANGUAGES.reduce(
  (acc, l) => {
    acc[l.code] = { name: l.name, flag: l.flag }
    return acc
  },
  {} as Record<string, { name: string; flag: string }>,
)

function langDisplay(code: string): { name: string; flag: string } {
  return LANG_INFO[code] ?? { name: code.toUpperCase(), flag: '\u{1F3F3}\u{FE0F}' }
}

interface RowProps {
  langCode: string
  channelCount: number
  serverTime: string | undefined
}

function ScheduleRow({ langCode, channelCount, serverTime }: RowProps) {
  const queryClient = useQueryClient()
  const [value, setValue] = useState<string>(serverTime ?? '')
  const [savedFlash, setSavedFlash] = useState(false)
  const debounceRef = useRef<number | null>(null)
  const lastSavedRef = useRef<string | undefined>(serverTime)

  // Re-sync local value if the server value changes from outside
  useEffect(() => {
    if (serverTime !== lastSavedRef.current) {
      lastSavedRef.current = serverTime
      setValue(serverTime ?? '')
    }
  }, [serverTime])

  const mutation = useMutation({
    mutationFn: (time_brt: string) => upsertSchedule(langCode, time_brt),
    onMutate: async (time_brt) => {
      await queryClient.cancelQueries({ queryKey: ['languageSchedules'] })
      const prev = queryClient.getQueryData<LanguageSchedule[]>(['languageSchedules'])
      queryClient.setQueryData<LanguageSchedule[]>(['languageSchedules'], (old) => {
        const arr = old ?? []
        const idx = arr.findIndex((s) => s.language_code === langCode)
        const next: LanguageSchedule = {
          language_code: langCode,
          time_brt,
          updated_at: new Date().toISOString(),
        }
        if (idx >= 0) {
          const copy = arr.slice()
          copy[idx] = { ...arr[idx], ...next }
          return copy
        }
        return [...arr, next]
      })
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) {
        queryClient.setQueryData(['languageSchedules'], ctx.prev)
      }
    },
    onSuccess: (data) => {
      lastSavedRef.current = data.time_brt
      setSavedFlash(true)
      window.setTimeout(() => setSavedFlash(false), 1500)
      queryClient.invalidateQueries({ queryKey: ['languageSchedules'] })
    },
  })

  function handleChange(next: string) {
    setValue(next)
    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
    if (!HHMM_RE.test(next)) return
    if (next === lastSavedRef.current) return
    debounceRef.current = window.setTimeout(() => {
      mutation.mutate(next)
    }, 800)
  }

  useEffect(() => {
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
    }
  }, [])

  const info = langDisplay(langCode)
  const invalid = value.length > 0 && !HHMM_RE.test(value)

  return (
    <div className="flex items-center gap-3 py-2 border-b border-gray-700 last:border-b-0">
      <div className="flex items-center gap-2 min-w-[180px]">
        <span className="text-lg leading-none">{info.flag}</span>
        <span className="font-mono text-xs text-gray-400 w-8">{langCode.toUpperCase()}</span>
        <span className="text-sm text-white">{info.name}</span>
      </div>
      <input
        type="text"
        inputMode="numeric"
        placeholder="HH:MM"
        maxLength={5}
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        className={`w-24 bg-gray-900 border ${invalid ? 'border-red-600' : 'border-gray-600'} rounded px-2 py-1 text-sm text-white font-mono text-center focus:outline-none focus:ring-2 focus:ring-indigo-500`}
      />
      <span className="text-xs text-gray-500 flex-1">
        aplica em {channelCount} {channelCount === 1 ? 'canal' : 'canais'}
      </span>
      {savedFlash && (
        <span className="flex items-center gap-1 text-xs text-green-400">
          <Check className="w-3.5 h-3.5" />
          salvo
        </span>
      )}
      {mutation.isError && (
        <span className="text-xs text-red-400">erro ao salvar</span>
      )}
    </div>
  )
}

export default function PostingHoursPanel() {
  const { data: channels = [], isLoading: chLoading } = useQuery({
    queryKey: ['channels'],
    queryFn: getChannels,
  })
  const { data: schedules = [], isLoading: schLoading } = useQuery({
    queryKey: ['languageSchedules'],
    queryFn: listSchedules,
  })

  const rows = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const ch of channels as Channel[]) {
      const code = ch.language_code
      if (!code) continue
      counts[code] = (counts[code] ?? 0) + 1
    }
    const langs = Object.keys(counts).sort()
    const scheduleMap = new Map<string, string>(
      schedules.map((s) => [s.language_code, s.time_brt]),
    )
    return langs.map((code) => ({
      code,
      count: counts[code],
      time: scheduleMap.get(code),
    }))
  }, [channels, schedules])

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-white flex items-center gap-2">
          <Clock className="w-4 h-4 text-indigo-400" />
          Horários de postagem
        </h2>
        <p className="text-xs text-gray-400 mt-1">
          Defina o horário padrão de publicação para cada idioma. Cada canal usará esse horário ao
          escolher "Auto-agendar por idioma" no Dashboard.
        </p>
      </div>

      {chLoading || schLoading ? (
        <p className="text-sm text-gray-500">Carregando...</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-gray-500">
          Nenhum canal com idioma configurado ainda. Defina o idioma de cada canal no Dashboard.
        </p>
      ) : (
        <div>
          {rows.map((r) => (
            <ScheduleRow
              key={r.code}
              langCode={r.code}
              channelCount={r.count}
              serverTime={r.time}
            />
          ))}
        </div>
      )}

      <p className="text-xs text-gray-500">
        Todos os horários no fuso de Brasília (BRT, UTC-3).
      </p>
    </div>
  )
}
