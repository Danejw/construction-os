import { describe, expect, it } from 'vitest'
import type { SourceListResponse } from '@/lib/types/api'
import {
  File,
  FileImage,
  FileSpreadsheet,
  FileText,
  ExternalLink,
} from 'lucide-react'
import {
  PdfFileIcon,
  getSourceDisplayIcon,
  resolveSourceFileExtension,
} from '@/lib/utils/source-icons'

function source(
  overrides: Partial<SourceListResponse> & Pick<SourceListResponse, 'id'>
): SourceListResponse {
  return {
    title: 'Untitled',
    topics: [],
    asset: null,
    embedded: false,
    embedded_chunks: 0,
    created: '2026-01-01T00:00:00Z',
    updated: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('source-icons', () => {
  it('resolves pdf from path or title and uses the PDF glyph', () => {
    expect(
      resolveSourceFileExtension(
        source({ id: '1', asset: { file_path: 'notes/Page_A701.PDF' } })
      )
    ).toBe('pdf')
    expect(
      resolveSourceFileExtension(
        source({ id: '2', title: 'Page_008_P204.pdf' })
      )
    ).toBe('pdf')

    const fromPath = getSourceDisplayIcon(
      source({ id: '3', asset: { file_path: 'a.pdf' } })
    )
    expect(fromPath.Icon).toBe(PdfFileIcon)
    expect(fromPath.className).toContain('text-red-500')
  })

  it('maps other extensions and source kinds', () => {
    expect(
      getSourceDisplayIcon(
        source({ id: 'img', asset: { file_path: 'plan.png' } })
      ).Icon
    ).toBe(FileImage)
    expect(
      getSourceDisplayIcon(
        source({ id: 'sheet', asset: { file_path: 'takeoff.xlsx' } })
      ).Icon
    ).toBe(FileSpreadsheet)
    expect(
      getSourceDisplayIcon(
        source({ id: 'unknown', asset: { file_path: 'blob.bin' } })
      ).Icon
    ).toBe(File)
    expect(
      getSourceDisplayIcon(
        source({ id: 'link', asset: { url: 'https://example.com' } })
      ).Icon
    ).toBe(ExternalLink)
    expect(getSourceDisplayIcon(source({ id: 'text' })).Icon).toBe(FileText)
  })
})
