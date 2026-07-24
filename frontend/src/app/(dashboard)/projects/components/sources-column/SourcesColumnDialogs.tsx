'use client'

import { AddSourceDialog } from '@/components/sources/AddSourceDialog'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { useTranslation } from '@/lib/hooks/use-translation'

export interface SourcesColumnDialogsProps {
  projectId: string
  addDialogOpen: boolean
  onAddDialogOpenChange: (open: boolean) => void
  deleteDialogOpen: boolean
  onDeleteDialogOpenChange: (open: boolean) => void
  onDeleteConfirm: () => void | Promise<void>
  deleteLoading: boolean
  removeDialogOpen: boolean
  onRemoveDialogOpenChange: (open: boolean) => void
  onRemoveConfirm: () => void | Promise<void>
  removeLoading: boolean
  bulkDeleteOpen: boolean
  onBulkDeleteOpenChange: (open: boolean) => void
  onBulkDeleteConfirm: () => void | Promise<void>
  bulkRemoveOpen: boolean
  onBulkRemoveOpenChange: (open: boolean) => void
  onBulkRemoveConfirm: () => void | Promise<void>
  bulkBusy: boolean
}

export function SourcesColumnDialogs({
  projectId,
  addDialogOpen,
  onAddDialogOpenChange,
  deleteDialogOpen,
  onDeleteDialogOpenChange,
  onDeleteConfirm,
  deleteLoading,
  removeDialogOpen,
  onRemoveDialogOpenChange,
  onRemoveConfirm,
  removeLoading,
  bulkDeleteOpen,
  onBulkDeleteOpenChange,
  onBulkDeleteConfirm,
  bulkRemoveOpen,
  onBulkRemoveOpenChange,
  onBulkRemoveConfirm,
  bulkBusy,
}: SourcesColumnDialogsProps) {
  const { t } = useTranslation()

  return (
    <>
      <AddSourceDialog
        open={addDialogOpen}
        onOpenChange={onAddDialogOpenChange}
        defaultprojectId={projectId}
      />

      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={onDeleteDialogOpenChange}
        title={t('sources.delete')}
        description={t('sources.deleteConfirm')}
        confirmText={t('common.delete')}
        onConfirm={onDeleteConfirm}
        isLoading={deleteLoading}
        confirmVariant="destructive"
      />

      <ConfirmDialog
        open={removeDialogOpen}
        onOpenChange={onRemoveDialogOpenChange}
        title={t('sources.removeFromProject')}
        description={t('sources.removeConfirm')}
        confirmText={t('common.remove')}
        onConfirm={onRemoveConfirm}
        isLoading={removeLoading}
        confirmVariant="default"
      />

      <ConfirmDialog
        open={bulkDeleteOpen}
        onOpenChange={onBulkDeleteOpenChange}
        title={t('sources.delete')}
        description={t('sources.deleteConfirm')}
        confirmText={t('common.delete')}
        onConfirm={onBulkDeleteConfirm}
        isLoading={bulkBusy}
        confirmVariant="destructive"
      />

      <ConfirmDialog
        open={bulkRemoveOpen}
        onOpenChange={onBulkRemoveOpenChange}
        title={t('sources.removeFromProject')}
        description={t('sources.removeConfirm')}
        confirmText={t('common.remove')}
        onConfirm={onBulkRemoveConfirm}
        isLoading={bulkBusy}
        confirmVariant="default"
      />
    </>
  )
}
