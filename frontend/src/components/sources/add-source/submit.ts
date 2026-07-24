import type { CreateSourceRequest } from '@/lib/types/api'

type UploadSourceRequest = CreateSourceRequest & { file: File }

interface CreateSourceMutation {
  mutateAsync: (data: UploadSourceRequest) => Promise<unknown>
}

function buildUploadRequest(
  file: File,
  projectIds: string[]
): UploadSourceRequest {
  return {
    type: 'upload',
    title: file.name,
    projects: projectIds,
    embed: true,
    delete_source: false,
    async_processing: true,
    file,
  }
}

export async function submitUploadFiles(params: {
  files: File[]
  projectIds: string[]
  createSource: CreateSourceMutation
}): Promise<{ success: number; failed: number }> {
  const { files, projectIds, createSource } = params

  const settled = await Promise.allSettled(
    files.map((file) =>
      createSource.mutateAsync(buildUploadRequest(file, projectIds))
    )
  )

  let success = 0
  let failed = 0
  for (const result of settled) {
    if (result.status === 'fulfilled') {
      success++
    } else {
      failed++
      console.error('Error creating source:', result.reason)
    }
  }

  return { success, failed }
}
