'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useEpisodeProfiles, useGeneratePodcast } from '@/lib/hooks/use-podcasts'
import { PodcastGenerationRequest } from '@/lib/types/podcasts'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  dialogBodyClassName,
  dialogLargeContentClassName,
} from '@/components/ui/dialog'
import { ContentSelectionPanel } from '@/components/podcasts/generate-podcast/ContentSelectionPanel'
import { EpisodeSettingsPanel } from '@/components/podcasts/generate-podcast/EpisodeSettingsPanel'
import { GeneratePodcastFooter } from '@/components/podcasts/generate-podcast/GeneratePodcastFooter'
import { useGeneratePodcastSelection } from '@/components/podcasts/generate-podcast/useGeneratePodcastSelection'

interface GeneratePodcastDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function GeneratePodcastDialog({
  open,
  onOpenChange,
}: GeneratePodcastDialogProps) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const [episodeProfileId, setEpisodeProfileId] = useState('')
  const [episodeName, setEpisodeName] = useState('')
  const [instructions, setInstructions] = useState('')
  const [isBuildingContext, setIsBuildingContext] = useState(false)

  const episodeProfilesQuery = useEpisodeProfiles()
  const generatePodcast = useGeneratePodcast()
  const episodeProfiles = useMemo(
    () => episodeProfilesQuery.episodeProfiles ?? [],
    [episodeProfilesQuery.episodeProfiles]
  )

  const {
    queryClient,
    projects,
    projectsLoading,
    expandedProjects,
    setExpandedProjects,
    selections,
    sourcesByProject,
    notesByProject,
    fetchingProjectIds,
    tokenCount,
    charCount,
    selectedProjectSummaries,
    handleProjectToggle,
    handleSourceModeChange,
    handleNoteToggle,
    buildContentFromSelections,
    resetSelectionState,
  } = useGeneratePodcastSelection(open)

  const resetState = useCallback(() => {
    resetSelectionState()
    setEpisodeProfileId('')
    setEpisodeName('')
    setInstructions('')
  }, [resetSelectionState])

  useEffect(() => {
    if (!open) {
      resetState()
    }
  }, [open, resetState])

  const selectedEpisodeProfile = useMemo(() => {
    if (!episodeProfileId) {
      return undefined
    }
    return episodeProfiles.find((profile) => profile.id === episodeProfileId)
  }, [episodeProfileId, episodeProfiles])

  const handleSubmit = useCallback(async () => {
    if (!selectedEpisodeProfile) {
      toast({
        title: t('podcasts.profileRequired'),
        description: t('podcasts.profileRequiredDesc'),
        variant: 'destructive',
      })
      return
    }

    if (!episodeName.trim()) {
      toast({
        title: t('podcasts.nameRequired'),
        description: t('podcasts.nameRequiredDesc'),
        variant: 'destructive',
      })
      return
    }

    setIsBuildingContext(true)
    try {
      const content = await buildContentFromSelections()
      if (!content.trim()) {
        toast({
          title: t('podcasts.addContext'),
          description: t('podcasts.addContextDesc'),
          variant: 'destructive',
        })
        return
      }

      const payload: PodcastGenerationRequest = {
        episode_profile: selectedEpisodeProfile.name,
        speaker_profile: selectedEpisodeProfile.speaker_config,
        episode_name: episodeName.trim(),
        content,
        briefing_suffix: instructions.trim() ? instructions.trim() : undefined,
      }

      await generatePodcast.mutateAsync(payload)

      toast({
        title: t('common.success'),
        description: t('podcasts.podcastTaskStarted'),
      })

      setTimeout(() => {
        onOpenChange(false)
        resetState()
      }, 500)
    } catch (error) {
      console.error('Failed to generate podcast', error)
      toast({
        title: t('podcasts.generationFailed'),
        description:
          error instanceof Error ? error.message : t('common.refreshPage'),
        variant: 'destructive',
      })
    } finally {
      setIsBuildingContext(false)
    }
  }, [
    buildContentFromSelections,
    episodeName,
    generatePodcast,
    instructions,
    onOpenChange,
    resetState,
    selectedEpisodeProfile,
    toast,
    t,
  ])

  const isSubmitting = generatePodcast.isPending || isBuildingContext

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        onOpenChange(value)
        if (!value) {
          resetState()
        }
      }}
    >
      <DialogContent
        className={cn(dialogLargeContentClassName, 'overflow-hidden')}
      >
        <DialogHeader>
          <DialogTitle>{t('podcasts.generateEpisode')}</DialogTitle>
        </DialogHeader>

        <div
          className={cn(
            dialogBodyClassName,
            'grid gap-3 md:grid-cols-[2fr_1fr] xl:grid-cols-[3fr_1fr]'
          )}
        >
          <ContentSelectionPanel
            projects={projects}
            isLoading={projectsLoading}
            selectedProjectSummaries={selectedProjectSummaries}
            tokenCount={tokenCount}
            charCount={charCount}
            expandedProjects={expandedProjects}
            setExpandedProjects={setExpandedProjects}
            selections={selections}
            sourcesByProject={sourcesByProject}
            notesByProject={notesByProject}
            fetchingProjectIds={fetchingProjectIds}
            handleProjectToggle={handleProjectToggle}
            handleSourceModeChange={handleSourceModeChange}
            handleNoteToggle={handleNoteToggle}
            queryClient={queryClient}
          />

          <div className="space-y-6">
            <EpisodeSettingsPanel
              isLoading={episodeProfilesQuery.isLoading}
              episodeProfiles={episodeProfiles}
              episodeProfileId={episodeProfileId}
              onEpisodeProfileIdChange={setEpisodeProfileId}
              selectedEpisodeProfile={selectedEpisodeProfile}
              episodeName={episodeName}
              onEpisodeNameChange={setEpisodeName}
              instructions={instructions}
              onInstructionsChange={setInstructions}
            />
            <GeneratePodcastFooter
              isSubmitting={isSubmitting}
              onSubmit={() => void handleSubmit()}
              onCancel={() => onOpenChange(false)}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
