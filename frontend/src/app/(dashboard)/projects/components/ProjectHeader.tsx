'use client'

import { useState, type ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ProjectResponse } from '@/lib/types/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Archive, ArchiveRestore, Bot, Link2, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { useUpdateProject } from '@/lib/hooks/use-projects'
import { ProjectDeleteDialog } from './ProjectDeleteDialog'
import { InlineEdit } from '@/components/common/InlineEdit'
import { useTranslation } from '@/lib/hooks/use-translation'

interface ProjectHeaderProps {
  project: ProjectResponse
  /** Optional extra actions rendered before Archive/Delete. */
  actions?: ReactNode
}

export function ProjectHeader({ project, actions }: ProjectHeaderProps) {
  const { t } = useTranslation()
  const pathname = usePathname()
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [copyingLink, setCopyingLink] = useState(false)

  const updateProject = useUpdateProject()
  const isOperatorPage = pathname?.endsWith('/operator') ?? false

  const handleUpdateName = async (name: string) => {
    if (!name || name === project.name) return

    await updateProject.mutateAsync({
      id: project.id,
      data: { name },
    })
  }

  const handleArchiveToggle = () => {
    updateProject.mutate({
      id: project.id,
      data: { archived: !project.archived },
    })
  }

  const handleCopyShareLink = async () => {
    if (typeof window === 'undefined' || !project.id) return

    const shareUrl = `${window.location.origin}/share/projects/${encodeURIComponent(project.id)}/chat`
    setCopyingLink(true)
    try {
      await navigator.clipboard.writeText(shareUrl)
      toast.success(t('share.linkCopied'))
    } catch {
      toast.error(t('share.linkCopyFailed'))
    } finally {
      setCopyingLink(false)
    }
  }

  return (
    <>
      <div className="py-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1 space-y-0.5">
            <div className="flex min-w-0 items-center gap-2">
              <InlineEdit
                id="project-name"
                name="project-name"
                value={project.name}
                onSave={handleUpdateName}
                className="min-w-0 flex-1 truncate break-normal text-base font-semibold leading-snug"
                inputClassName="text-base font-semibold"
                placeholder={t('projects.namePlaceholder')}
              />
              {project.archived ? (
                <Badge variant="secondary" className="h-5 shrink-0 px-1.5 text-[10px]">
                  {t('projects.archived')}
                </Badge>
              ) : null}
            </div>
          </div>

          <div className="flex shrink-0 flex-nowrap items-center gap-1">
            {actions}
            {!isOperatorPage ? (
              <Button asChild variant="outline" size="sm" className="h-7 px-2 text-xs">
                <Link href={`/projects/${encodeURIComponent(project.id)}/operator`}>
                  <Bot className="h-3.5 w-3.5 sm:mr-1.5" />
                  <span className="hidden sm:inline">Operator</span>
                </Link>
              </Button>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => {
                void handleCopyShareLink()
              }}
              disabled={copyingLink}
              title={t('share.copyLink')}
            >
              <Link2 className="h-3.5 w-3.5 sm:mr-1.5" />
              <span className="hidden sm:inline">{t('share.copyLink')}</span>
            </Button>
            <Button variant="outline" size="sm" className="h-7 px-2 text-xs" onClick={handleArchiveToggle}>
              {project.archived ? (
                <>
                  <ArchiveRestore className="h-3.5 w-3.5 sm:mr-1.5" />
                  <span className="hidden sm:inline">{t('projects.unarchive')}</span>
                </>
              ) : (
                <>
                  <Archive className="h-3.5 w-3.5 sm:mr-1.5" />
                  <span className="hidden sm:inline">{t('projects.archive')}</span>
                </>
              )}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs text-destructive hover:text-destructive"
              onClick={() => setShowDeleteDialog(true)}
            >
              <Trash2 className="h-3.5 w-3.5 sm:mr-1.5" />
              <span className="hidden sm:inline">{t('common.delete')}</span>
            </Button>
          </div>
        </div>
      </div>

      <ProjectDeleteDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        projectId={project.id}
        projectName={project.name}
        redirectAfterDelete
      />
    </>
  )
}
