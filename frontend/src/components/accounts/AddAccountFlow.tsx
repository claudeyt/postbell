import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getProjects } from '../../api/projects'
import { startAuth, startInstalledAuth } from '../../api/accounts'
import { LogIn, CheckCircle, Loader2, Plus } from 'lucide-react'
import type { Project } from '../../types'

type FlowStep = 'select-project' | 'waiting' | 'success'

/**
 * Detect whether we're running inside the Electron shell. The preload script
 * (postbell-electron/preload.js) exposes ``window.electronAPI``; pure browser
 * builds (Vite dev / served by uvicorn) leave it undefined. We use this to
 * pick between the legacy popup-based web flow and the installed-app flow.
 */
function isElectron(): boolean {
  return typeof window !== 'undefined' && Boolean(window.electronAPI)
}

export default function AddAccountFlow({
  onClose,
}: {
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [step, setStep] = useState<FlowStep>('select-project')
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const [authEmail, setAuthEmail] = useState<string | null>(null)
  const [channelsAdded, setChannelsAdded] = useState(0)

  const { data: projects, isLoading: projectsLoading } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: getProjects,
  })

  // Listen for postMessage from OAuth callback tab
  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.data?.type === 'oauth_complete') {
        setAuthEmail(event.data.email || 'unknown')
        setStep('success')
        setChannelsAdded(prev => prev + 1)
        queryClient.invalidateQueries({ queryKey: ['accounts'] })
        queryClient.invalidateQueries({ queryKey: ['channels'] })
        queryClient.invalidateQueries({ queryKey: ['account-channels'] })
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [queryClient])

  /**
   * Begin authentication. In Electron we use the installed-app flow: a single
   * blocking POST that opens the user's default browser via Python's
   * ``webbrowser.open``, then resolves with the new account once they finish
   * (or rejects on timeout/cancel). In a regular browser we keep the legacy
   * popup-based web flow.
   */
  async function beginAuth(forSecondAccount: boolean): Promise<void> {
    if (!selectedProjectId) return
    setError(null)
    if (forSecondAccount) setAuthEmail(null)

    if (isElectron()) {
      // Installed-app flow: backend blocks for up to 5 min waiting for the
      // browser handshake. We move to 'waiting' first so the UI updates,
      // then await the response and jump to 'success'.
      setStep('waiting')
      try {
        const result = await startInstalledAuth(selectedProjectId)
        setAuthEmail(result.email)
        setStep('success')
        setChannelsAdded((prev) => prev + (result.total_channels ?? 0))
        queryClient.invalidateQueries({ queryKey: ['accounts'] })
        queryClient.invalidateQueries({ queryKey: ['channels'] })
        queryClient.invalidateQueries({ queryKey: ['account-channels'] })
      } catch (err: unknown) {
        // Auth failed or timed out — drop back to the project picker so the
        // user can retry without reloading the modal.
        setStep('select-project')
        if (err instanceof Error) {
          setError(err.message)
        } else {
          setError('Failed to start authentication')
        }
      }
      return
    }

    // Web/dev flow (legacy popup).
    try {
      const { auth_url } = await startAuth(selectedProjectId)
      window.open(auth_url, '_blank', 'width=600,height=700')
      setStep('waiting')
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Failed to start authentication')
      }
    }
  }

  async function handleStartAuth() {
    await beginAuth(false)
  }

  async function handleAddAnother() {
    await beginAuth(true)
  }

  function handleDone() {
    queryClient.invalidateQueries({ queryKey: ['accounts'] })
    queryClient.invalidateQueries({ queryKey: ['channels'] })
    queryClient.invalidateQueries({ queryKey: ['account-channels'] })
    onClose()
  }

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-5">
      <h3 className="text-sm font-semibold text-white mb-4">
        Add Google Account
      </h3>

      {step === 'select-project' && (
        <div className="space-y-4">
          <div>
            <label
              htmlFor="auth-project"
              className="block text-sm text-gray-300 mb-1"
            >
              Select GCP Project
            </label>
            {projectsLoading ? (
              <div className="flex items-center gap-2 text-gray-400 text-sm py-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading projects...
              </div>
            ) : projects && projects.length > 0 ? (
              <select
                id="auth-project"
                value={selectedProjectId ?? ''}
                onChange={(e) =>
                  setSelectedProjectId(
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option value="">-- Choose a project --</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            ) : (
              <p className="text-sm text-gray-500">
                No GCP projects registered. Add a project above first.
              </p>
            )}
          </div>

          {error && (
            <div className="bg-red-900/30 border border-red-700 rounded-lg px-3 py-2 text-sm text-red-300">
              {error}
            </div>
          )}

          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={handleStartAuth}
              disabled={!selectedProjectId}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              <LogIn className="w-4 h-4" />
              Authenticate with Google
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white text-sm font-medium transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {step === 'waiting' && (
        <div className="text-center py-6">
          <Loader2 className="w-8 h-8 text-indigo-400 animate-spin mx-auto mb-3" />
          <p className="text-gray-300 text-sm">
            Waiting for Google authentication...
          </p>
          <p className="text-gray-500 text-xs mt-1">
            {isElectron()
              ? 'Complete the sign-in in your default browser (times out in 5 min)'
              : 'Complete the sign-in in the popup window'}
          </p>
          <button
            onClick={onClose}
            className="mt-4 px-4 py-2 text-gray-400 hover:text-white text-sm font-medium transition-colors"
          >
            Cancel
          </button>
        </div>
      )}

      {step === 'success' && (
        <div className="text-center py-6">
          <CheckCircle className="w-8 h-8 text-green-400 mx-auto mb-3" />
          <p className="text-white text-sm font-medium">Authentication Successful!</p>
          {authEmail && (
            <p className="text-gray-400 text-xs mt-1">Connected as {authEmail}</p>
          )}
          <p className="text-gray-500 text-xs mt-2">
            {channelsAdded} {channelsAdded === 1 ? 'channel' : 'channels'} added in this session
          </p>
          <div className="flex items-center justify-center gap-3 mt-4">
            <button
              onClick={handleAddAnother}
              className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Plus className="w-4 h-4" />
              Add Another Channel
            </button>
            <button
              onClick={handleDone}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Done
            </button>
          </div>
          <p className="text-gray-600 text-xs mt-3">
            Have more Brand Account channels? Click "Add Another Channel" and select a different account in Google's picker.
          </p>
        </div>
      )}
    </div>
  )
}
