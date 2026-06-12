import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, FolderOpen, Loader2, Upload, CheckCircle } from 'lucide-react'
import { getProjects, createProject, deleteProject, uploadClientSecret } from '../../api/projects'
import type { Project } from '../../types'

export default function ProjectManager() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [clientSecretPath, setClientSecretPath] = useState('')
  const [dailyQuotaLimit, setDailyQuotaLimit] = useState('10000')
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [secretFile, setSecretFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)

  const {
    data: projects,
    isLoading,
    error: fetchError,
  } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: getProjects,
  })

  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setShowForm(false)
      resetForm()
    },
    onError: (err: Error) => {
      setFormError(err.message)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setDeleteConfirmId(null)
    },
  })

  function resetForm() {
    setName('')
    setClientSecretPath('')
    setDailyQuotaLimit('10000')
    setFormError(null)
    setSecretFile(null)
  }

  async function handleSecretFile(file: File) {
    setUploading(true)
    setFormError(null)
    try {
      const result = await uploadClientSecret(file)
      setClientSecretPath(result.path)
      setSecretFile(file)
    } catch (err: any) {
      setFormError(err.message || 'Failed to upload client secret')
    } finally {
      setUploading(false)
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)

    if (!name.trim()) {
      setFormError('Project name is required')
      return
    }
    if (!clientSecretPath.trim()) {
      setFormError('Please upload a client secret file')
      return
    }

    const quota = parseInt(dailyQuotaLimit, 10)
    if (isNaN(quota) || quota <= 0) {
      setFormError('Daily quota limit must be a positive number')
      return
    }

    createMutation.mutate({
      name: name.trim(),
      client_secret_path: clientSecretPath.trim(),
      daily_quota_limit: quota,
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 py-8">
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading projects...
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
        Failed to load projects: {fetchError.message}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">GCP Projects</h2>
          <p className="text-sm text-gray-400">
            Register Google Cloud projects to authenticate YouTube accounts
          </p>
        </div>
        <button
          onClick={() => {
            setShowForm(!showForm)
            if (!showForm) resetForm()
          }}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Project
        </button>
      </div>

      {/* Add Project Form */}
      {showForm && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-5">
          <h3 className="text-sm font-semibold text-white mb-4">
            New GCP Project
          </h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="project-name"
                className="block text-sm text-gray-300 mb-1"
              >
                Project Name
              </label>
              <input
                id="project-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. My YouTube Project"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-300 mb-1">
                Client Secret File
              </label>
              {clientSecretPath ? (
                <div className="flex items-center gap-3 bg-gray-900 border border-gray-700 rounded-lg px-4 py-3">
                  <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-white truncate">{secretFile?.name || 'client_secret.json'}</p>
                    <p className="text-xs text-gray-500 truncate">{clientSecretPath}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => { setClientSecretPath(''); setSecretFile(null) }}
                    className="text-gray-500 hover:text-white text-xs transition-colors"
                  >
                    Change
                  </button>
                </div>
              ) : (
                <div
                  onDragOver={(e) => { e.preventDefault(); e.stopPropagation() }}
                  onDrop={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    const file = e.dataTransfer.files[0]
                    if (file) handleSecretFile(file)
                  }}
                  onClick={() => {
                    const input = document.createElement('input')
                    input.type = 'file'
                    input.accept = '.json'
                    input.onchange = (e) => {
                      const file = (e.target as HTMLInputElement).files?.[0]
                      if (file) handleSecretFile(file)
                    }
                    input.click()
                  }}
                  className="w-full bg-gray-900 border-2 border-dashed border-gray-700 hover:border-indigo-500 rounded-lg px-4 py-6 text-center cursor-pointer transition-colors"
                >
                  {uploading ? (
                    <div className="flex items-center justify-center gap-2 text-gray-400">
                      <Loader2 className="w-5 h-5 animate-spin" />
                      <span className="text-sm">Uploading...</span>
                    </div>
                  ) : (
                    <>
                      <Upload className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                      <p className="text-sm text-gray-400">
                        Drag & drop your <span className="text-white font-medium">client_secret.json</span> here
                      </p>
                      <p className="text-xs text-gray-500 mt-1">or click to browse</p>
                    </>
                  )}
                </div>
              )}
              <p className="text-xs text-gray-500 mt-1">
                The OAuth client_secret.json downloaded from Google Cloud Console
              </p>
            </div>

            <div>
              <label
                htmlFor="daily-quota"
                className="block text-sm text-gray-300 mb-1"
              >
                Daily Quota Limit
              </label>
              <input
                id="daily-quota"
                type="number"
                value={dailyQuotaLimit}
                onChange={(e) => setDailyQuotaLimit(e.target.value)}
                min="1"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-500 mt-1">
                YouTube Data API v3 default quota is 10,000 units/day
              </p>
            </div>

            {formError && (
              <div className="bg-red-900/30 border border-red-700 rounded-lg px-3 py-2 text-sm text-red-300">
                {formError}
              </div>
            )}

            <div className="flex items-center gap-3 pt-1">
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
              >
                {createMutation.isPending && (
                  <Loader2 className="w-4 h-4 animate-spin" />
                )}
                {createMutation.isPending ? 'Creating...' : 'Create Project'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowForm(false)
                  resetForm()
                }}
                className="px-4 py-2 text-gray-400 hover:text-white text-sm font-medium transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Projects Table */}
      {projects && projects.length > 0 ? (
        <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">
                  Name
                </th>
                <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">
                  Client Secret Path
                </th>
                <th className="text-left text-xs font-medium text-gray-400 uppercase tracking-wider px-4 py-3">
                  Quota Limit
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
              {projects.map((project) => (
                <tr key={project.id} className="hover:bg-gray-750">
                  <td className="px-4 py-3 text-sm text-white font-medium">
                    {project.name}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-300 font-mono text-xs max-w-xs truncate">
                    {project.client_secret_path}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-300">
                    {project.daily_quota_limit.toLocaleString()} units/day
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">
                    {new Date(project.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {deleteConfirmId === project.id ? (
                      <div className="flex items-center justify-end gap-2">
                        <span className="text-xs text-gray-400">Delete?</span>
                        <button
                          onClick={() => deleteMutation.mutate(project.id)}
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
                        onClick={() => setDeleteConfirmId(project.id)}
                        className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                        title="Delete project"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="bg-gray-800 border border-gray-700 border-dashed rounded-lg p-8 text-center">
          <FolderOpen className="w-10 h-10 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400 text-sm">
            No GCP projects registered yet
          </p>
          <p className="text-gray-500 text-xs mt-1">
            Add a project to start authenticating YouTube accounts
          </p>
        </div>
      )}
    </div>
  )
}
