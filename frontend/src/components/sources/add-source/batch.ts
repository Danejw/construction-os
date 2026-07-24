import { MAX_BATCH_SIZE } from '@/components/sources/add-source/schema'

export function normalizeSelectedFiles(files: File[]): File[] {
  return files.filter((file) => file.size >= 0)
}

export function isWithinBatchLimit(files: File[]): boolean {
  return files.length > 0 && files.length <= MAX_BATCH_SIZE
}
