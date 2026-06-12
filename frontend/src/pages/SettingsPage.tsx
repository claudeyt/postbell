import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Save, CheckCircle, XCircle, Loader2, Zap, Trash2 } from 'lucide-react'
import { getSettings, updateSettings, getGeminiKey, testGeminiKey } from '../api/settings'
import type { SettingsUpdate } from '../api/settings'
import PostingHoursPanel from '../components/settings/PostingHoursPanel'

type ToastState = { type: 'success' | 'error'; message: string } | null

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [toast, setToast] = useState<ToastState>(null)
  const [showKey, setShowKey] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const [form, setForm] = useState<SettingsUpdate>({
    gemini_api_key: '',
    upload_chunk_size_mb: 10,
    youtube_daily_quota: 10000,
    default_privacy: 'private',
    default_description: '',
    default_tags: [],
  })
  const [tagsInput, setTagsInput] = useState('')
  const [testingKey, setTestingKey] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)

  useEffect(() => {
    if (data) {
      getGeminiKey().then((res) => {
        setForm({
          gemini_api_key: res.gemini_api_key || '',
          upload_chunk_size_mb: data.upload_chunk_size_mb,
          youtube_daily_quota: data.youtube_daily_quota,
          default_privacy: data.default_privacy,
          default_description: data.default_description,
          default_tags: data.default_tags,
        })
      }).catch(() => {
        setForm({
          gemini_api_key: '',
          upload_chunk_size_mb: data.upload_chunk_size_mb,
          youtube_daily_quota: data.youtube_daily_quota,
          default_privacy: data.default_privacy,
          default_description: data.default_description,
          default_tags: data.default_tags,
        })
      })
      setTagsInput(data.default_tags.join(', '))
    }
  }, [data])

  async function handleTestKey() {
    setTestingKey(true)
    setTestResult(null)
    try {
      const result = await testGeminiKey()
      if (result.success) {
        setTestResult({ success: true, message: `Key works! Response: "${result.response}"` })
      } else {
        setTestResult({ success: false, message: result.error || 'Test failed' })
      }
    } catch {
      setTestResult({ success: false, message: 'Failed to test key' })
    } finally {
      setTestingKey(false)
    }
  }

  const saveMutation = useMutation({
    mutationFn: (payload: SettingsUpdate) => updateSettings(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      showToast({ type: 'success', message: 'Settings saved successfully.' })
    },
    onError: (err: Error) => {
      showToast({ type: 'error', message: err.message || 'Failed to save settings.' })
    },
  })

  function showToast(t: ToastState) {
    setToast(t)
    setTimeout(() => setToast(null), 4000)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)

    const payload: SettingsUpdate = { ...form, default_tags: tags }
    saveMutation.mutate(payload)
  }

  if (isLoading) {
    return (
      <div className="p-6 flex items-center gap-2 text-gray-400">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading settings...
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
          Failed to load settings: {(error as Error).message}
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-400 mt-1">Application configuration</p>
      </div>

      {toast && (
        <div
          className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm font-medium ${
            toast.type === 'success'
              ? 'bg-green-900/40 border border-green-700 text-green-300'
              : 'bg-red-900/40 border border-red-700 text-red-300'
          }`}
        >
          {toast.type === 'success' ? (
            <CheckCircle className="w-4 h-4 shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 shrink-0" />
          )}
          {toast.message}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 space-y-4">
          <h2 className="text-base font-semibold text-white">API Keys</h2>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-300">
              Gemini API Key
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showKey ? 'text' : 'password'}
                  placeholder="Paste your Gemini API key..."
                  value={form.gemini_api_key ?? ''}
                  onChange={(e) => setForm({ ...form, gemini_api_key: e.target.value })}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 pr-10 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                >
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <button
                type="button"
                onClick={handleTestKey}
                disabled={testingKey || !form.gemini_api_key}
                className="flex items-center gap-1.5 px-3 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
              >
                {testingKey ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                Test Key
              </button>
            </div>
            {testResult && (
              <div className={`flex items-center gap-1.5 text-xs mt-1 ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                {testResult.success ? <CheckCircle className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                {testResult.message}
              </div>
            )}
          </div>
        </div>

        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 space-y-4">
          <h2 className="text-base font-semibold text-white">Upload Settings</h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="block text-sm font-medium text-gray-300">
                Upload Chunk Size (MB)
              </label>
              <input
                type="number"
                min={1}
                max={256}
                value={form.upload_chunk_size_mb ?? 10}
                onChange={(e) =>
                  setForm({ ...form, upload_chunk_size_mb: Number(e.target.value) })
                }
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="space-y-1">
              <label className="block text-sm font-medium text-gray-300">
                YouTube Daily Quota
              </label>
              <input
                type="number"
                min={1}
                value={form.youtube_daily_quota ?? 10000}
                onChange={(e) =>
                  setForm({ ...form, youtube_daily_quota: Number(e.target.value) })
                }
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>
        </div>

        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 space-y-4">
          <h2 className="text-base font-semibold text-white">Upload Defaults</h2>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-300">
              Default Privacy
            </label>
            <select
              value={form.default_privacy ?? 'private'}
              onChange={(e) => setForm({ ...form, default_privacy: e.target.value })}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="private">Private</option>
              <option value="unlisted">Unlisted</option>
              <option value="public">Public</option>
            </select>
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-300">
              Default Description
            </label>
            <textarea
              rows={4}
              value={form.default_description ?? ''}
              onChange={(e) => setForm({ ...form, default_description: e.target.value })}
              placeholder="Default video description..."
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
            />
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-300">
              Default Tags
            </label>
            <input
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder="tag1, tag2, tag3"
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <p className="text-xs text-gray-500">Comma-separated</p>
          </div>
        </div>

        <PostingHoursPanel />

        {/* Manutencao */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-5 space-y-4">
          <div>
            <h2 className="text-base font-semibold text-white">Manutenção</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Liberar espaço de arquivos temporários ou ações administrativas.
            </p>
          </div>
          <ClearTempButton />
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saveMutation.isPending}
            className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
          >
            {saveMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                Save Settings
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}


function ClearTempButton() {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ deleted: number; freed_mb: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleClick() {
    if (busy) return
    if (!confirm('Deletar todos os arquivos temporários da pasta data/temp?')) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await fetch('/api/settings/clear-temp', { method: 'POST' })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${r.status}`)
      }
      const data = await r.json()
      setResult({ deleted: data.deleted, freed_mb: data.freed_mb })
      setTimeout(() => setResult(null), 8000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao limpar')
      setTimeout(() => setError(null), 8000)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={busy}
        className="flex items-center gap-2 px-3 py-2 bg-red-900/50 hover:bg-red-800 text-red-200 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium rounded-lg border border-red-800 transition-colors"
      >
        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
        Limpar pasta temp
      </button>
      <p className="text-xs text-gray-500">
        Remove vídeos e thumbnails que sobraram de uploads anteriores.
        Não roda enquanto houver upload em andamento.
      </p>
      {result && (
        <p className="text-xs text-emerald-300">
          ✓ {result.deleted} arquivo{result.deleted === 1 ? '' : 's'} removido{result.deleted === 1 ? '' : 's'}, {result.freed_mb} MB liberados.
        </p>
      )}
      {error && (
        <p className="text-xs text-red-300">✗ {error}</p>
      )}
    </div>
  )
}
