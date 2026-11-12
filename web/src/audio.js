// Moteur audio : décode les clips une seule fois, les garde en mémoire et les joue sans délai.
const BARS = 140
const MAX_CACHED = 300

let ctx = null
const cache = new Map() // url -> Promise<{ buffer, peaks }>
const listeners = new Set()

let queued = null // clip à jouer juste après (comparaison VO puis VF)
const state = { url: null, meta: null, buffer: null, peaks: [], source: null, startedAt: 0, offset: 0, playing: false, error: null }

function audioCtx() {
  ctx ||= new (window.AudioContext || window.webkitAudioContext)()
  if (ctx.state === 'suspended') ctx.resume()
  return ctx
}

function peaksOf(buffer) {
  const data = buffer.getChannelData(0)
  const per = Math.max(1, Math.floor(data.length / BARS))
  const out = new Array(BARS).fill(0)
  for (let i = 0; i < BARS; i++) {
    let m = 0
    const end = Math.min((i + 1) * per, data.length)
    for (let j = i * per; j < end; j += 2) { const v = data[j] < 0 ? -data[j] : data[j]; if (v > m) m = v }
    out[i] = m
  }
  const max = Math.max(...out) || 1
  return out.map((v) => Math.sqrt(v / max))
}

export function load(url) {
  if (cache.has(url)) {
    const p = cache.get(url)
    cache.delete(url); cache.set(url, p) // garde les plus récents
    return p
  }
  const p = fetch(url)
    .then(async (r) => {
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Lecture impossible')
      return r.arrayBuffer()
    })
    .then((buf) => audioCtx().decodeAudioData(buf))
    .then((buffer) => ({ buffer, peaks: peaksOf(buffer) }))
  p.catch(() => cache.delete(url))
  cache.set(url, p)
  if (cache.size > MAX_CACHED) cache.delete(cache.keys().next().value)
  return p
}

export function forget(prefix) {
  for (const k of [...cache.keys()]) if (k.startsWith(prefix)) cache.delete(k)
}

function emit() { listeners.forEach((fn) => fn()) }
export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn) }

function startSource(offset) {
  const c = audioCtx()
  const src = c.createBufferSource()
  src.buffer = state.buffer
  src.connect(c.destination)
  src.onended = () => {
    if (state.source !== src) return
    state.playing = false
    state.offset = 0
    state.source = null
    emit()
    if (queued) {
      const q = queued
      queued = null
      play(q.url, q.meta)
    }
  }
  src.start(0, offset)
  state.source = src
  state.startedAt = c.currentTime - offset
  state.playing = true
}

function stopSource() {
  if (state.source) {
    const s = state.source
    state.source = null
    try { s.stop() } catch { /* déjà arrêté */ }
  }
}

export async function play(url, meta, then = null) {
  queued = then
  stopSource()
  state.url = url
  state.meta = meta
  state.playing = false
  state.error = null
  state.buffer = null
  state.peaks = []
  state.offset = 0
  emit()
  try {
    const { buffer, peaks } = await load(url)
    if (state.url !== url) return
    state.buffer = buffer
    state.peaks = peaks
    state.offset = 0
    startSource(0)
  } catch (e) {
    if (state.url === url) state.error = e.message
  }
  emit()
}

export function stop() {
  queued = null
  stopSource()
  state.playing = false
  state.url = null
  state.meta = null
  emit()
}

export function toggle() {
  if (!state.buffer || !state.url) return
  if (state.playing) {
    state.offset = position()
    stopSource()
    state.playing = false
  } else {
    startSource(state.offset >= duration() ? 0 : state.offset)
  }
  emit()
}

export function seek(fraction) {
  if (!state.buffer) return
  const t = Math.max(0, Math.min(1, fraction)) * duration()
  stopSource()
  state.offset = t
  startSource(t)
  emit()
}

export function duration() { return state.buffer?.duration || 0 }
export function position() {
  if (!state.buffer) return 0
  if (!state.playing) return state.offset
  return Math.min(duration(), audioCtx().currentTime - state.startedAt)
}
export function snapshot() { return state }
