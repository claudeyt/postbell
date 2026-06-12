import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { LayoutDashboard, Users, History, Inbox, BarChart3, Settings } from 'lucide-react'
import { getQuotaSummary } from '../../api/quota'
import QuotaBar from '../common/QuotaBar'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/accounts', label: 'Accounts', icon: Users },
  { to: '/history', label: 'History', icon: History },
  { to: '/uploads-recent', label: 'Uploads recentes', icon: Inbox },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar() {
  const { data: quotaData } = useQuery({
    queryKey: ['quota', 'summary'],
    queryFn: getQuotaSummary,
    refetchInterval: 60_000,
  })

  return (
    <aside className="w-64 shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col min-h-screen">
      <div className="h-16 flex items-center px-6 border-b border-gray-800">
        <span className="text-xl font-bold text-white tracking-tight">
          Postbell
        </span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`
            }
          >
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}
      </nav>

      {quotaData && quotaData.projects.length > 0 && (
        <div className="px-4 py-3 border-t border-gray-800 space-y-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            API Quota Today
          </p>
          {quotaData.projects.map(item => (
            <div key={item.project_id} className="space-y-2">
              <QuotaBar
                projectName={item.project_name}
                label="Vídeos hoje"
                used={item.videos_today}
                limit={item.video_limit}
              />
            </div>
          ))}
        </div>
      )}

      <div className="px-6 py-4 border-t border-gray-800">
        <p className="text-xs text-gray-500">Postbell v0.1.0</p>
      </div>
    </aside>
  )
}
