import { useState, useRef, useEffect } from 'react'
import { Plus } from 'lucide-react'

interface NewGroupButtonProps {
  onCreate: (name: string) => void
  disabled?: boolean
}

export default function NewGroupButton({ onCreate, disabled }: NewGroupButtonProps) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus()
    }
  }, [editing])

  const cancel = () => {
    setEditing(false)
    setValue('')
  }

  const commit = () => {
    const trimmed = value.trim()
    if (trimmed.length > 0) {
      onCreate(trimmed)
    }
    setEditing(false)
    setValue('')
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            commit()
          } else if (e.key === 'Escape') {
            e.preventDefault()
            cancel()
          }
        }}
        onBlur={cancel}
        placeholder="Group name"
        className="bg-gray-800 border border-indigo-500 text-white text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
    )
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      disabled={disabled}
      className="flex items-center gap-1.5 px-3 py-1.5 border border-dashed border-gray-600 hover:border-indigo-500 text-gray-300 hover:text-white text-sm rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <Plus className="w-4 h-4" />
      Novo grupo
    </button>
  )
}
