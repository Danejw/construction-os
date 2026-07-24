import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'
import { enUS } from './en-US'
import { zhCN } from './zh-CN'
import { zhTW } from './zh-TW'
import { ptBR } from './pt-BR'
import { jaJP } from './ja-JP'
import { itIT } from './it-IT'
import { frFR } from './fr-FR'
import { ruRU } from './ru-RU'
import { bnIN } from './bn-IN'
import { caES } from './ca-ES'
import { esES } from './es-ES'
import { deDE } from './de-DE'
import { plPL } from './pl-PL'
import { trTR } from './tr-TR'

const allLocales = {
  'zh-CN': zhCN,
  'zh-TW': zhTW,
  'pt-BR': ptBR,
  'ja-JP': jaJP,
  'it-IT': itIT,
  'fr-FR': frFR,
  'ru-RU': ruRU,
  'bn-IN': bnIN,
  'ca-ES': caES,
  'es-ES': esES,
  'de-DE': deDE,
  'pl-PL': plPL,
  'tr-TR': trTR,
} as const

const getKeys = (obj: Record<string, unknown>, prefix = ''): string[] => {
  return Object.keys(obj).reduce((res: string[], el) => {
    const val = obj[el]
    if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
      return [...res, ...getKeys(val as Record<string, unknown>, prefix + el + '.')]
    }
    return [...res, prefix + el]
  }, [])
}

describe('Locale Parity', () => {
  const enKeys = getKeys(enUS)

  const locales = Object.entries(allLocales)

  it.each(locales.map(([code, translation]) => [code, translation] as const))(
    '%s should have the same keys as en-US',
    (code, translation) => {
      const localeKeys = getKeys(translation as Record<string, unknown>)

      const missing = enKeys.filter(key => !localeKeys.includes(key))
      const extra = localeKeys.filter(key => !enKeys.includes(key))

      expect(missing, `Missing keys in ${code}: ${missing.join(', ')}`).toEqual([])
      expect(extra, `Extra keys in ${code}: ${extra.join(', ')}`).toEqual([])
    },
  )
})

describe('Unused Key Detection', () => {
  // Keys with these prefixes are composed dynamically at runtime via template
  // literals (e.g. `tools.risk.${level}`) and cannot be detected by a static
  // string search.  Add a prefix here only when you can confirm the pattern in
  // source code.
  const DYNAMIC_KEY_PREFIXES = [
    'agentSteps.',        // agentStepI18nKey() → `agentSteps.${stepName}`
    'tools.risk.',        // t(`tools.risk.${tool.risk_level}`)
    'tools.status.',      // t(`tools.status.${connection.status}`)
    'tools.toolCallStatus.', // t(`tools.toolCallStatus.${toolCall.status}`)
    'projects.artifactPhases.', // t(`projects.artifactPhases.${phase}`)
    'companyProfile.source.', // t(`companyProfile.source.${profile.source}`)
  ]

  it(
    'all en-US leaf keys should be referenced in source files',
    () => {
      // Scan application source only — not frontend/.next or other build output.
      const srcDir = path.resolve(__dirname, '../..')
      const localesDir = path.resolve(__dirname)

      const files = fs.readdirSync(srcDir, { recursive: true }) as string[]
      const sourceFiles = files.filter(f => {
        const full = path.join(srcDir, f)
        if (full.startsWith(localesDir)) return false
        if (f.endsWith('.test.ts') || f.endsWith('.test.tsx')) return false
        return f.endsWith('.ts') || f.endsWith('.tsx')
      })

      const corpus = sourceFiles
        .map(f => fs.readFileSync(path.join(srcDir, f), 'utf-8'))
        .join('\n')
        .replace(/\?\./g, '.')

      const leafKeys = getKeys(enUS)
      const unused = leafKeys.filter(
        key =>
          !corpus.includes(key) &&
          !DYNAMIC_KEY_PREFIXES.some(prefix => key.startsWith(prefix)),
      )

      expect(
        unused,
        `Found ${unused.length} unused i18n key(s):\n${unused.join('\n')}`,
      ).toEqual([])
    },
    30_000,
  )
})
