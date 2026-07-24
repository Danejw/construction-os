'use client'

import {
  useCallback,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type KeyboardEvent,
} from 'react'
import { UploadIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'
import { SOURCE_FILE_ACCEPT } from '@/components/sources/add-source/schema'

export interface SourceFileDropZoneProps {
  disabled?: boolean
  onFiles: (files: File[]) => void
}

function filesFromDataTransfer(dataTransfer: DataTransfer): File[] {
  return Array.from(dataTransfer.files)
}

export function SourceFileDropZone({
  disabled = false,
  onFiles,
}: SourceFileDropZoneProps) {
  const { t } = useTranslation()
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const dragDepthRef = useRef(0)

  const emitFiles = useCallback(
    (files: File[]) => {
      if (disabled || files.length === 0) return
      onFiles(files)
    },
    [disabled, onFiles]
  )

  const openPicker = () => {
    if (disabled) return
    inputRef.current?.click()
  }

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (disabled) return
    dragDepthRef.current += 1
    setIsDragging(true)
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
    if (dragDepthRef.current === 0) {
      setIsDragging(false)
    }
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    dragDepthRef.current = 0
    setIsDragging(false)
    emitFiles(filesFromDataTransfer(event.dataTransfer))
  }

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const list = event.target.files
    if (!list || list.length === 0) return
    emitFiles(Array.from(list))
    event.target.value = ''
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      openPicker()
    }
  }

  return (
    <div className="flex flex-col gap-0.5">
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        multiple
        accept={SOURCE_FILE_ACCEPT}
        className="sr-only"
        disabled={disabled}
        onChange={handleInputChange}
      />

      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-controls={inputId}
        aria-disabled={disabled}
        aria-label={t('sources.dropFilesHere')}
        onClick={openPicker}
        onKeyDown={handleKeyDown}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        className={cn(
          'flex min-h-40 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed px-3 py-6 text-center outline-none transition-colors',
          'focus-visible:ring-1 focus-visible:ring-ring',
          isDragging
            ? 'border-primary bg-primary/5'
            : 'border-border bg-muted/30 hover:border-primary/50 hover:bg-muted/50',
          disabled && 'pointer-events-none opacity-50'
        )}
      >
        <UploadIcon className="size-8 text-muted-foreground" aria-hidden />
        <p className="text-sm font-medium text-foreground">
          {t('sources.dropFilesHere')}
        </p>
        <p className="max-w-sm text-[11px] leading-snug text-muted-foreground">
          {t('sources.selectMultipleFilesHint')}
        </p>
      </div>
    </div>
  )
}
