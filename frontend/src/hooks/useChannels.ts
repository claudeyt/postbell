import { useQuery } from '@tanstack/react-query'
import { getChannels } from '../api/channels'

export function useChannels() {
  return useQuery({
    queryKey: ['channels'],
    queryFn: getChannels,
  })
}
