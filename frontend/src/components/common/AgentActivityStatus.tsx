'use client'

import { AnimatedBrandLogo } from '@/components/common/AnimatedBrandLogo'
import { cn } from '@/lib/utils'

interface AgentActivityStatusProps {
  streamStatus?: string | null
  activityLog?: string[]
  className?: string
}

/**
 * Live agent status + compact completed-step log for the current turn.
 * Flat text — no chat-bubble chrome.
 */
export function AgentActivityStatus({
  streamStatus,
  activityLog = [],
  className,
}: AgentActivityStatusProps) {
  if (!streamStatus && activityLog.length === 0) {
    return null
  }

  return (
    <div className={cn('flex justify-start', className)}>
      <div className="w-full max-w-[min(100%,52rem)] space-y-1.5 text-sm text-muted-foreground">
        {activityLog.length > 0 && (
          <ul className="space-y-0.5 text-[12px] leading-snug">
            {activityLog.map((line, index) => (
              <li key={`${index}-${line}`} className="flex gap-1.5">
                <span className="text-muted-foreground/70" aria-hidden>
                  ✓
                </span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
        )}
        {streamStatus ? (
          <div className="flex items-center gap-2">
            <AnimatedBrandLogo size={18} />
            <span>{streamStatus}</span>
          </div>
        ) : null}
      </div>
    </div>
  )
}
