import React, { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import Player from './Player.jsx'
import * as audio from './audio.js'
import * as I from './icons.jsx'

/* ---------- Outils ---------- */
async function api(path, opts = {}) {
  const r = await fetch('/api' + path, opts)
  if (!r.ok) {
    const body = await r.json().catch(() => ({}))
    throw new Error(body.detail || `Erreur ${r.status}`)
  }
  return r.json()
}
const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const fmt = (s) => (s ? `${s.toFixed(1).replace('.', ',')} s` : '–')
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0)

function storage(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback } catch { return fallback }
}
function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* rien */ }
}

const FILTERS = [
  { id: 'all', label: 'Toutes' },
  { id: 'todo', label: 'À faire' },
  { id: 'vf', label: 'VF posée' },
  { id: 'valid', label: 'Validées' },
]
const STATUS = {
  todo: { label: 'À faire', cls: 'badge' },
  vf: { label: 'VF posée', cls: 'badge badge-vf' },
  valid: { label: 'Validée en jeu', cls: 'badge badge-ok' },
}

const voUrl = (bank, i) => `/api/banks/${bank}/clips/${i}/vo`
const vfUrl = (bank, c) => `/api/banks/${bank}/clips/${c.index}/vf?f=${encodeURIComponent(c.vf)}&v=${c.vfv || 0}`

let audioVersion = 0
audio.subscribe(() => { audioVersion++ })
const useAudio = () => useSyncExternalStore(audio.subscribe, () => audioVersion)

/* ---------- Contrôle segmenté avec indicateur glissant ---------- */
function Segmented({ items, value, onChange, counts }) {
  const wrap = useRef(null)
  const [pill, setPill] = useState(null)
  useLayoutEffect(() => {
    const el = wrap.current?.querySelector(`[data-id="${value}"]`)
    if (el) setPill({ left: el.offsetLeft, width: el.offsetWidth })
  }, [value, counts])
  return (
    <div className="segmented" role="tablist" ref={wrap}>
      {pill && <span className="seg-pill" style={{ transform: `translateX(${pill.left}px)`, width: pill.width }} />}
      {items.map((f) => (
        <button key={f.id} data-id={f.id} role="tab" aria-selected={value === f.id}
          className={value === f.id ? 'is-on' : ''} onClick={() => onChange(f.id)}>
          {f.label} <span className="count">{counts[f.id]}</span>
        </button>
      ))}
    </div>
  )
}

/* ---------- Ligne (mémorisée : ne se redessine que si elle change) ---------- */
const Row = memo(function Row({ clip, pos, selected, playing, busy, recent, act }) {
  const [over, setOver] = useState(false)
  const [text, setText] = useState(clip.text)
  useEffect(() => setText(clip.text), [clip.text])
  const status = clip.valid ? 'valid' : clip.vf ? 'vf' : 'todo'

  return (
    <div role="row" data-pos={pos}
      className={`row ${selected ? 'is-sel' : ''} ${over ? 'is-over' : ''} ${recent ? 'is-recent' : ''} ${playing ? 'is-playing' : ''}`}
      onMouseDown={() => act.select(pos)}
      onDragOver={(e) => { e.preventDefault(); if (!over) setOver(true) }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setOver(false) }}
      onDrop={(e) => {
        e.preventDefault(); setOver(false)
        const files = [...e.dataTransfer.files]
        if (files.length > 1) act.uploadMany(files)
        else if (files[0]) act.upload(clip, files[0])
      }}
    >
      <span className="c-num">{clip.index}</span>
      <span className="c-cue">
        <span title={clip.name || ''}>{clip.name || '–'}</span>
        <small>{fmt(clip.duration)}</small>
      </span>
      <span className="c-vo">
        <button className={`play ${playing === 'vo' ? 'is-on' : ''}`}
          onClick={() => act.play(clip, 'vo')} onMouseEnter={() => act.prefetch(clip, 'vo')}
          aria-label={`Écouter la VO du clip ${clip.index}`}>
          {playing === 'vo' ? <I.Bars /> : <I.Play size={12} />}
        </button>
      </span>
      <span className="c-text">
        <input className="text" value={text} placeholder={clip.en ? `VO : ${clip.en}` : 'Transcription'}
          aria-label={`Transcription du clip ${clip.index}`}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => text !== clip.text && act.note(clip, { text })}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur()
            if (e.key === 'Escape') { setText(clip.text); e.currentTarget.blur() }
          }} />
      </span>
      <span className="c-vf">
        {busy ? (
          <span className="converting"><span className="spin" /> Conversion…</span>
        ) : clip.vf ? (
          <span className="vf-on">
            <button className={`play play-vf ${playing === 'vf' ? 'is-on' : ''}`}
              onClick={() => act.play(clip, 'vf')} onMouseEnter={() => act.prefetch(clip, 'vf')}
              aria-label={`Écouter la VF du clip ${clip.index}`}>
              {playing === 'vf' ? <I.Bars /> : <I.Play size={12} />}
            </button>
            <span className="file" title={clip.vf}>{clip.vf}</span>
            {clip.vf_duration > 0 && (
              <span className={`vf-dur ${clip.vf_duration > clip.duration * 1.3 + 0.3 ? 'is-long' : ''}`}
                title={clip.vf_duration > clip.duration * 1.3 + 0.3
                  ? `La VF dure ${fmt(clip.vf_duration)}, la VO ${fmt(clip.duration)} : elle risque d'être coupée ou de chevaucher la suite en jeu.`
                  : `Durée de la VF (VO : ${fmt(clip.duration)})`}>
                {fmt(clip.vf_duration)}
              </span>
            )}
            <span className="row-tools">
              <button className="icon-btn" onClick={() => act.reveal(clip)} title="Afficher dans l'Explorateur" aria-label="Afficher le fichier"><I.Folder /></button>
              <button className="icon-btn" onClick={() => act.pick(clip)} title="Remplacer par un autre fichier" aria-label="Remplacer"><I.Replace /></button>
              <button className="icon-btn danger" onClick={() => act.remove(clip)} title="Retirer la VF" aria-label="Retirer"><I.Trash /></button>
            </span>
          </span>
        ) : (
          <button className="drop" onClick={() => act.pick(clip)}>
            <I.Upload /> Déposer un fichier
          </button>
        )}
      </span>
      <span className="c-status">
        <span className={STATUS[status].cls}>{STATUS[status].label}</span>
        {clip.vf && (
          <label className="valid">
            <input type="checkbox" checked={clip.valid} onChange={(e) => { act.note(clip, { valid: e.target.checked }); e.target.blur() }} />
            <span className="box"><I.Check size={12} /></span>
            Testée en jeu
          </label>
        )}
      </span>
      <span className="c-dl">
        <a className="icon-btn" href={`/api/banks/${clip.bank}/clips/${clip.index}/download`} download
          title="Télécharger la VO (WAV)" aria-label={`Télécharger la VO du clip ${clip.index}`}
          onMouseDown={(e) => e.stopPropagation()}><I.Download /></a>
      </span>
    </div>
  )
})

/* ---------- Réglages ---------- */
export function reloadedSteps(r) {
  return [
    { ok: r.installed, label: 'Reloaded-II trouvé', todo: 'Installe Reloaded-II, ou indique son dossier ci-dessous.' },
    { ok: r.essentials, label: 'Persona Essentials installé', todo: 'Dans Reloaded-II : « Télécharger des mods », cherche Persona Essentials et installe-le.' },
    { ok: r.p5r_added, label: 'P5R ajouté dans Reloaded-II', todo: 'Dans Reloaded-II, clique sur « + » et choisis P5R.exe.' },
    { ok: r.linked, label: 'Mod relié à Reloaded-II', todo: 'Clique sur « Relier ».', action: 'link' },
    { ok: r.enabled, label: 'Mod activé pour P5R', todo: 'Clique sur « Activer » (Reloaded-II doit être fermé), ou coche-le dans Reloaded-II.', action: 'enable' },
  ]
}

function Reloaded({ state, onChange }) {
  const r = state.reloaded || {}
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState(null)
  const run = async (what, extra) => {
    setBusy(what); setMsg(null)
    try {
      if (what === 'install') await api('/reloaded/install', { method: 'POST' })
      if (what === 'enable') { onChange(await api('/reloaded/enable', { method: 'POST' })); setBusy(''); return }
      if (what === 'dir') await api('/config', json('POST', { reloaded_dir: extra }))
      onChange(await api('/reloaded/link', { method: 'POST' }))
    } catch (e) { setMsg(e.message) }
    setBusy('')
  }
  const pick = async () => {
    const { path } = await api('/browse', json('POST', { start: r.root || '' }))
    if (path) run('dir', path)
  }
  const steps = reloadedSteps(r)
  return (
    <div className="reloaded">
      <ol className="rl-steps">
        {steps.map((st, k) => {
          const blocked = steps.slice(0, k).some((x) => !x.ok)
          return (
            <li key={st.label} className={st.ok ? 'is-ok' : blocked ? 'is-wait' : 'is-todo'}>
              <span className="rl-dot">{st.ok ? <I.Check size={12} /> : k + 1}</span>
              <span className="rl-text">
                <b>{st.label}</b>
                {!st.ok && !blocked && <small>{st.todo}</small>}
              </span>
              {!st.ok && !blocked && st.action && (
                <button className="btn btn-sm btn-primary" onClick={() => run(st.action)} disabled={!!busy}>
                  {busy === st.action ? <span className="spin light" /> : st.action === 'link' ? 'Relier' : 'Activer'}
                </button>
              )}
              {k === 0 && !st.ok && (
                <button className="btn btn-sm btn-primary" onClick={() => run('install')} disabled={!!busy}>
                  {busy === 'install' ? <><span className="spin light" /> Téléchargement…</> : 'Installer Reloaded-II'}
                </button>
              )}
            </li>
          )
        })}
      </ol>
      {msg && <p className="rl-msg">{msg}</p>}

      <div className="field">
        <label>Dossier de Reloaded-II</label>
        <div className="field-row">
          <code className="rl-path" title={r.root}>{r.root || 'Introuvable'}</code>
          <button className="btn" onClick={pick} disabled={!!busy}><I.Folder /> Changer</button>
          {r.manual && <button className="btn" onClick={() => run('dir', '')} disabled={!!busy}>Automatique</button>}
        </div>
        <p className="help">
          {r.manual ? 'Choisi à la main.' : 'Trouvé automatiquement.'} Le dossier à choisir est celui qui contient <code>Reloaded-II.exe</code>.
        </p>
      </div>

      <details className="rl-why">
        <summary>Pourquoi le mod apparaît à deux endroits ?</summary>
        <p>
          C'est un seul et même dossier. Les VF sont rangées dans l'outil (<code>{r.mod}</code>), et Reloaded-II y accède
          par un raccourci (une « jonction » Windows) placé dans son dossier <code>Mods</code>. Tout ce que tu poses dans
          l'outil est donc vu immédiatement par Reloaded-II, sans copie. Si tu déplaces l'outil, relance-le : le raccourci est refait.
        </p>
      </details>
    </div>
  )
}

function Updates({ version, update, onCheck, onInstall }) {
  const [busy, setBusy] = useState(false)
  const [checked, setChecked] = useState(false)
  const check = async () => {
    setBusy(true)
    await onCheck().catch(() => {})
    setBusy(false)
    setChecked(true)
  }
  let status = null
  if (update?.available) {
    status = (
      <>
        <span className="rl-warn">Version {update.latest} disponible</span>
        <button className="btn btn-sm btn-primary" onClick={onInstall}><I.Download /> Installer</button>
      </>
    )
  } else if (checked && update?.error) {
    status = <span className="rl-warn">Impossible de vérifier pour l'instant (connexion internet, ou aucune version publiée).</span>
  } else if (checked) {
    status = <span className="rl-ok"><I.Check size={13} /> Tu as la dernière version</span>
  }
  return (
    <div className="updates">
      <div className="rl-line">
        <span>Version installée : <b>{version}</b></span>
        <button className="btn btn-sm" onClick={check} disabled={busy}>
          {busy ? <span className="spin" /> : null} Vérifier les mises à jour
        </button>
      </div>
      {status && <div className="rl-line">{status}</div>}
      <p className="help">
        Les nouvelles versions sont publiées sur <a href={update?.url || 'https://github.com/chenetulipe/P5R-FR-AUDIO-LAB/releases'} target="_blank" rel="noreferrer">GitHub</a>.
        L'installation garde tes réglages, tes voix extraites et le mod.
      </p>
    </div>
  )
}

function Settings({ state, onClose, onSave, onExtract, onReloaded, update, onCheckUpdate, onInstallUpdate }) {
  const [cfg, setCfg] = useState(state.config)
  const [extracting, setExtracting] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }))
  const close = useCallback(() => { setLeaving(true); setTimeout(onClose, 140) }, [onClose])
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])
  const browse = async (k) => {
    const { path } = await api('/browse', json('POST', { start: cfg[k] || '' }))
    if (path) set(k, path)
  }
  const extract = async () => {
    setExtracting(true)
    const res = await onExtract(cfg.game_dir, cfg.lang || 'E')
    if (res) set('sound_dir', res.sound_dir)
    setExtracting(false)
  }
  const Field = ({ k, label, help, placeholder }) => (
    <div className="field">
      <label htmlFor={k}>{label}</label>
      <div className="field-row">
        <input id={k} value={cfg[k] || ''} placeholder={placeholder} onChange={(e) => set(k, e.target.value)} />
        <button className="btn" onClick={() => browse(k)}><I.Folder /> Parcourir</button>
      </div>
      {help && <p className="help">{help}</p>}
    </div>
  )
  return (
    <div className={`backdrop ${leaving ? 'is-leaving' : ''}`} onMouseDown={close}>
      <section className="dialog" role="dialog" aria-label="Réglages" onMouseDown={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>Réglages</h2>
          <button className="icon-btn" onClick={close} aria-label="Fermer"><I.Close /></button>
        </div>

        <h3>Jeu</h3>
        {Field({ k: 'game_dir', label: 'Dossier du jeu P5R', placeholder: '…\\steamapps\\common\\P5R' })}
        <div className="field-row extract-row">
          <div className="select">
            <select value={cfg.lang || 'E'} onChange={(e) => set('lang', e.target.value)} aria-label="Langue des voix">
              <option value="E">Voix anglaises</option>
              <option value="J">Voix japonaises</option>
            </select>
          </div>
          <button className="btn btn-primary" onClick={extract} disabled={!cfg.game_dir || extracting}>
            {extracting ? <><span className="spin light" /> Extraction…</> : 'Extraire les voix de combat'}
          </button>
        </div>
        <p className="help">Copie les voix des persos (BPxx) et des navigatrices (SPTxx). Le jeu n'est pas modifié.</p>

        <h3>Mod et Reloaded-II</h3>
        <Reloaded state={state} onChange={onReloaded} />

        <h3>Mises à jour</h3>
        <Updates version={state.version} update={update} onCheck={onCheckUpdate} onInstall={onInstallUpdate} />

        <h3>Dossiers</h3>
        {Field({ k: 'sound_dir', label: 'Voix extraites', help: 'Rempli tout seul après l\'extraction.' })}
        {Field({ k: 'rec_dir', label: 'Enregistrements VF', help: 'Pour l\'import groupé : fichiers nommés BP01_118.wav, ou rangés dans un sous-dossier BP01.' })}

        <label className="switch">
          <input type="checkbox" checked={!!cfg.match_volume} onChange={(e) => set('match_volume', e.target.checked)} />
          <span className="track"><span /></span>
          Ajuster le volume de la VF sur celui de la VO
        </label>
        <label className="switch">
          <input type="checkbox" checked={cfg.trim_silence !== false} onChange={(e) => set('trim_silence', e.target.checked)} />
          <span className="track"><span /></span>
          Couper les silences au début et à la fin des VF
        </label>

        <p className="tools">
          {Object.entries(state.tools).map(([name, ok]) => (
            <span key={name} className={ok ? 'ok' : 'ko'}>{ok ? <I.Check size={12} /> : <I.Close size={12} />} {name}</span>
          ))}
        </p>
        <div className="dialog-actions">
          <button className="btn" onClick={close}>Annuler</button>
          <button className="btn btn-primary" onClick={() => onSave(cfg)}>Enregistrer</button>
        </div>
      </section>
    </div>
  )
}

/* ---------- Squelette de chargement ---------- */
const Skeleton = () => (
  <div className="skeleton" aria-label="Chargement">
    {Array.from({ length: 10 }, (_, i) => <div key={i} className="sk-row" style={{ animationDelay: `${i * 40}ms` }} />)}
  </div>
)

/* ---------- Appli ---------- */
export default function App() {
  const [state, setState] = useState(null)
  const [banks, setBanks] = useState([])
  const [bank, setBank] = useState(() => storage('bank', null))
  const [clips, setClips] = useState([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [sel, setSel] = useState(0)
  const [busy, setBusy] = useState({})
  const [recent, setRecent] = useState([])
  const [toasts, setToasts] = useState([])
  const [settings, setSettings] = useState(false)
  const [view, setView] = useState({ top: 0, h: 800 })
  const [rowH, setRowH] = useState(51)
  const [editName, setEditName] = useState(false)
  const [update, setUpdate] = useState(null)
  const [updating, setUpdating] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef(null)
  const pickTarget = useRef(null)
  const listRef = useRef(null)
  const clipCache = useRef(new Map())
  useAudio()
  const now = audio.snapshot()

  const toast = useCallback((msg, kind = 'ok', action = null) => {
    const id = Math.random()
    setToasts((t) => [...t, { id, msg, kind, action }])
    setTimeout(() => setToasts((t) => t.map((x) => (x.id === id ? { ...x, leaving: true } : x))), action ? 6500 : 3800)
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), action ? 6800 : 4100)
  }, [])

  const loadState = useCallback(() => api('/state').then(setState), [])
  const loadBanks = useCallback(async () => {
    const b = await api('/banks')
    setBanks(b)
    setBank((cur) => (cur && b.some((x) => x.bank === cur) ? cur : b[0]?.bank || null))
  }, [])

  useEffect(() => {
    api('/update').then(setUpdate).catch(() => {})
  }, [])

  const installUpdate = async () => {
    const notes = update.notes ? `\n\nNouveautés :\n${update.notes.slice(0, 600)}` : ''
    if (!window.confirm(`Installer la version ${update.latest} ?\nTes réglages, tes voix extraites et le mod sont gardés.${notes}`)) return
    setUpdating(true)
    try {
      await api('/update', { method: 'POST' })
      // L'outil redémarre : on attend qu'il revienne, puis on recharge la page
      await new Promise((r) => setTimeout(r, 2500))
      for (let i = 0; i < 120; i++) {
        try {
          const w = await api('/whoami')
          if (w.version === update.latest) { location.reload(); return }
        } catch { /* pas encore relancé */ }
        await new Promise((r) => setTimeout(r, 1000))
      }
      setUpdating(false)
      toast("La mise à jour est installée, mais l'outil ne redémarre pas tout seul : relance start.bat.", 'err')
    } catch (e) {
      setUpdating(false)
      toast(e.message, 'err')
    }
  }

  useEffect(() => {
    loadState().catch((e) => toast(e.message, 'err'))
    loadBanks().catch((e) => toast(e.message, 'err'))
  }, [loadState, loadBanks, toast])

  const fetchClips = useCallback((b) => {
    const p = api(`/banks/${b}/clips`).then((list) => {
      const c = list.map((x) => ({ ...x, bank: b }))
      clipCache.current.set(b, c)
      return c
    })
    return p
  }, [])

  // Changement de perso : affichage immédiat depuis le cache, puis mise à jour
  useEffect(() => {
    if (!bank) { setClips([]); return }
    store('bank', bank)
    setSel(0); setRecent([]); setQuery(''); setEditName(false)
    if (listRef.current) listRef.current.scrollTop = 0
    setView((v) => ({ ...v, top: 0 }))
    const cached = clipCache.current.get(bank)
    if (cached) setClips(cached)
    else setLoading(true)
    let alive = true
    fetchClips(bank)
      .then((c) => alive && setClips(c))
      .catch((e) => toast(e.message, 'err'))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [bank, fetchClips, toast])

  // Une fois l'outil ouvert, on charge en arrière-plan la liste de chaque perso
  const bankNames = banks.map((b) => b.bank).join(',')
  useEffect(() => {
    if (!bankNames) return
    let stop = false
    const t = setTimeout(async () => {
      for (const b of bankNames.split(',')) {
        if (stop) return
        if (!clipCache.current.has(b)) await fetchClips(b).catch(() => {})
      }
    }, 800)
    return () => { stop = true; clearTimeout(t) }
  }, [bankNames, fetchClips])

  // Liste virtuelle : seules les lignes visibles (et quelques-unes autour) sont dessinées
  useEffect(() => {
    const el = listRef.current
    if (!el) return
    const measure = () => {
      setView({ top: el.scrollTop, h: el.clientHeight })
      const r = el.querySelector('.row')
      if (r && r.offsetHeight) setRowH(r.offsetHeight)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [loading])
  useLayoutEffect(() => {
    const r = listRef.current?.querySelector('.row')
    if (r && r.offsetHeight && r.offsetHeight !== rowH) setRowH(r.offsetHeight)
  })
  const ensureVisible = (i) => {
    const el = listRef.current
    if (!el) return
    const top = i * rowH
    if (top < el.scrollTop) el.scrollTop = top
    else if (top + rowH > el.scrollTop + el.clientHeight) el.scrollTop = top + rowH - el.clientHeight
    setView({ top: el.scrollTop, h: el.clientHeight })
  }

  // Glisser un fichier n'importe où : met en avant les zones de dépôt
  useEffect(() => {
    let depth = 0
    const enter = (e) => { if (e.dataTransfer?.types?.includes('Files')) { depth++; setDragging(true) } }
    const leave = () => { depth = Math.max(0, depth - 1); if (!depth) setDragging(false) }
    const drop = () => { depth = 0; setDragging(false) }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    window.addEventListener('dragover', (e) => e.preventDefault())
    return () => { window.removeEventListener('dragenter', enter); window.removeEventListener('dragleave', leave); window.removeEventListener('drop', drop) }
  }, [])

  const current = banks.find((b) => b.bank === bank)

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return clips.filter((c) => {
      const keep = recent.includes(c.index)
      if (!keep && filter === 'todo' && c.vf) return false
      if (!keep && filter === 'vf' && (!c.vf || c.valid)) return false
      if (!keep && filter === 'valid' && !c.valid) return false
      if (!q) return true
      return String(c.index) === q || (c.name || '').toLowerCase().includes(q) || (c.text || '').toLowerCase().includes(q) || (c.en || '').toLowerCase().includes(q)
    })
  }, [clips, filter, query, recent])

  const counts = useMemo(() => {
    let vf = 0, valid = 0
    for (const c of clips) { if (c.valid) valid++; else if (c.vf) vf++ }
    return { all: clips.length, todo: clips.length - vf - valid, vf, valid }
  }, [clips])

  const patchClip = useCallback((index, patch) => {
    setClips((cs) => {
      const next = cs.map((c) => (c.index === index ? { ...c, ...patch } : c))
      clipCache.current.set(bank, next)
      return next
    })
    setRecent((r) => (r.includes(index) ? r : [...r, index]))
  }, [bank])

  const updateBankCount = (b, delta) => setBanks((bs) => bs.map((x) => (x.bank === b ? { ...x, done: x.done + delta } : x)))

  /* Actions des lignes : objet stable pour que les lignes mémorisées ne se redessinent pas */
  const live = useRef({})
  const urlOf = (clip, kind) => (kind === 'vf' ? vfUrl(bank, clip) : voUrl(bank, clip.index))
  live.current = {
    bank,
    patch: (i, p) => patchClip(i, p),
    select: (pos) => setSel(pos),
    prefetch: (clip, kind) => { audio.load(urlOf(clip, kind)).catch(() => {}) },
    play: (clip, kind) => {
      const url = urlOf(clip, kind)
      const st = audio.snapshot()
      if (st.url === url && (st.playing || !st.buffer)) { audio.stop(); return }
      audio.play(url, { key: `${bank}:${clip.index}:${kind}`, kind, title: `${current?.name || bank}, clip ${clip.index}`, text: clip.text })
    },
    pick: (clip) => { pickTarget.current = clip; fileRef.current.click() },
    reveal: (clip) => api(`/banks/${bank}/clips/${clip.index}/reveal`, { method: 'POST' }).catch((e) => toast(e.message, 'err')),
    upload: async (clip, file) => {
      setBusy((b) => ({ ...b, [clip.index]: true }))
      try {
        const fd = new FormData()
        fd.append('file', file)
        const had = !!clip.vf
        const res = await api(`/banks/${bank}/clips/${clip.index}/vf`, { method: 'POST', body: fd })
        audio.forget(`/api/banks/${bank}/clips/${clip.index}/vf`)
        patchClip(clip.index, { vf: res.file, vf_duration: res.vf_duration, valid: false, vfv: Date.now() })
        if (!had) updateBankCount(bank, 1)
        toast(`Clip ${clip.index} : VF enregistrée dans le mod.`, 'ok', { label: 'Afficher', run: () => live.current.reveal(clip) })
      } catch (e) { toast(e.message, 'err') }
      setBusy((b) => { const n = { ...b }; delete n[clip.index]; return n })
    },
    remove: async (clip) => {
      try {
        await api(`/banks/${bank}/clips/${clip.index}/vf`, { method: 'DELETE' })
        if (audio.snapshot().meta?.key === `${bank}:${clip.index}:vf`) audio.stop()
        audio.forget(`/api/banks/${bank}/clips/${clip.index}/vf`)
        patchClip(clip.index, { vf: null, valid: false })
        updateBankCount(bank, -1)
        const b = bank
        toast(`Clip ${clip.index} : VF retirée.`, 'ok', {
          label: 'Annuler',
          run: async () => {
            try {
              const r = await api(`/banks/${b}/clips/${clip.index}/restore`, { method: 'POST' })
              if (b === live.current.bank) live.current.patch(clip.index, { vf: r.file, vf_duration: r.vf_duration, vfv: Date.now() })
              updateBankCount(b, 1)
              toast(`Clip ${clip.index} : VF remise.`)
            } catch (e) { toast(e.message, 'err') }
          },
        })
      } catch (e) { toast(e.message, 'err') }
    },
    uploadMany: async (files) => {
      const names = banks.map((b) => b.bank.toUpperCase())
      const plan = []
      const unknown = []
      for (const f of files) {
        const stem = f.name.replace(/\.[^.]+$/, '').toUpperCase()
        const owner = names.filter((n) => stem.startsWith(n)).sort((a, b) => b.length - a.length)[0]
        const m = owner ? stem.slice(owner.length).match(/^[_\- #]*(\d+)/) : stem.match(/^(\d+)/)
        if (m) plan.push({ bank: owner || bank, index: +m[1], file: f })
        else unknown.push(f.name)
      }
      if (!plan.length) {
        toast(`Aucun fichier reconnu. Nomme-les comme ${bank}_118.wav (perso puis numéro du clip).`, 'err')
        return
      }
      toast(`Import de ${plan.length} fichier${plan.length > 1 ? 's' : ''}…`)
      let ok = 0
      const errors = []
      for (const it of plan) {
        if (it.bank === bank) setBusy((b) => ({ ...b, [it.index]: true }))
        try {
          const fd = new FormData()
          fd.append('file', it.file)
          const res = await api(`/banks/${it.bank}/clips/${it.index}/vf`, { method: 'POST', body: fd })
          if (it.bank === bank) patchClip(it.index, { vf: res.file, vf_duration: res.vf_duration, valid: false, vfv: Date.now() })
          ok++
        } catch (e) { errors.push(`${it.file.name} : ${e.message}`) }
        if (it.bank === bank) setBusy((b) => { const n = { ...b }; delete n[it.index]; return n })
      }
      audio.forget('/api/banks/')
      plan.forEach((it) => clipCache.current.delete(it.bank))
      loadBanks()
      const extra = [unknown.length && `${unknown.length} nom${unknown.length > 1 ? 's' : ''} non reconnu${unknown.length > 1 ? 's' : ''}`,
        errors.length && `${errors.length} en erreur`].filter(Boolean).join(', ')
      toast(`${ok} VF posée${ok > 1 ? 's' : ''}${extra ? ` (${extra})` : ''}.`, errors.length || unknown.length ? 'err' : 'ok')
    },
    note: (clip, patch) => {
      patchClip(clip.index, patch)
      api(`/banks/${bank}/clips/${clip.index}`, json('PATCH', patch)).catch((e) => toast(e.message, 'err'))
    },
  }
  const act = useMemo(() => Object.fromEntries(
    ['select', 'prefetch', 'play', 'pick', 'reveal', 'upload', 'uploadMany', 'remove', 'note'].map((k) => [k, (...a) => live.current[k](...a)]),
  ), [])

  // Précharge la VO de la ligne choisie et de la suivante, une fois la sélection posée
  useEffect(() => {
    if (!bank || !shown[sel]) return
    const t = setTimeout(() => {
      for (let i = sel; i < Math.min(sel + 2, shown.length); i++) audio.load(voUrl(bank, shown[i].index)).catch(() => {})
    }, 160)
    return () => clearTimeout(t)
  }, [sel, shown, bank])

  const setup = state?.setup
  // Pendant la préparation (recherche du jeu, extraction), on suit l'avancement
  useEffect(() => {
    if (!setup || !['detecting', 'extracting'].includes(setup.status)) return
    const t = setTimeout(() => loadState().catch(() => {}), 700)
    return () => clearTimeout(t)
  }, [state, setup, loadState])
  const wasReady = useRef(true)
  useEffect(() => {
    const ready = setup?.status === 'ready'
    if (ready && !wasReady.current) loadBanks().catch(() => {})
    wasReady.current = ready
  }, [setup, loadBanks])

  const pickGame = async () => {
    const { path } = await api('/browse', json('POST', { start: '' }))
    if (!path) return
    setState((s) => ({ ...s, setup: { status: 'extracting', message: 'Extraction des voix de combat…' } }))
    const res = await extractGame(path, 'E')
    setState((s) => ({ ...s, setup: res ? { status: 'ready', message: '' } : { status: 'not_found', message: 'Ce dossier ne contient pas Persona 5 Royal.' } }))
  }

  const exportBank = () => {
    toast(`Préparation de l'export de ${current?.name || bank}… le téléchargement va démarrer.`)
    const a = document.createElement('a')
    a.href = `/api/banks/${bank}/export`
    a.download = ''
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  const batch = async () => {
    try {
      const r = await api(`/banks/${bank}/batch`, { method: 'POST' })
      toast(`${r.imported.length} VF importées sur ${r.found} fichiers trouvés${r.errors.length ? `, ${r.errors.length} en erreur` : ''}.`,
        r.errors.length ? 'err' : 'ok')
      audio.forget(`/api/banks/${bank}/`)
      setClips(await fetchClips(bank))
      loadBanks()
    } catch (e) { toast(e.message, 'err') }
  }

  const saveSettings = async (cfg) => {
    try {
      // Reloaded-II et le dossier du mod se règlent à part : ne pas renvoyer d'anciennes valeurs
      const { reloaded_dir, mod_dir, ...rest } = cfg
      await api('/config', json('POST', rest))
      await loadState()
      clipCache.current.clear()
      setSettings(false)
      toast('Réglages enregistrés.')
      loadBanks()
    } catch (e) { toast(e.message, 'err') }
  }

  const extractGame = async (game_dir, lang) => {
    try {
      const res = await api('/game/extract', json('POST', { game_dir, lang }))
      clipCache.current.clear()
      await loadState()
      await loadBanks()
      toast(`${res.count} fichiers de voix extraits.`)
      return res
    } catch (e) { toast(e.message, 'err'); return null }
  }

  const rename = async (name) => {
    setEditName(false)
    if (!name?.trim() || name.trim() === current?.name) return
    try {
      await api('/config', json('POST', { names: { ...state.config.names, [bank]: name.trim() } }))
      await loadState()
      loadBanks()
    } catch (e) { toast(e.message, 'err') }
  }

  // Clavier : ↑ ↓ naviguer, Espace = VO, Maj + Espace = VF, Entrée = écrire la transcription
  useEffect(() => {
    const onKey = (e) => {
      if (settings || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const next = Math.max(0, Math.min(shown.length - 1, sel + (e.key === 'ArrowDown' ? 1 : -1)))
        setSel(next)
        ensureVisible(next)
      } else if (e.key === ' ' && shown[sel]) {
        e.preventDefault()
        const c = shown[sel]
        if (e.shiftKey) { if (c.vf) act.play(c, 'vf') } else act.play(c, 'vo')
      } else if ((e.key === 'c' || e.key === 'C') && shown[sel]?.vf) {
        e.preventDefault()
        const c = shown[sel]
        const title = `${current?.name || bank}, clip ${c.index}`
        audio.play(voUrl(bank, c.index), { key: `${bank}:${c.index}:vo`, kind: 'vo', title, text: c.text },
          { url: vfUrl(bank, c), meta: { key: `${bank}:${c.index}:vf`, kind: 'vf', title, text: c.text } })
      } else if (e.key === 'Enter' && shown[sel]) {
        e.preventDefault()
        ensureVisible(sel)
        requestAnimationFrame(() => listRef.current?.querySelector(`[data-pos="${sel}"] .text`)?.focus())
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const total = banks.reduce((a, b) => ({ done: a.done + b.done, count: a.count + b.count }), { done: 0, count: 0 })
  const groups = [
    { title: 'Personnages', items: banks.filter((b) => !b.bank.startsWith('SPT')) },
    { title: 'Navigation', items: banks.filter((b) => b.bank.startsWith('SPT')) },
  ].filter((g) => g.items.length)
  const playingKey = now.playing || (now.url && !now.buffer) ? now.meta?.key : null

  return (
    <div className={`app ${dragging ? 'is-dragging' : ''}`}>
      <header className="topbar">
        <div className="brand">
          <I.Logo />
          <h1>P5R Audio Lab</h1>
          <span className="brand-sub">PERSONA 5 ROYAL MOD VF</span>
        </div>
        <div className="total" title="Répliques avec une VF, tous persos confondus">
          <span className="total-bar"><span style={{ width: `${pct(total.done, total.count)}%` }} /></span>
          <span><b>{total.done.toLocaleString('fr-FR')}</b> / {total.count.toLocaleString('fr-FR')} doublées</span>
        </div>
        <div className="top-actions">
          {update?.available && (
            <button className="btn btn-primary" onClick={installUpdate} disabled={updating}
              title={`Version actuelle : ${update.current}`}>
              <I.Download /> Nouvelle version {update.latest}
            </button>
          )}
          {state?.reloaded && (() => {
            const left = reloadedSteps(state.reloaded).filter((x) => !x.ok).length
            return (
              <button className={`rl-chip ${left ? '' : 'ok'}`} onClick={() => setSettings(true)}
                title={left ? 'Ouvre les réglages pour finir de brancher le mod sur le jeu' : 'Le mod est prêt à être testé en jeu'}>
                <i /> {left ? `Reloaded-II : ${left} étape${left > 1 ? 's' : ''} à faire` : 'Prêt pour le jeu'}
              </button>
            )
          })()}
          <button className="btn" onClick={() => api('/open', json('POST', { what: 'mod' })).catch((e) => toast(e.message, 'err'))}>
            <I.Folder /> Dossier du mod
          </button>
          <button className="btn" onClick={() => setSettings(true)}><I.Gear /> Réglages</button>
        </div>
      </header>

      <aside className="sidebar">
        {banks.length === 0 && <p className="muted pad">Aucune voix trouvée. Ouvre les réglages pour extraire celles du jeu.</p>}
        {groups.map((g) => (
          <nav key={g.title} aria-label={g.title}>
            <h2 className="side-title">{g.title}</h2>
            {g.items.map((b) => {
              const p = pct(b.done, b.count)
              return (
                <button key={b.bank} className={`char ${b.bank === bank ? 'is-on' : ''} ${p === 100 ? 'is-full' : ''}`}
                  onClick={() => setBank(b.bank)}
                  onMouseEnter={() => { if (!clipCache.current.has(b.bank)) fetchClips(b.bank).catch(() => {}) }}>
                  <span className="char-name">{b.name}</span>
                  <span className="char-count">{p === 100 ? <I.Check size={13} /> : `${b.done}/${b.count}`}</span>
                  <span className="char-bar"><span style={{ width: `${p}%` }} /></span>
                </button>
              )
            })}
          </nav>
        ))}
      </aside>

      <main className={`content ${setup && setup.status !== 'ready' ? 'is-setup' : ''}`}>
        {setup && setup.status !== 'ready' && (
          <div className="setup">
            {['detecting', 'extracting'].includes(setup.status) ? (
              <>
                <span className="spin big" />
                <h2>{setup.message}</h2>
                <p className="muted">Une seule fois, au premier lancement. Le jeu n'est pas modifié.</p>
              </>
            ) : (
              <>
                <h2>{setup.message || 'Persona 5 Royal est introuvable.'}</h2>
                <p className="muted">Indique le dossier du jeu, celui qui contient <code>P5R.exe</code> et le dossier <code>CPK</code>.</p>
                <button className="btn btn-primary" onClick={pickGame}><I.Folder /> Choisir le dossier du jeu</button>
              </>
            )}
          </div>
        )}

        {current && (
          <div className="head">
            <div>
              <h2 className="title">
                {editName ? (
                  <input className="name-edit" autoFocus defaultValue={current.name} aria-label="Nom du personnage"
                    onBlur={(e) => rename(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') rename(e.currentTarget.value)
                      if (e.key === 'Escape') setEditName(false)
                    }} />
                ) : current.name}
                <span className="tag">{current.bank}</span>
                {!editName && <button className="link small" onClick={() => setEditName(true)}>Renommer</button>}
              </h2>
              <p className="muted">
                {current.done} sur {current.count} répliques doublées ({pct(current.done, current.count)} %), {counts.valid} testée{counts.valid > 1 ? 's' : ''} en jeu
              </p>
            </div>
            <div className="head-actions">
              <button className="btn" onClick={exportBank} title="Télécharge toutes les VO de ce perso dans un zip, nommées pour l'import groupé"><I.Download /> Export groupé</button>
              <button className="btn" onClick={batch} title="Importe les fichiers du dossier des enregistrements VF"><I.Upload /> Import groupé</button>
            </div>
          </div>
        )}

        <div className="toolbar">
          <Segmented items={FILTERS} value={filter} counts={counts}
            onChange={(f) => { setFilter(f); setSel(0); setRecent([]) }} />
          <label className="search">
            <I.Search />
            <input type="search" placeholder="Rechercher un n°, un cue, une phrase" value={query}
              onChange={(e) => { setQuery(e.target.value); setSel(0) }} aria-label="Rechercher" />
          </label>
        </div>

        <div className="table" role="table">
          <div className="row row-head" role="row">
            <span className="c-num">N°</span><span>Cue</span><span>VO</span><span>Transcription</span><span>VF</span><span>Statut</span><span />
          </div>
          <div className="rows" ref={listRef}
            onScroll={(e) => { const el = e.currentTarget; setView({ top: el.scrollTop, h: el.clientHeight }) }}>
            {loading ? <Skeleton /> : shown.length === 0 ? (
              <p className="empty">{clips.length ? 'Aucune réplique pour ce filtre.' : 'Choisis un personnage.'}</p>
            ) : (() => {
              const start = Math.max(0, Math.floor(view.top / rowH) - 12)
              const end = Math.min(shown.length, Math.ceil((view.top + view.h) / rowH) + 12)
              return (
                <>
                  <div style={{ height: start * rowH }} aria-hidden="true" />
                  {shown.slice(start, end).map((c, k) => {
                    const i = start + k
                    const pk = playingKey?.startsWith(`${bank}:${c.index}:`) ? playingKey.split(':')[2] : null
                    return (
                      <Row key={c.index} clip={c} pos={i} selected={i === sel} playing={pk}
                        busy={!!busy[c.index]} recent={recent.includes(c.index) && !!c.vf} act={act} />
                    )
                  })}
                  <div style={{ height: (shown.length - end) * rowH }} aria-hidden="true" />
                </>
              )
            })()}
          </div>
        </div>
        <p className="keys">
          <kbd>↑</kbd><kbd>↓</kbd> naviguer <kbd>Espace</kbd> VO <kbd>Maj</kbd>+<kbd>Espace</kbd> VF <kbd>C</kbd> comparer VO puis VF <kbd>Entrée</kbd> transcrire. Glisse plusieurs fichiers nommés <code>BP01_118.wav</code> sur la liste pour tous les poser d'un coup.
        </p>
      </main>

      <Player />

      <input ref={fileRef} type="file" accept="audio/*" hidden
        onChange={(e) => { const f = e.target.files[0]; if (f && pickTarget.current) act.upload(pickTarget.current, f); e.target.value = '' }} />

      {settings && state && <Settings state={state} onClose={() => setSettings(false)} onSave={saveSettings} onExtract={extractGame}
        onReloaded={(r) => setState((s) => ({ ...s, reloaded: r }))}
        update={update} onCheckUpdate={() => api('/update?force=true').then(setUpdate)}
        onInstallUpdate={() => { setSettings(false); installUpdate() }} />}

      {updating && (
        <div className="backdrop">
          <div className="dialog updating">
            <span className="spin big" />
            <h2>Mise à jour vers la version {update?.latest}…</h2>
            <p className="muted">L'outil va redémarrer tout seul. Ne ferme pas la fenêtre noire.</p>
          </div>
        </div>
      )}

      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind} ${t.leaving ? 'is-leaving' : ''}`}>
            {t.kind === 'err' ? <I.Close /> : <I.Check />}
            <span>{t.msg}</span>
            {t.action && <button className="link" onClick={t.action.run}>{t.action.label}</button>}
          </div>
        ))}
      </div>
    </div>
  )
}
