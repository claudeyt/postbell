import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import ChannelCard from './ChannelCard'
import type { Channel } from '../../types'

interface SortableChannelCardProps {
  channel: Channel
  groupId: number | null
  selectable?: boolean
  selected?: boolean
  onToggle?: (id: number) => void
}

export default function SortableChannelCard({
  channel,
  groupId,
  selectable,
  selected,
  onToggle,
}: SortableChannelCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({
      id: `channel-${channel.id}`,
      data: { type: 'channel', channelId: channel.id, groupId },
    })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <ChannelCard
        channel={channel}
        selectable={selectable}
        selected={selected}
        onSelect={onToggle}
      />
    </div>
  )
}
