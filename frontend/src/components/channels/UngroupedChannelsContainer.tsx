import { useDroppable } from '@dnd-kit/core'
import { SortableContext, rectSortingStrategy } from '@dnd-kit/sortable'
import SortableChannelCard from './SortableChannelCard'
import type { Channel } from '../../types'

interface UngroupedChannelsContainerProps {
  channels: Channel[]
  selectedIds: Set<number>
  onToggle: (id: number) => void
}

export default function UngroupedChannelsContainer({
  channels,
  selectedIds,
  onToggle,
}: UngroupedChannelsContainerProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: 'group-body-ungrouped',
    data: { type: 'group-body', groupId: null },
  })

  return (
    <div
      ref={setNodeRef}
      className={`rounded-lg p-3 transition-colors ${
        isOver ? 'bg-indigo-500/5 ring-1 ring-indigo-500' : ''
      }`}
    >
      <SortableContext
        id="ungrouped"
        items={channels.map((c) => `channel-${c.id}`)}
        strategy={rectSortingStrategy}
      >
        {channels.length === 0 ? (
          <div className="text-xs text-gray-500 italic py-6 text-center">
            Drop channels here to remove them from groups
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {channels.map((ch) => (
              <SortableChannelCard
                key={ch.id}
                channel={ch}
                groupId={null}
                selectable
                selected={selectedIds.has(ch.id)}
                onToggle={onToggle}
              />
            ))}
          </div>
        )}
      </SortableContext>
    </div>
  )
}
