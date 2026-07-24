import type { ComponentType } from 'react'
import type { LucideProps } from 'lucide-react'
import {
  ExternalLink,
  File,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
} from 'lucide-react'
import type { SourceListResponse } from '@/lib/types/api'
import { getSourceExtension, getSourceKind } from '@/lib/utils/source-filters'

type FileGlyph = ComponentType<LucideProps>

/**
 * Lucide-style PDF glyph (lucide has no dedicated Pdf icon).
 * Document + "PDF" label stays readable at list-row sizes.
 */
export function PdfFileIcon({
  size = 24,
  className,
  ...props
}: LucideProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
      <text
        x="12"
        y="17.5"
        textAnchor="middle"
        fill="currentColor"
        stroke="none"
        fontSize="6"
        fontWeight="700"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
      >
        PDF
      </text>
    </svg>
  )
}

const EXTENSION_ICONS: Record<string, FileGlyph> = {
  pdf: PdfFileIcon,
  doc: FileText,
  docx: FileText,
  rtf: FileText,
  txt: FileText,
  md: FileText,
  markdown: FileText,
  csv: FileSpreadsheet,
  xls: FileSpreadsheet,
  xlsx: FileSpreadsheet,
  ods: FileSpreadsheet,
  png: FileImage,
  jpg: FileImage,
  jpeg: FileImage,
  gif: FileImage,
  webp: FileImage,
  svg: FileImage,
  bmp: FileImage,
  heic: FileImage,
  mp3: FileAudio,
  wav: FileAudio,
  m4a: FileAudio,
  aac: FileAudio,
  flac: FileAudio,
  ogg: FileAudio,
  mp4: FileVideo,
  webm: FileVideo,
  mov: FileVideo,
  mkv: FileVideo,
  avi: FileVideo,
  zip: FileArchive,
  rar: FileArchive,
  '7z': FileArchive,
  tar: FileArchive,
  gz: FileArchive,
  js: FileCode,
  jsx: FileCode,
  ts: FileCode,
  tsx: FileCode,
  py: FileCode,
  json: FileCode,
  html: FileCode,
  css: FileCode,
  xml: FileCode,
  yaml: FileCode,
  yml: FileCode,
}

function extensionFromName(name: string | null | undefined): string | null {
  if (!name) return null
  const base = name.split(/[/\\]/).pop() || name
  const dot = base.lastIndexOf('.')
  if (dot <= 0 || dot === base.length - 1) return null
  return base.slice(dot + 1).toLowerCase()
}

/** Prefer path extension; fall back to title (optimistic rows often only set title). */
export function resolveSourceFileExtension(
  source: SourceListResponse
): string | null {
  return getSourceExtension(source) ?? extensionFromName(source.title)
}

export type SourceDisplayIcon = {
  Icon: FileGlyph
  /** Optional accent (e.g. PDF red) on top of muted list styling. */
  className?: string
}

/**
 * Icon for the sources list / table — specific file type when known,
 * otherwise link / plain-text / generic file.
 */
export function getSourceDisplayIcon(
  source: SourceListResponse
): SourceDisplayIcon {
  const kind = getSourceKind(source)
  if (kind === 'link') {
    return { Icon: ExternalLink }
  }
  if (kind === 'text') {
    return { Icon: FileText }
  }

  const extension = resolveSourceFileExtension(source)
  if (extension) {
    const Icon = EXTENSION_ICONS[extension]
    if (Icon) {
      return {
        Icon,
        className:
          extension === 'pdf' ? 'text-red-500 dark:text-red-400' : undefined,
      }
    }
  }

  return { Icon: File }
}
