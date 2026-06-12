import { useState, useRef, useEffect } from 'react'
import { useDroppable } from '@dnd-kit/core'
import { SortableContext, useSortable, rectSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Trash2 } from 'lucide-react'
import SortableChannelCard from './SortableChannelCard'
import type { Channel, ChannelGroup } from '../../types'

interface ChannelGroupContainerProps {
  group: ChannelGroup
  channels: Channel[]
  selectedIds: Set<number>
  onToggle: (id: number) => void
  onToggleGroup: (groupId: number, select: boolean) => void
  onRename: (groupId: number, name: string) => void
  onDelete: (groupId: number) => void
}

export default function ChannelGroupContainer({
  group,
  channels,
  selectedIds,
  onToggle,
  onToggleGroup,
  onRename,
  onDelete,
}: ChannelGroupContainerProps) {
  const [editingName, setEditingName] = useState(false)
  const [nameValue, setNameValue] = useState(group.name)
  const nameInputRef = useRef<HTMLInputElement>(null)
  const checkboxRef = useRef<HTMLInputElement>(null)

  // Sortable for the group header (drag handle reorders groups)
  const {
    attributes,
    listeners,
    setNodeRef: setSortableRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: `group-${group.id}`,
    data: { type: 'group', groupId: group.id },
  })

  // Droppable for the group body — drop channels into this group
  const { setNodeRef: setDroppableRef, isOver } = useDroppable({
    id: `group-body-${group.id}`,
    data: { type: 'group-body', groupId: group.id },
  })

  // Tri-state logic
  const memberIds = channels.map((c) => c.id)
  const selectedCount = memberIds.filter((id) => selectedIds.has(id)).length
  const allSelected = memberIds.length > 0 && selectedCount === memberIds.length
  const someSelected = selectedCount > 0 && selectedCount < memberIds.length

  useEffect(() => {
    if (checkboxRef.current) {
      checkboxRef.current.indeterminate = someSelected
    }
  }, [someSelected])

  useEffect(() => {
    if (editingName) {
      nameInputRef.current?.focus()
      nameInputRef.current?.select()
    }
  }, [editingName])

  useEffect(() => {
    setNameValue(group.name)
  }, [group.name])

  const commitName = () => {
    const trimmed = nameValue.trim()
    if (trimmed.length > 0 && trimmed !== group.name) {
      onRename(group.id, trimmed)
    } else {
      setNameValue(group.name)
    }
    setEditingName(false)
  }

  const cancelName = () => {
    setNameValue(group.name)
    setEditingName(false)
  }

  const handleDelete = () => {
    if (window.confirm(`Apagar grupo ${group.name}?`)) {
      onDelete(group.id)
    }
  }

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div
      ref={setSortableRef}
      style={style}
      className={`border rounded-lg p-3 transition-colors ${
        isOver ? 'border-indigo-500 bg-indigo-500/5' : 'border-gray-700 bg-gray-800/40'
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <input
          ref={checkboxRef}
          type="checkbox"
          checked={allSelected}
          onChange={() => onToggleGroup(group.id, !allSelected)}
          className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-indigo-500 focus:ring-indigo-500"
        />

        {editingName ? (
          <input
            ref={nameInputRef}
            type="text"
            value={nameValue}
            onChange={(e) => setNameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                commitName()
              } else if (e.key === 'Escape') {
                e.preventDefault()
                cancelName()
              }
            }}
            onBlur={cancelName}
            className="bg-gray-700 border border-indigo-500 text-white text-sm font-semibold rounded px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        ) : (
          <button
            type="button"
            onClick={() => setEditingName(true)}
            className="text-sm font-semibold text-white hover:text-indigo-300 transition-colors"
          >
            {group.name}
          </button>
        )}

        <span className="text-xs text-gray-400">
          · {channels.length} {channels.length === 1 ? 'channel' : 'channels'}
        </span>

        <div className="flex-1" />

        <button
          type="button"
          onClick={handleDelete}
          title="Delete group"
          className="text-gray-400 hover:text-red-400 transition-colors p-1"
        >
          <Trash2 className="w-4 h-4" />
        </button>

        <button
          type="button"
          {...attributes}
          {...listeners}
          title="Drag to reorder group"
          className="text-gray-400 hover:text-white cursor-grab active:cursor-grabbing p-1"
        >
          <GripVertical className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div
        ref={setDroppableRef}
        className="min-h-[80px]"
      >
        <SortableContext
          id={`group-${group.id}`}
          items={channels.map((c) => `channel-${c.id}`)}
          strategy={rectSortingStrategy}
        >
          {channels.length === 0 ? (
            <div className="text-xs text-gray-500 italic py-6 text-center">
              Drop channels here
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
              {channels.map((ch) => (
                <SortableChannelCard
                  key={ch.id}
                  channel={ch}
                  groupId={group.id}
                  selectable
                  selected={selectedIds.has(ch.id)}
                  onToggle={onToggle}
                />
              ))}
            </div>
          )}
        </SortableContext>
      </div>
    </div>
  )
}
