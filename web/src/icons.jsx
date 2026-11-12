import React from 'react'

// Petites icônes au trait (16 px), dessinées à la main pour rester légères.
const Svg = ({ children, size = 16, ...p }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}>{children}</svg>
)

export const Play = (p) => <Svg {...p}><path d="M4.6 3.1v9.8c0 .5.5.8.9.5l7.4-4.9c.4-.2.4-.8 0-1L5.5 2.6c-.4-.3-.9 0-.9.5Z" fill="currentColor" stroke="none" /></Svg>
export const Pause = (p) => <Svg {...p}><rect x="4" y="3" width="2.6" height="10" rx=".8" fill="currentColor" stroke="none" /><rect x="9.4" y="3" width="2.6" height="10" rx=".8" fill="currentColor" stroke="none" /></Svg>
export const Folder = (p) => <Svg {...p}><path d="M2 4.5c0-.6.4-1 1-1h3.3l1.4 1.6H13c.6 0 1 .4 1 1v6.4c0 .6-.4 1-1 1H3c-.6 0-1-.4-1-1Z" /></Svg>
export const Replace = (p) => <Svg {...p}><path d="M13 6.5A5 5 0 0 0 3.6 5M3 9.5A5 5 0 0 0 12.4 11" /><path d="M3.3 2.5v2.8h2.8M12.7 13.5v-2.8H9.9" /></Svg>
export const Trash = (p) => <Svg {...p}><path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.3c0 .4.4.7.8.7h4.2c.4 0 .8-.3.8-.7l.6-8.3" /></Svg>
export const Upload = (p) => <Svg {...p}><path d="M8 10.5V2.8M5 5.5l3-3 3 3M2.8 10v2.2c0 .6.4 1 1 1h8.4c.6 0 1-.4 1-1V10" /></Svg>
export const Search = (p) => <Svg {...p}><circle cx="7" cy="7" r="4.3" /><path d="m10.3 10.3 3.2 3.2" /></Svg>
export const Gear = (p) => <Svg {...p}><circle cx="8" cy="8" r="2" /><path d="M8 1.8v1.6M8 12.6v1.6M14.2 8h-1.6M3.4 8H1.8M12.4 3.6l-1.1 1.1M4.7 11.3l-1.1 1.1M12.4 12.4l-1.1-1.1M4.7 4.7 3.6 3.6" /></Svg>
export const Help = (p) => <Svg {...p}><circle cx="8" cy="8" r="6" /><path d="M6.4 6.3a1.7 1.7 0 0 1 3.3.5c0 1.1-1.7 1.4-1.7 2.4" /><circle cx="8" cy="11.4" r=".4" fill="currentColor" /></Svg>
export const Check = (p) => <Svg {...p}><path d="m3.5 8.5 3 3 6-6.5" /></Svg>
export const Close = (p) => <Svg {...p}><path d="m4 4 8 8M12 4l-8 8" /></Svg>
export const Download = (p) => <Svg {...p}><path d="M8 2.5v7.7M5 7.5l3 3 3-3M2.8 10v2.2c0 .6.4 1 1 1h8.4c.6 0 1-.4 1-1V10" /></Svg>
export const Import = (p) => <Svg {...p}><path d="M8 2.5v7.7M5 7.5l3 3 3-3M2.8 10v2.2c0 .6.4 1 1 1h8.4c.6 0 1-.4 1-1V10" /></Svg>
export const Logo = (p) => (
  <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" {...p}>
    <rect width="22" height="22" rx="6" fill="var(--accent)" />
    <path d="M6 13V9M9 16V6M12 14V8M15 12.5v-3" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
)

// Petit égaliseur animé pour la ligne en cours de lecture
export const Bars = () => (
  <span className="eq" aria-hidden="true"><i /><i /><i /></span>
)
