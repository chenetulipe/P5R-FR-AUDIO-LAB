import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import * as audio from './audio.js'
import { Play, Pause } from './icons.jsx'

const time = (s) => (s || 0).toFixed(1).replace('.', ',')

let version = 0
audio.subscribe(() => { version++ })
const useAudioVersion = () => useSyncExternalStore(audio.subscribe, () => version)

export default function Player() {
  useAudioVersion()
  const st = audio.snapshot()
  const canvas = useRef(null)
  const timeRef = useRef(null)
  const [hover, setHover] = useState(null)

  // Dessin de l'onde : tourne seulement pendant la lecture
  useEffect(() => {
    let raf
    let colors = null
    const draw = () => {
      const c = canvas.current
      if (!c) return
      const dpr = window.devicePixelRatio || 1
      const W = c.clientWidth, H = c.clientHeight
      if (c.width !== Math.round(W * dpr) || c.height !== Math.round(H * dpr)) {
        c.width = Math.round(W * dpr); c.height = Math.round(H * dpr)
      }
      const g = c.getContext('2d')
      g.setTransform(dpr, 0, 0, dpr, 0, 0)
      g.clearRect(0, 0, W, H)
      if (!colors) {
        const css = getComputedStyle(c)
        colors = { played: css.getPropertyValue('--played').trim(), rest: css.getPropertyValue('--rest').trim() }
      }
      const { played, rest } = colors
      const peaks = st.peaks
      const d = audio.duration()
      const p = d ? audio.position() / d : 0
      const n = peaks.length
      if (n) {
        const gap = 2
        const bw = Math.max(1, W / n - gap)
        for (let i = 0; i < n; i++) {
          const h = Math.max(3, peaks[i] * (H - 2))
          g.fillStyle = (i + 0.5) / n <= p ? played : rest
          const x = i * (W / n)
          const y = (H - h) / 2
          g.beginPath()
          g.roundRect ? g.roundRect(x, y, bw, h, Math.min(bw / 2, 1.5)) : g.rect(x, y, bw, h)
          g.fill()
        }
      } else {
        g.fillStyle = rest
        g.fillRect(0, H / 2 - 0.5, W, 1)
      }
      if (timeRef.current) timeRef.current.textContent = `${time(audio.position())} / ${time(d)} s`
      if (st.playing) raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    const onResize = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(draw) }
    window.addEventListener('resize', onResize)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', onResize) }
  })

  const frac = (e) => {
    const r = e.currentTarget.getBoundingClientRect()
    return (e.clientX - r.left) / r.width
  }
  const meta = st.meta
  const isVf = meta?.kind === 'vf'

  return (
    <footer className={`player ${isVf ? 'is-vf' : ''} ${meta ? 'is-loaded' : ''}`}>
      <button className="player-btn" onClick={audio.toggle} disabled={!st.buffer}
        aria-label={st.playing ? 'Pause' : 'Lecture'}>
        {st.playing ? <Pause /> : <Play />}
      </button>
      <div className="player-label">
        {meta ? (
          <>
            <b>{meta.title}</b>
            <span><i className={`dot ${isVf ? 'dot-vf' : ''}`} />{isVf ? 'Version française' : 'Version originale'}</span>
          </>
        ) : (
          <span className="muted">Choisis une réplique à écouter</span>
        )}
      </div>
      <div className="player-wave"
        onClick={(e) => audio.seek(frac(e))}
        onMouseMove={(e) => setHover(frac(e))}
        onMouseLeave={() => setHover(null)}>
        <canvas ref={canvas} aria-hidden="true" />
        {hover !== null && st.buffer && (
          <span className="scrub" style={{ left: `${hover * 100}%` }}>
            <em>{time(hover * audio.duration())} s</em>
          </span>
        )}
        {meta?.text && <p className="player-text">{meta.text}</p>}
        {st.error && <p className="player-err">{st.error}</p>}
      </div>
      <div className="player-time" ref={timeRef}>0,0 / 0,0 s</div>
    </footer>
  )
}
