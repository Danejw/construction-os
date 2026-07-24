'use client'

import { Search, SlidersHorizontal, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { useTranslation } from '@/lib/hooks/use-translation'
import {
  DEFAULT_SOURCE_LIST_FILTERS,
  isSourceListFilterActive,
  type SourceKind,
  type SourceListFilterState,
  type StageFilter,
} from '@/lib/utils/source-filters'
import { cn } from '@/lib/utils'

type SourcesFilterBarProps = {
  filters: SourceListFilterState
  onChange: (next: SourceListFilterState) => void
  extensions: string[]
  className?: string
}

function stageLabel(
  value: StageFilter,
  t: (key: string) => string
): string {
  switch (value) {
    case 'complete':
      return t('sources.filterStageComplete')
    case 'incomplete':
      return t('sources.filterStageIncomplete')
    default:
      return t('sources.filterStageAny')
  }
}

export function SourcesFilterBar({
  filters,
  onChange,
  extensions,
  className,
}: SourcesFilterBarProps) {
  const { t } = useTranslation()
  const active = isSourceListFilterActive(filters)

  const patch = (partial: Partial<SourceListFilterState>) => {
    onChange({ ...filters, ...partial })
  }

  return (
    <div
      className={cn(
        'flex shrink-0 flex-wrap items-center gap-0.5 px-1.5 py-0.5',
        className
      )}
    >
      <div className="relative min-w-[8rem] flex-1">
        <Search className="pointer-events-none absolute left-1.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={filters.query}
          onChange={(event) => patch({ query: event.target.value })}
          placeholder={t('sources.filterByName')}
          className="h-7 pl-7 text-xs"
          aria-label={t('sources.filterByName')}
        />
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant={
              filters.kind !== 'all' || filters.extension ? 'secondary' : 'ghost'
            }
            size="sm"
            className="h-7 shrink-0"
          >
            {t('common.type')}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuLabel>{t('common.type')}</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={filters.kind}
            onValueChange={(value) =>
              patch({
                kind: value as 'all' | SourceKind,
                extension: value === 'upload' ? filters.extension : '',
              })
            }
          >
            <DropdownMenuRadioItem value="all">
              {t('sources.filterTypeAll')}
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="upload">
              {t('sources.type.file')}
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="link">
              {t('sources.type.link')}
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="text">
              {t('sources.type.text')}
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>

          {extensions.length > 0 ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>{t('sources.filterFileType')}</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={filters.extension || 'all'}
                onValueChange={(value) =>
                  patch({
                    extension: value === 'all' ? '' : value,
                    kind: value === 'all' ? filters.kind : 'upload',
                  })
                }
              >
                <DropdownMenuRadioItem value="all">
                  {t('sources.filterExtensionAll')}
                </DropdownMenuRadioItem>
                {extensions.map((ext) => (
                  <DropdownMenuRadioItem key={ext} value={ext}>
                    .{ext}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant={
              filters.embedding !== 'any' ||
              filters.knowledgeGraph !== 'any' ||
              filters.drawing !== 'any'
                ? 'secondary'
                : 'ghost'
            }
            size="sm"
            className="h-7 shrink-0 gap-1"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            {t('sources.filterProcess')}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuLabel>{t('sources.filterEmbedding')}</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={filters.embedding}
            onValueChange={(value) =>
              patch({ embedding: value as StageFilter })
            }
          >
            {(['any', 'complete', 'incomplete'] as const).map((value) => (
              <DropdownMenuRadioItem key={value} value={value}>
                {stageLabel(value, t)}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>

          <DropdownMenuSeparator />
          <DropdownMenuLabel>{t('sources.filterKnowledgeGraph')}</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={filters.knowledgeGraph}
            onValueChange={(value) =>
              patch({ knowledgeGraph: value as StageFilter })
            }
          >
            {(['any', 'complete', 'incomplete'] as const).map((value) => (
              <DropdownMenuRadioItem key={value} value={value}>
                {stageLabel(value, t)}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>

          <DropdownMenuSeparator />
          <DropdownMenuLabel>{t('sources.filterDrawing')}</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={filters.drawing}
            onValueChange={(value) => patch({ drawing: value as StageFilter })}
          >
            {(['any', 'complete', 'incomplete'] as const).map((value) => (
              <DropdownMenuRadioItem key={value} value={value}>
                {stageLabel(value, t)}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      {active ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 shrink-0 px-1.5"
          title={t('sources.filterClear')}
          onClick={() => onChange(DEFAULT_SOURCE_LIST_FILTERS)}
        >
          <X className="h-3.5 w-3.5" />
          <span className="sr-only">{t('sources.filterClear')}</span>
        </Button>
      ) : null}
    </div>
  )
}
