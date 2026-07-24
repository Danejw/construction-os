'use client'

import { useId } from 'react'
import { cn } from '@/lib/utils'

interface AnimatedBrandLogoProps {
  className?: string
  /** Pixel size — defaults to chat activity row size. */
  size?: number
  title?: string
}

/**
 * Animated Construction OS mark (hard hat + building) for live loading states.
 * Wordmark omitted so it stays readable at 16–24px.
 */
export function AnimatedBrandLogo({
  className,
  size = 16,
  title = 'Construction OS',
}: AnimatedBrandLogoProps) {
  const rawId = useId().replace(/:/g, '')
  const helmetGradient = `brand-helmet-${rawId}`
  const buildingGradient = `brand-building-${rawId}`

  return (
    <svg
      width={size}
      height={size}
      viewBox="48 68 144 126"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label={title}
      className={cn('brand-logo-loader shrink-0', className)}
    >
      <title>{title}</title>
      <defs>
        <linearGradient
          id={helmetGradient}
          x1="0%"
          y1="0%"
          x2="100%"
          y2="100%"
        >
          <stop offset="0%" stopColor="#F59E0B" />
          <stop offset="100%" stopColor="#D97706" />
        </linearGradient>
        <linearGradient
          id={buildingGradient}
          x1="0%"
          y1="100%"
          x2="0%"
          y2="0%"
        >
          <stop offset="0%" stopColor="#1E3A8A" />
          <stop offset="100%" stopColor="#2563EB" />
        </linearGradient>
      </defs>

      <g className="brand-logo-loader__building">
        <rect
          x="72"
          y="118"
          width="96"
          height="72"
          rx="4"
          fill={`url(#${buildingGradient})`}
        />
        <rect
          className="brand-logo-loader__window"
          x="88"
          y="134"
          width="16"
          height="16"
          rx="2"
          fill="#93C5FD"
        />
        <rect
          className="brand-logo-loader__window"
          x="112"
          y="134"
          width="16"
          height="16"
          rx="2"
          fill="#93C5FD"
          style={{ animationDelay: '0.12s' }}
        />
        <rect
          className="brand-logo-loader__window"
          x="136"
          y="134"
          width="16"
          height="16"
          rx="2"
          fill="#93C5FD"
          style={{ animationDelay: '0.24s' }}
        />
        <rect
          className="brand-logo-loader__window"
          x="88"
          y="158"
          width="16"
          height="16"
          rx="2"
          fill="#93C5FD"
          style={{ animationDelay: '0.18s' }}
        />
        <rect
          className="brand-logo-loader__window"
          x="112"
          y="158"
          width="16"
          height="16"
          rx="2"
          fill="#93C5FD"
          style={{ animationDelay: '0.3s' }}
        />
        <rect
          className="brand-logo-loader__window"
          x="136"
          y="158"
          width="16"
          height="16"
          rx="2"
          fill="#93C5FD"
          style={{ animationDelay: '0.42s' }}
        />
        <rect x="108" y="174" width="24" height="16" rx="2" fill="#1E40AF" />
      </g>

      <g className="brand-logo-loader__helmet">
        <path
          d="M60 118C60 96 88 82 120 82C152 82 180 96 180 118H60Z"
          fill={`url(#${helmetGradient})`}
        />
        <path
          d="M54 118H186C188 118 190 120 190 122V128C190 130 188 132 186 132H54C52 132 50 130 50 128V122C50 120 52 118 54 118Z"
          fill="#B45309"
        />
        <rect x="112" y="70" width="16" height="14" rx="3" fill="#FBBF24" />
      </g>
    </svg>
  )
}
