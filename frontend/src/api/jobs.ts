import type { JobSummary, JobDetail } from '../types'

export async function getRecentJobs(limit = 10): Promise<JobSummary[]> {
  const r = await fetch(`/api/uploads/jobs/recent?limit=${limit}`)
  if (!r.ok) throw new Error('Failed to load recent jobs')
  return r.json()
}

export async function getJob(jobId: string): Promise<JobDetail> {
  const r = await fetch(`/api/uploads/job/${encodeURIComponent(jobId)}`)
  if (!r.ok) throw new Error('Failed to load job')
  return r.json()
}
