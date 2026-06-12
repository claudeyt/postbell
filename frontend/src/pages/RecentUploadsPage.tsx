import { useCallback, useState } from 'react'
import RecentJobsStrip from '../components/upload/RecentJobsStrip'
import JobHeader from '../components/upload/JobHeader'
import UploadProgress from '../components/upload/UploadProgress'
import { useJob } from '../hooks/useJob'

const LAST_JOB_KEY = 'postbell:lastJobId'

export default function RecentUploadsPage() {
  // Selected job (for the recent-jobs strip / resumed view).
  // Initialized from localStorage so a refresh auto-restores the last job —
  // including jobs started on the Dashboard (the live-upload flow there
  // still writes activeJobId into this same key on start).
  const [selectedJobId, setSelectedJobId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(LAST_JOB_KEY)
    } catch {
      return null
    }
  })
  const selectedJob = useJob(selectedJobId)

  const handleSelectJob = useCallback((jobId: string) => {
    setSelectedJobId(jobId)
    try {
      localStorage.setItem(LAST_JOB_KEY, jobId)
    } catch {
      // ignore
    }
  }, [])

  const handleDismissJob = useCallback(() => {
    setSelectedJobId(null)
    try {
      localStorage.removeItem(LAST_JOB_KEY)
    } catch {
      // ignore
    }
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Uploads recentes</h1>
        <p className="text-sm text-gray-400 mt-1">
          Volte a qualquer upload em andamento ou já concluído.
        </p>
      </div>

      <RecentJobsStrip
        selectedJobId={selectedJobId}
        onSelect={handleSelectJob}
      />

      {selectedJobId && selectedJob.progress && selectedJob.summary && (
        <section className="space-y-3">
          <JobHeader
            summary={{
              total: selectedJob.summary.total,
              completed: selectedJob.summary.completed,
              failed: selectedJob.summary.failed,
              in_flight: selectedJob.summary.in_flight,
              started_at: selectedJob.jobStartedAt,
              status: selectedJob.summary.status,
            }}
            onRefresh={selectedJob.refetch}
            onDismiss={handleDismissJob}
          />
          <UploadProgress progress={selectedJob.progress} />
        </section>
      )}

      {selectedJobId && !selectedJob.progress && !selectedJob.isLoading && (
        <p className="text-sm text-gray-500">
          Nenhum dado disponível para esse upload.
        </p>
      )}

      {!selectedJobId && (
        <p className="text-sm text-gray-500">
          Selecione um upload acima para ver os detalhes.
        </p>
      )}
    </div>
  )
}
