import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000, // 10 minutes
      retry: 2,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 1,
    },
  },
})

export const QUERY_KEYS = {
  projects: ['projects'] as const,
  project: (id: string) => ['projects', id] as const,
  artifacts: ['artifacts'] as const,
  artifact: (id: string) => ['artifacts', id] as const,
  artifactDefaultPrompt: ['artifacts', 'default-prompt'] as const,
  projectArtifacts: (projectId?: string) => ['projectArtifacts', projectId] as const,
  projectArtifact: (id: string) => ['projectArtifacts', id] as const,
  artifactReview: (noteId: string) => ['artifactReview', noteId] as const,
  projectMemory: (projectId: string) => ['projectMemory', projectId] as const,
  sources: (projectId?: string) => ['sources', projectId] as const,
  sourcesInfinite: (projectId: string) => ['sources', 'infinite', projectId] as const,
  sourcesAllInfinite: (sortBy: string, sortOrder: string) =>
    ['sources', 'all', sortBy, sortOrder] as const,
  source: (id: string) => ['sources', id] as const,
  settings: ['settings'] as const,
  projectChatSessions: (projectId: string, guestKey?: string | null) =>
    ['project-chat', projectId, 'sessions', guestKey ?? 'owner'] as const,
  projectChatSession: (sessionId: string, guestKey?: string | null) =>
    ['project-chat', 'sessions', sessionId, guestKey ?? 'owner'] as const,
  chatQueue: (sessionId: string) => ['chat-queue', sessionId] as const,
  podcastEpisodes: ['podcasts', 'episodes'] as const,
  podcastEpisode: (episodeId: string) => ['podcasts', 'episodes', episodeId] as const,
  episodeProfiles: ['podcasts', 'episode-profiles'] as const,
  speakerProfiles: ['podcasts', 'speaker-profiles'] as const,
  languages: ['languages'] as const,
  skills: ['skills'] as const,
  skill: (id: string) => ['skills', id] as const,
  skillsCatalog: ['skills', 'catalog'] as const,
  collections: ['collections'] as const,
  collection: (id: string) => ['collections', id] as const,
  collectionsCatalog: ['collections', 'catalog'] as const,
  mcpConnections: ['mcp', 'connections'] as const,
  mcpConnection: (id: string) => ['mcp', 'connections', id] as const,
  mcpConnectionTools: (id: string) => ['mcp', 'connections', id, 'tools'] as const,
  mcpSelectableTools: ['mcp', 'tools', 'selectable'] as const,
  mcpSessionToolCalls: (sessionId: string) => ['mcp', 'sessions', sessionId, 'tool-calls'] as const,
  htmlTemplates: ['html-templates'] as const,
  htmlTemplate: (id: string) => ['html-templates', id] as const,
  mediaAssets: ['media-assets'] as const,
  projectDocuments: (projectId: string) => ['documents', 'project', projectId] as const,
  bidDocument: (id: string) => ['documents', id] as const,
}
