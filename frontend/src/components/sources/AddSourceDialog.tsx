'use client'

import { useCallback, useMemo } from 'react'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { SourceFileDropZone } from '@/components/sources/add-source/SourceFileDropZone'
import {
  isWithinBatchLimit,
  normalizeSelectedFiles,
} from '@/components/sources/add-source/batch'
import { MAX_BATCH_SIZE } from '@/components/sources/add-source/schema'
import { submitUploadFiles } from '@/components/sources/add-source/submit'
import { useCreateSource } from '@/lib/hooks/use-sources'
import { useTranslation } from '@/lib/hooks/use-translation'

interface AddSourceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultprojectId?: string
}

export function AddSourceDialog({
  open,
  onOpenChange,
  defaultprojectId,
}: AddSourceDialogProps) {
  const { t } = useTranslation()
  const createSource = useCreateSource()

  const projectIds = useMemo(
    () => (defaultprojectId ? [defaultprojectId] : []),
    [defaultprojectId]
  )

  const handleClose = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  const handleFiles = useCallback(
    (selected: File[]) => {
      const files = normalizeSelectedFiles(selected)
      if (files.length === 0) return

      if (!isWithinBatchLimit(files)) {
        toast.error(
          t('sources.maxFilesAllowed').replace('{count}', MAX_BATCH_SIZE.toString())
        )
        return
      }

      // Close immediately — each upload appears as a list item via optimistic cache.
      onOpenChange(false)

      void (async () => {
        try {
          const results = await submitUploadFiles({
            files,
            projectIds,
            createSource,
          })

          if (files.length > 1) {
            if (results.failed === 0) {
              toast.success(
                t('sources.batchSuccess').replace(
                  '{count}',
                  results.success.toString()
                )
              )
            } else if (results.success === 0) {
              toast.error(
                t('sources.batchFailed').replace(
                  '{count}',
                  results.failed.toString()
                )
              )
            } else {
              toast.warning(
                t('sources.batchPartial')
                  .replace('{success}', results.success.toString())
                  .replace('{failed}', results.failed.toString())
              )
            }
          }
        } catch (error) {
          console.error('Error creating sources:', error)
          toast.error(t('sources.failedToAddSource'))
        }
      })()
    },
    [createSource, onOpenChange, projectIds, t]
  )

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) handleClose()
      }}
    >
      <DialogContent className="max-h-[70vh]">
        <DialogHeader>
          <DialogTitle>{t('sources.addNew')}</DialogTitle>
        </DialogHeader>

        <div className="min-w-0 px-0.5">
          <SourceFileDropZone onFiles={handleFiles} />
        </div>

        <DialogFooter className="justify-start sm:justify-start">
          <Button type="button" variant="outline" onClick={handleClose}>
            {t('common.cancel')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
