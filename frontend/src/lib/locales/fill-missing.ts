/**
 * Ensure a locale object has exactly the same key shape as en-US.
 * Overlay values win when present; missing leaves fall back to English.
 * Keys present only in the overlay are dropped (keeps parity tests honest).
 */
export function fillMissingKeys<T extends Record<string, unknown>>(
  base: T,
  overlay: Record<string, unknown>,
): T {
  const result: Record<string, unknown> = {}
  for (const key of Object.keys(base)) {
    const baseVal = base[key as keyof T]
    const overVal = overlay[key]
    if (
      typeof baseVal === 'object' &&
      baseVal !== null &&
      !Array.isArray(baseVal)
    ) {
      const childOverlay =
        typeof overVal === 'object' &&
        overVal !== null &&
        !Array.isArray(overVal)
          ? (overVal as Record<string, unknown>)
          : {}
      result[key] = fillMissingKeys(
        baseVal as Record<string, unknown>,
        childOverlay,
      )
    } else {
      result[key] = overVal !== undefined ? overVal : baseVal
    }
  }
  return result as T
}
