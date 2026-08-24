import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'lifeledger_mobile_mode'

/**
 * Detects mobile viewport and manages a manual mobile/desktop toggle.
 *
 * Auto-detects mobile when viewport ≤ 768 px wide.
 * User can override with the toggle button — preference is stored in
 * localStorage so it persists across sessions.
 *
 * @returns { isMobile, isManualOverride, toggleMobileView }
 */
export function useMobileView() {
  const getInitialMode = () => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored !== null) return stored === 'true'
    return window.innerWidth <= 768
  }

  const [isMobile, setIsMobile] = useState(getInitialMode)
  const [isManualOverride, setIsManualOverride] = useState(
    () => localStorage.getItem(STORAGE_KEY) !== null
  )

  // Listen to viewport changes — only auto-switch if user hasn't overridden
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const handler = (e: MediaQueryListEvent) => {
      if (!isManualOverride) setIsMobile(e.matches)
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [isManualOverride])

  const toggleMobileView = useCallback(() => {
    setIsMobile(prev => {
      const next = !prev
      localStorage.setItem(STORAGE_KEY, String(next))
      setIsManualOverride(true)
      return next
    })
  }, [])

  const resetToAuto = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY)
    setIsManualOverride(false)
    setIsMobile(window.innerWidth <= 768)
  }, [])

  return { isMobile, isManualOverride, toggleMobileView, resetToAuto }
}
