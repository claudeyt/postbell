import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { getRecentJobs } from '../../api/jobs'
import JobChip from './JobChip'

interface RecentJobsStripProps {
  selectedJobId: string | null
  onSelect: (jobId: string) => void
}

export default function RecentJobsStrip({
  selectedJobId,
  onSelect,
}: RecentJobsStripProps) {
  const { data: jobs = [] } = useQuery({
    queryKey: ['recentJobs'],
    queryFn: () => getRecentJobs(5),
    refetchInterval: 15_000,
  })

  if (jobs.length === 0) return null

  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-1">
      {jobs.map(job => (
        <JobChip
          key={job.job_id}
          summary={job}
          selected={job.job_id === selectedJobId}
          onClick={() => onSelect(job.job_id)}
        />
      ))}
      <Link
        to="/history"
        className="ml-auto shrink-0 flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors px-2"
      >
        Ver tudo
        <ArrowRight className="w-3 h-3" />
      </Link>
    </div>
  )
}
