import { useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { getChannels, moveChannelToGroup, reorderChannels } from '../../api/channels'
import {
  listGroups,
  createGroup,
  updateGroup,
  deleteGroup,
  reorderGroups,
} from '../../api/channelGroups'
import ChannelGroupContainer from './ChannelGroupContainer'
import UngroupedChannelsContainer from './UngroupedChannelsContainer'
import NewGroupButton from './NewGroupButton'
import type { Channel, ChannelGroup } from '../../types'

interface ChannelsSectionProps {
  selectedIds: Set<number>
  onToggle: (id: number) => void
  onToggleMany: (ids: number[], select: boolean) => void
}

type ByGroup = Map<number | null, Channel[]>

function buildByGroup(channels: Channel[]): ByGroup {
  const map: ByGroup = new Map()
  for (const ch of channels) {
    const key = ch.group_id ?? null
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(ch)
  }
  for (const [, list] of map) {
    list.sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0))
  }
  return map
}

export default function ChannelsSection({
  selectedIds,
  onToggle,
  onToggleMany,
}: ChannelsSectionProps) {
  const queryClient = useQueryClient()

  const { data: channels = [], isLoading } = useQuery({
    queryKey: ['channels'],
    queryFn: getChannels,
  })
  const { data: groups = [] } = useQuery({
    queryKey: ['channelGroups'],
    queryFn: listGroups,
  })

  const sortedGroups = useMemo(
    () => [...groups].sort((a, b) => a.display_order - b.display_order),
    [groups],
  )

  const byGroup = useMemo(() => buildByGroup(channels), [channels])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  )

  // ---- Mutations with optimistic updates ----

  const createGroupMutation = useMutation({
    mutationFn: (name: string) => createGroup(name),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['channelGroups'] })
    },
  })

  const deleteGroupMutation = useMutation({
    mutationFn: (id: number) => deleteGroup(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['channelGroups'] })
      await queryClient.cancelQueries({ queryKey: ['channels'] })
      const prevGroups = queryClient.getQueryData<ChannelGroup[]>(['channelGroups'])
      const prevChannels = queryClient.getQueryData<Channel[]>(['channels'])
      queryClient.setQueryData<ChannelGroup[]>(['channelGroups'], (old = []) =>
        old.filter((g) => g.id !== id),
      )
      queryClient.setQueryData<Channel[]>(['channels'], (old = []) =>
        old.map((c) => (c.group_id === id ? { ...c, group_id: null } : c)),
      )
      return { prevGroups, prevChannels }
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prevGroups) queryClient.setQueryData(['channelGroups'], ctx.prevGroups)
      if (ctx?.prevChannels) queryClient.setQueryData(['channels'], ctx.prevChannels)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['channelGroups'] })
      queryClient.invalidateQueries({ queryKey: ['channels'] })
    },
  })

  const renameGroupMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      updateGroup(id, { name }),
    onMutate: async ({ id, name }) => {
      await queryClient.cancelQueries({ queryKey: ['channelGroups'] })
      const prev = queryClient.getQueryData<ChannelGroup[]>(['channelGroups'])
      queryClient.setQueryData<ChannelGroup[]>(['channelGroups'], (old = []) =>
        old.map((g) => (g.id === id ? { ...g, name } : g)),
      )
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['channelGroups'], ctx.prev)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['channelGroups'] })
    },
  })

  const reorderGroupsMutation = useMutation({
    mutationFn: (ids: number[]) => reorderGroups(ids),
    onMutate: async (ids) => {
      await queryClient.cancelQueries({ queryKey: ['channelGroups'] })
      const prev = queryClient.getQueryData<ChannelGroup[]>(['channelGroups'])
      queryClient.setQueryData<ChannelGroup[]>(['channelGroups'], (old = []) => {
        const byId = new Map(old.map((g) => [g.id, g]))
        return ids
          .map((id, idx) => {
            const g = byId.get(id)
            return g ? { ...g, display_order: idx } : null
          })
          .filter((g): g is ChannelGroup => g !== null)
      })
      return { prev }
    },
    onError: (_err, _ids, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['channelGroups'], ctx.prev)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['channelGroups'] })
    },
  })

  const moveChannelMutation = useMutation({
    mutationFn: ({ channelId, groupId }: { channelId: number; groupId: number | null }) =>
      moveChannelToGroup(channelId, groupId),
    onMutate: async ({ channelId, groupId }) => {
      await queryClient.cancelQueries({ queryKey: ['channels'] })
      const prev = queryClient.getQueryData<Channel[]>(['channels'])
      queryClient.setQueryData<Channel[]>(['channels'], (old = []) =>
        old.map((c) => (c.id === channelId ? { ...c, group_id: groupId } : c)),
      )
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['channels'], ctx.prev)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['channels'] })
    },
  })

  const reorderChannelsMutation = useMutation({
    mutationFn: ({ ids, groupId }: { ids: number[]; groupId: number | null }) =>
      reorderChannels(ids, groupId),
    onMutate: async ({ ids, groupId }) => {
      await queryClient.cancelQueries({ queryKey: ['channels'] })
      const prev = queryClient.getQueryData<Channel[]>(['channels'])
      const orderMap = new Map(ids.map((id, idx) => [id, idx]))
      queryClient.setQueryData<Channel[]>(['channels'], (old = []) =>
        old.map((c) =>
          orderMap.has(c.id)
            ? { ...c, group_id: groupId, display_order: orderMap.get(c.id)! }
            : c,
        ),
      )
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['channels'], ctx.prev)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['channels'] })
    },
  })

  // ---- Drag end handler ----

  const handleDragEnd = (e: DragEndEvent) => {
    const { active, over } = e
    if (!over) return
    if (active.id === over.id) return

    const aData = active.data.current as
      | { type: string; channelId?: number; groupId?: number | null }
      | undefined
    const oData = over.data.current as
      | { type: string; channelId?: number; groupId?: number | null }
      | undefined

    if (!aData) return

    // --- Group reorder ---
    if (aData.type === 'group' && oData?.type === 'group') {
      const groupIds = sortedGroups.map((g) => g.id)
      const fromIndex = groupIds.indexOf(aData.groupId as number)
      const toIndex = groupIds.indexOf(oData.groupId as number)
      if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return
      const newIds = arrayMove(groupIds, fromIndex, toIndex)
      reorderGroupsMutation.mutate(newIds)
      return
    }

    // --- Channel move/reorder ---
    if (aData.type === 'channel') {
      const channelId = aData.channelId!
      const fromGroupId = aData.groupId ?? null

      // Determine destination groupId
      let toGroupId: number | null
      if (oData?.type === 'channel') {
        toGroupId = oData.groupId ?? null
      } else if (oData?.type === 'group-body') {
        toGroupId = oData.groupId ?? null
      } else if (oData?.type === 'group') {
        // Dropped on group header — treat as moving into that group
        toGroupId = oData.groupId ?? null
      } else {
        toGroupId = fromGroupId
      }

      const destList = (byGroup.get(toGroupId) ?? []).map((c) => c.id)
      const fromList = (byGroup.get(fromGroupId) ?? []).map((c) => c.id)

      if (toGroupId !== fromGroupId) {
        // Cross-container move
        // Insert at the position of over (if over is a channel) or at end
        let insertIndex = destList.length
        if (oData?.type === 'channel' && oData.channelId !== undefined) {
          const idx = destList.indexOf(oData.channelId)
          if (idx >= 0) insertIndex = idx
        }
        const newDestIds = [...destList]
        newDestIds.splice(insertIndex, 0, channelId)

        moveChannelMutation.mutate(
          { channelId, groupId: toGroupId },
          {
            onSuccess: () => {
              reorderChannelsMutation.mutate({
                ids: newDestIds,
                groupId: toGroupId,
              })
            },
          },
        )
      } else {
        // Same-container reorder
        const fromIndex = fromList.indexOf(channelId)
        let toIndex = fromList.length - 1
        if (oData?.type === 'channel' && oData.channelId !== undefined) {
          toIndex = fromList.indexOf(oData.channelId)
        }
        if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return
        const newIds = arrayMove(fromList, fromIndex, toIndex)
        reorderChannelsMutation.mutate({ ids: newIds, groupId: fromGroupId })
      }
    }
  }

  const handleToggleGroup = (groupId: number, select: boolean) => {
    const memberIds = (byGroup.get(groupId) ?? []).map((c) => c.id)
    onToggleMany(memberIds, select)
  }

  const handleCreateGroup = (name: string) => {
    createGroupMutation.mutate(name)
  }

  const handleRenameGroup = (id: number, name: string) => {
    renameGroupMutation.mutate({ id, name })
  }

  const handleDeleteGroup = (id: number) => {
    deleteGroupMutation.mutate(id)
  }

  const ungrouped = byGroup.get(null) ?? []

  const totalCount = channels.length

  if (isLoading) {
    return <div className="text-gray-400">Loading channels...</div>
  }

  if (channels.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <p>No channels yet. Add a Google account first.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Top control row */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-sm text-gray-400">
          {selectedIds.size} of {totalCount} channels selected
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              const allIds = channels.map((c) => c.id)
              const allSelected = allIds.every((id) => selectedIds.has(id))
              onToggleMany(allIds, !allSelected)
            }}
            className="text-sm text-indigo-400 hover:text-indigo-300"
          >
            {channels.every((c) => selectedIds.has(c.id))
              ? 'Deselect All'
              : 'Select All'}
          </button>
          <NewGroupButton
            onCreate={handleCreateGroup}
            disabled={createGroupMutation.isPending}
          />
        </div>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        {/* Groups list (vertically sortable) */}
        <SortableContext
          id="groups-list"
          items={sortedGroups.map((g) => `group-${g.id}`)}
          strategy={verticalListSortingStrategy}
        >
          <div className="space-y-3">
            {sortedGroups.map((group) => (
              <ChannelGroupContainer
                key={group.id}
                group={group}
                channels={byGroup.get(group.id) ?? []}
                selectedIds={selectedIds}
                onToggle={onToggle}
                onToggleGroup={handleToggleGroup}
                onRename={handleRenameGroup}
                onDelete={handleDeleteGroup}
              />
            ))}
          </div>
        </SortableContext>

        {/* Ungrouped section */}
        <div className="mt-4">
          <UngroupedChannelsContainer
            channels={ungrouped}
            selectedIds={selectedIds}
            onToggle={onToggle}
          />
        </div>
      </DndContext>
    </div>
  )
}
