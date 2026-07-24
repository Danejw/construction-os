'use client'

import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  columnHeaderIconButtonClassName,
  columnHeaderIconClassName,
  columnHeaderPrimaryButtonClassName,
} from '@/components/projects/ColumnHeader'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'

export interface SourcesColumnAddMenuProps {
  onAddSource: () => void
  /** Compact icon trigger for graph header. */
  variant?: 'primary' | 'icon'
}

export function SourcesColumnAddMenu({
  onAddSource,
  variant = 'primary',
}: SourcesColumnAddMenuProps) {
  const { t } = useTranslation()

  if (variant === 'icon') {
    return (
      <Button
        type="button"
        size="icon"
        variant="outline"
        className={cn(
          columnHeaderIconButtonClassName,
          'border bg-background/80 shadow-sm backdrop-blur-sm'
        )}
        aria-label={t('sources.addSource')}
        title={t('sources.addSource')}
        onClick={onAddSource}
      >
        <Plus className={columnHeaderIconClassName} />
      </Button>
    )
  }

  return (
    <Button
      type="button"
      size="sm"
      className={columnHeaderPrimaryButtonClassName}
      onClick={onAddSource}
    >
      <Plus className={columnHeaderIconClassName} />
      {t('sources.addSource')}
    </Button>
  )
}
