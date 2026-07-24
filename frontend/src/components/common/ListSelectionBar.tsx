'use client'

import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

interface ListSelectionBarProps {
  count: number
  countLabel: string
  onClear: () => void
  onSelectAll?: () => void
  className?: string
  children?: ReactNode
}

export function ListSelectionBar({
  count,
  countLabel,
  onClear,
  onSelectAll,
  className,
  children,
}: ListSelectionBarProps) {
  const { t } = useTranslation()

  return (
    <div
      className={cn(
        'sticky top-0 z-20 mt-1 mb-0.5 flex h-8 min-w-0 items-center gap-0.5 overflow-x-auto rounded-md border bg-muted/80 px-0.5 backdrop-blur',
        className
      )}
      role="toolbar"
      aria-label={countLabel}
    >
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-7 shrink-0"
        onClick={onClear}
        aria-label={t('common.clearSelection')}
        title={t('common.clearSelection')}
      >
        <X className="size-3.5" />
      </Button>
      <span className="shrink-0 truncate text-[11px] font-medium tabular-nums text-foreground">
        {countLabel}
      </span>
      <div className="ml-auto flex shrink-0 items-center gap-0.5">
        {onSelectAll ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 shrink-0 px-1.5 text-[11px]"
            onClick={onSelectAll}
          >
            {t('common.selectAll')}
          </Button>
        ) : null}
        {children}
      </div>
    </div>
  )
}
