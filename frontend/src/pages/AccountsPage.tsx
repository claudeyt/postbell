import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Trash2,
  Loader2,
  UserCircle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Wand2,
  Tag,
} from 'lucide-react'
import ProjectManager from '../components/accounts/ProjectManager'
import AddAccountFlow from '../components/accounts/AddAccountFlow'
import ChannelGrid from '../components/channels/ChannelGrid'
import {
  getAccounts,
  deleteAccount,
  getAccountChannels,
  syncChannels,
} from '../api/accounts'
import {
  getChannels,
  autoDetectChannelLanguages,
  pullYoutubeTagsForAll,
  type AutoDetectResponse,
  type PullYoutubeTagsAllResponse,
} from '../api/channels'
import { getProjects } from '../api/projects'
import type { Account, Project, Channel } from '../types'

function AccountList() {
  const queryClient = useQueryClient()
  const [showAddFlow, setShowAddFlow] = useState(false)
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
  const [expandedAccountId, setExpandedAccountId] = useState<number | null>(
    null,
  )

  const {
    data: accounts,
    isLoading,
    error: fetchError,
  } = useQuery<Account[]>({
    queryKey: ['accounts'],
    queryFn: getAccounts,
  })

  const { data: projects } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: getProjects,
  })

  const { data: channels } = useQuery<Channel[]>({
    queryKey: ['account-channels', expandedAccountId],
    queryFn: () => getAccountChannels(expandedAccountId!),
    enabled: expandedAccountId !== null,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      setDeleteConfirmId(null)
    },
  })

  const syncMutation = useMutation({
    mutationFn: syncChannels,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['channels'] })
      queryClient.invalidateQueries({ queryKey: ['account-channels'] })
    },
  })

  function getProjectName(projectId: number): string {
    const project = projects?.find((p) => p.id === projectId)
    return project?.name ?? `Project #${projectId}`
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 py-8">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading accounts...
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
        Failed to load accounts: {fetchError.message}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">
            Connected Accounts
          </h2>
          <p className="text-sm text-gray-400">
            Google accounts authenticated for YouTube uploads
          </p>
        </div>
        <button
          onClick={() => setShowAddFlow(!showAddFlow)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Account
        </button>
      </div>

      {/* Add Account Flow */}
      {showAddFlow && (
        <AddAccountFlow onClose={() => setShowAddFlow(false)} />
      )}

      {/* Accounts Table */}
      {accounts && accounts.length > 0 ? (
        <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">
                  Email
                </th>
                <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">
                  Project
                </th>
                <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">
                  Token Status
                </th>
                <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">
                  Created
                </th>
                <th className="text-right text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {accounts.map((account) => (
                <tr key={account.id}>
                  <td className="px-4 py-3">
                    <button
                      onClick={() =>
                        setExpandedAccountId(
                          expandedAccountId === account.id
                            ? null
                            : account.id,
                        )
                      }
                      className="text-sm text-white font-medium hover:text-indigo-400 transition-colors text-left"
                    >
                      {account.email}
                    </button>
                    {expandedAccountId === account.id && channels && (
                      <div className="mt-2 ml-2 space-y-1">
                        {channels.length > 0 ? (
                          channels.map((ch) => (
                            <div
                              key={ch.id}
                              className="flex items-center gap-2 text-xs text-gray-400"
                            >
                              {ch.thumbnail_url ? (
                                <img
                                  src={ch.thumbnail_url}
                                  alt=""
                                  className="w-4 h-4 rounded-full"
                                />
                              ) : (
                                <div className="w-4 h-4 rounded-full bg-gray-600" />
                              )}
                              <span>{ch.channel_name}</span>
                              {!ch.is_active && (
                                <span className="text-yellow-500">
                                  (inactive)
                                </span>
                              )}
                            </div>
                          ))
                        ) : (
                          <span className="text-xs text-gray-500">
                            No channels discovered
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-300">
                    {getProjectName(account.project_id)}
                  </td>
                  <td className="px-4 py-3">
                    {account.token_valid ? (
                      <span className="inline-flex items-center gap-1 text-xs text-green-400">
                        <CheckCircle className="w-3 h-3" />
                        Valid
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-red-400">
                        <XCircle className="w-3 h-3" />
                        Invalid
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">
                    {new Date(account.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => syncMutation.mutate(account.id)}
                        disabled={syncMutation.isPending}
                        className="p-1 text-gray-500 hover:text-indigo-400 transition-colors mr-1"
                        title="Re-sync channels"
                      >
                        <RefreshCw
                          className={`w-4 h-4 ${syncMutation.isPending ? 'animate-spin' : ''}`}
                        />
                      </button>
                      {deleteConfirmId === account.id ? (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400">Delete?</span>
                          <button
                            onClick={() => deleteMutation.mutate(account.id)}
                            disabled={deleteMutation.isPending}
                            className="px-2 py-1 bg-red-600 hover:bg-red-500 text-white text-xs rounded transition-colors"
                          >
                            {deleteMutation.isPending
                              ? 'Deleting...'
                              : 'Confirm'}
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(null)}
                            className="px-2 py-1 text-gray-400 hover:text-white text-xs transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setDeleteConfirmId(account.id)}
                          className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                          title="Delete account"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="bg-gray-800 border border-gray-700 border-dashed rounded-lg p-8 text-center">
          <UserCircle className="w-10 h-10 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400 text-sm">
            No Google accounts connected yet
          </p>
          <p className="text-gray-500 text-xs mt-1">
            Add an account to start uploading to YouTube
          </p>
        </div>
      )}
    </div>
  )
}

export default function AccountsPage() {
  return (
    <div className="p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Accounts</h1>
        <p className="text-sm text-gray-400 mt-1">
          Manage GCP projects and YouTube channel accounts
        </p>
      </div>

      <section>
        <ProjectManager />
      </section>

      <hr className="border-gray-700" />

      <section>
        <AccountList />
      </section>

      <hr className="border-gray-700" />

      <section>
        <ChannelLanguagesSection />
      </section>
    </div>
  )
}

function ChannelLanguagesSection() {
  const queryClient = useQueryClient()
  const [banner, setBanner] = useState<AutoDetectResponse | null>(null)
  const [tagsBanner, setTagsBanner] = useState<PullYoutubeTagsAllResponse | null>(null)

  const { data: channels = [] } = useQuery<Channel[]>({
    queryKey: ['channels'],
    queryFn: getChannels,
  })

  const unsetCount = channels.filter((ch) => !ch.language_code).length
  const nothingToDo = unsetCount === 0

  const mutation = useMutation({
    mutationFn: autoDetectChannelLanguages,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['channels'] })
      setBanner(data)
    },
  })

  const pullTagsMutation = useMutation({
    mutationFn: pullYoutubeTagsForAll,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['channels'] })
      setTagsBanner(data)
    },
  })

  // Auto-clear the success banner after 6s.
  useEffect(() => {
    if (!banner) return
    const t = setTimeout(() => setBanner(null), 6000)
    return () => clearTimeout(t)
  }, [banner])

  useEffect(() => {
    if (!tagsBanner) return
    const t = setTimeout(() => setTagsBanner(null), 6000)
    return () => clearTimeout(t)
  }, [tagsBanner])

  const isDisabled = mutation.isPending || nothingToDo
  const enabledClasses =
    'bg-amber-600 hover:bg-amber-500 text-white'
  const disabledClasses =
    'bg-gray-700 text-gray-500 cursor-not-allowed'

  const tooltip = nothingToDo
    ? 'Todos os canais já têm idioma'
    : 'Detectar idioma de canais sem idioma definido'

  const pullTagsDisabled = pullTagsMutation.isPending || channels.length === 0
  const pullTagsTooltip = channels.length === 0
    ? 'Nenhum canal disponível'
    : 'Puxar tags padrão (brandingSettings.keywords) de todos os canais'

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">
            Channel Languages
          </h2>
          <p className="text-sm text-gray-400">
            Assign a language to each channel for automatic metadata
            translation
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={isDisabled}
            title={tooltip}
            className={`text-xs font-medium px-2.5 py-1 rounded-lg flex items-center gap-1.5 transition-colors ${
              isDisabled ? disabledClasses : enabledClasses
            }`}
          >
            {mutation.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Wand2 className="w-3.5 h-3.5" />
            )}
            Detectar idiomas
          </button>
          <button
            type="button"
            onClick={() => pullTagsMutation.mutate()}
            disabled={pullTagsDisabled}
            title={pullTagsTooltip}
            className={`text-xs font-medium px-2.5 py-1 rounded-lg flex items-center gap-1.5 transition-colors ${
              pullTagsDisabled ? disabledClasses : enabledClasses
            }`}
          >
            {pullTagsMutation.isPending ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Tag className="w-3.5 h-3.5" />
            )}
            Puxar tags de todos
          </button>
        </div>
      </div>
      {banner && (
        <div className="bg-emerald-900/30 border border-emerald-800 text-emerald-200 text-xs px-3 py-2 rounded">
          {banner.updated} canais atualizados, {banner.skipped_unknown} sem
          idioma detectável.
        </div>
      )}
      {tagsBanner && (
        <div className="bg-emerald-900/30 border border-emerald-800 text-emerald-200 text-xs px-3 py-2 rounded">
          {tagsBanner.updated} canais atualizados, {tagsBanner.failed} falharam.
        </div>
      )}
      <ChannelGrid />
    </div>
  )
}
