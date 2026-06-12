import { useState, useRef, useLayoutEffect, ReactNode } from 'react'

interface ErrorTooltipProps {
  message: string
  children: ReactNode
}

export function ErrorTooltip({ message, children }: ErrorTooltipProps) {
  const [visible, setVisible] = useState(false)
  const [placeAbove, setPlaceAbove] = useState(true)
  const anchorRef = useRef<HTMLSpanElement>(null)

  useLayoutEffect(() => {
    if (!visible || !anchorRef.current) return
    const rect = anchorRef.current.getBoundingClientRect()
    // If anchor is too close to top of viewport, flip below
    setPlaceAbove(rect.top > 80)
  }, [visible])

  return (
    <span
      ref={anchorRef}
      style={{ position: 'relative', display: 'inline-block' }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span
          role="tooltip"
          style={{
            position: 'absolute',
            left: '50%',
            transform: 'translateX(-50%)',
            [placeAbove ? 'bottom' : 'top']: 'calc(100% + 8px)',
            background: '#0f172a',
            border: '1px solid #ef4444',
            color: '#fecaca',
            padding: '8px 12px',
            borderRadius: 8,
            fontSize: 12,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            boxShadow: '0 8px 24px rgba(0,0,0,.5)',
            zIndex: 50,
            whiteSpace: 'normal',
            maxWidth: 360,
            minWidth: 'max-content',
            wordBreak: 'break-word',
            pointerEvents: 'none',
          }}
        >
          {message}
          <span
            style={{
              position: 'absolute',
              left: '50%',
              [placeAbove ? 'bottom' : 'top']: -6,
              transform: 'translateX(-50%) rotate(45deg)',
              width: 10,
              height: 10,
              background: '#0f172a',
              [placeAbove ? 'borderRight' : 'borderLeft']: '1px solid #ef4444',
              [placeAbove ? 'borderBottom' : 'borderTop']: '1px solid #ef4444',
            }}
          />
        </span>
      )}
    </span>
  )
}
