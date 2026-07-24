'use client'

import { memo } from 'react'
import { Trash2 } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SourceListResponse } from '@/lib/types/api'
import { cn } from '@/lib/utils'
import { getSourceDisplayIcon } from '@/lib/utils/source-icons'
import type { Locale } from 'date-fns'

export interface SourcesTableRowProps {
  source: SourceListResponse
  index: number
  isSelected: boolean
  dateLocale: Locale
  typeLinkLabel: string
  typeFileLabel: string
  typeTextLabel: string
  untitledLabel: string
  yesLabel: string
  noLabel: string
  deleteLabel: string
  onRowClick: (index: number, sourceId: string) => void
  onMouseEnter: (index: number) => void
  onDeleteClick: (e: React.MouseEvent, source: SourceListResponse) => void
  measureRef?: (node: HTMLTableRowElement | null) => void
  dataIndex?: number
}

function SourcesTableRowImpl({
  source,
  index,
  isSelected,
  dateLocale,
  typeLinkLabel,
  typeFileLabel,
  typeTextLabel,
  untitledLabel,
  yesLabel,
  noLabel,
  deleteLabel,
  onRowClick,
  onMouseEnter,
  onDeleteClick,
  measureRef,
  dataIndex,
}: SourcesTableRowProps) {
  const { Icon: SourceIcon, className: sourceIconClassName } =
    getSourceDisplayIcon(source)

  const typeLabel = source.asset?.url
    ? typeLinkLabel
    : source.asset?.file_path
      ? typeFileLabel
      : typeTextLabel

  return (
    <tr
      ref={measureRef}
      data-index={dataIndex ?? index}
      data-source-row
      onClick={() => onRowClick(index, source.id)}
      onMouseEnter={() => onMouseEnter(index)}
      className={cn(
        'cursor-pointer border-b transition-colors',
        isSelected ? 'bg-accent' : 'hover:bg-muted/50'
      )}
    >
      <td className="h-9 px-3">
        <div className="flex items-center gap-2">
          <SourceIcon
            className={cn(
              'h-3.5 w-3.5 text-muted-foreground',
              sourceIconClassName
            )}
          />
          <Badge variant="secondary" className="text-[11px]">
            {typeLabel}
          </Badge>
        </div>
      </td>
      <td className="h-9 px-3">
        <div className="flex flex-col overflow-hidden">
          <span className="truncate text-sm font-medium leading-snug">{source.title || untitledLabel}</span>
          {source.asset?.url && (
            <span className="truncate text-[11px] leading-tight text-muted-foreground">{source.asset.url}</span>
          )}
        </div>
      </td>
      <td className="hidden h-9 px-3 text-xs text-muted-foreground sm:table-cell">
        {formatDistanceToNow(new Date(source.created), {
          addSuffix: true,
          locale: dateLocale,
        })}
      </td>
      <td className="hidden h-9 px-3 text-center lg:table-cell">
        <Badge variant={source.embedded ? 'default' : 'secondary'} className="text-[11px]">
          {source.embedded ? yesLabel : noLabel}
        </Badge>
      </td>
      <td className="h-9 px-3 text-right">
        <Button
          variant="ghost"
          size="icon"
          onClick={(e) => onDeleteClick(e, source)}
          className="h-7 w-7 text-destructive hover:text-destructive"
          aria-label={deleteLabel}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </td>
    </tr>
  )
}

function areEqual(prev: SourcesTableRowProps, next: SourcesTableRowProps) {
  return (
    prev.source.id === next.source.id &&
    prev.source.title === next.source.title &&
    prev.source.updated === next.source.updated &&
    prev.source.embedded === next.source.embedded &&
    prev.source.asset?.file_path === next.source.asset?.file_path &&
    prev.source.asset?.url === next.source.asset?.url &&
    prev.isSelected === next.isSelected &&
    prev.index === next.index
  )
}

export const SourcesTableRow = memo(SourcesTableRowImpl, areEqual)
