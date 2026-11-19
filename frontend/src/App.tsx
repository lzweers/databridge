import { useEffect, useRef, useState, type ReactNode } from 'react'

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
type Mapping = Record<'external_id' | 'name' | 'price_eur' | 'stock', string>
type Preview = { headers: string[]; preview: Record<string, string>[]; total_rows: number; suggested_mapping: Mapping }
type ImportRun = { id: number; filename: string; source_name: string; status: string; total_rows: number; inserted: number; updated: number; unchanged: number; rejected: number; created_at: string }
type Issue = { row_number: number; field: string; code: string; message: string }
type Offer = { id: number; source_name: string; external_id: string; name: string; price_amount: string; currency: string; stock: number | null }
type CatalogSort = 'name_asc' | 'name_desc' | 'stock_asc' | 'stock_desc' | 'source_asc' | 'latest'
type CatalogResponse = { items: Offer[]; total: number; offset: number; limit: number; sources: string[] }
const CATALOG_PAGE_SIZE = 20
type DemoPreview = { source: string; total_rows: number; currency_note: string; preview: { id: number; title: string; price: number; stock: number }[] }
type Summary = { offers: number; imports: number; issues: number; sources: number }
type Page = 'overview' | 'imports' | 'api' | 'catalog' | 'runs' | 'lineage' | 'pipeline' | 'quality'
type Snapshot = Record<string, string | number | null>
type LineageEvent = { id: number; action: string; import_id: number; import_filename: string; import_created_at: string; row_number: number; raw: Record<string, unknown>; before: Snapshot | null; after: Snapshot; changed_fields: string[] }
type OfferLineage = { offer: Offer & { last_changed_import_id: number }; history_available_since: string; history_limited: boolean; events: LineageEvent[] }
type RowDetail = { row_number: number; raw: Record<string, unknown>; action: string; offer_id: number | null; normalized: Snapshot | null; issues: { field: string; code: string; message: string }[] }
type RunRows = { run: ImportRun; offset: number; limit: number; rows: RowDetail[] }
type Pipeline = { configured: boolean; connector: string; enabled: boolean; interval_minutes: number; status: string; next_run_at: string | null; last_attempt_at: string | null; last_success_at: string | null; last_error: string | null; consecutive_failures: number; last_import_id: number | null }
type Execution = { id: number; status: string; started_at: string; finished_at: string | null; error: string | null; import_id: number | null }
type QualitySource = { source_name: string; runs: number; total_rows: number; accepted: number; rejected: number; quality_percent: number | null }
type QualityRun = { id: number; source_name: string; total_rows: number; accepted: number; rejected: number; quality_percent: number | null; created_at: string | null }
type QualityReport = { filter_source: string | null; available_sources: string[]; total_runs: number; total_rows: number; accepted: number; rejected: number; quality_percent: number | null; by_source: QualitySource[]; top_issues: { field: string; code: string; count: number }[]; recent_runs: QualityRun[] }
const displayQuality = (value: number | null) => value === null ? '–' : `${value.toLocaleString('de-DE', { maximumFractionDigits: 1 })} %`
const formatDate = (date: string | null) => date ? new Date(date).toLocaleString('de-DE') : '–'

const actionText: Record<string, string> = { inserted: 'Neu', updated: 'Aktualisiert', unchanged: 'Unverändert', rejected: 'Abgelehnt', legacy: 'Vor v0.3' }
const fieldText: Record<string, string> = { name: 'Produktname', price_amount: 'Preis', currency: 'Währung', stock: 'Lagerbestand', external_id: 'Externe ID' }
const pretty = (value: unknown) => JSON.stringify(value, null, 2)

// Network errors need actionable language instead of generic 'Failed to fetch'.
function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof TypeError && /fetch|network/i.test(error.message)) {
    return 'Backend nicht erreichbar. Prüfe, ob Docker und die API auf localhost:8000 laufen.'
  }
  return error instanceof Error ? error.message : fallback
}

async function callApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, options)
  if (!response.ok) {
    const data: { detail?: string | { msg?: string }[] } = await response.json().catch(() => ({}))
    const detail = Array.isArray(data.detail) ? data.detail.map(x => x.msg).join(', ') : data.detail
    throw new Error(detail || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

const names: Record<keyof Mapping, string> = {
  external_id: 'Externe Produkt-ID', name: 'Produktname', price_eur: 'Preis in EUR', stock: 'Lagerbestand (optional)'
}

function Status({ state }: { state: string }) {
  return <span className={`pill ${state === 'completed' ? 'good' : 'warn'}`}>
    <span className="status-dot" />{state === 'completed' ? 'Abgeschlossen' : 'Mit Prüffällen'}
  </span>
}


/** Small consistent outline icon set; kept local to avoid new runtime dependencies. */
function Glyph({ name }: { name: string }) {
  const shared = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  let content: ReactNode
  switch (name) {
    case 'brand': content = <><circle cx="12" cy="5" r="2.2" /><path d="M12 7.5v11M8.5 19h7" /></>; break
    case 'overview': content = <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>; break
    case 'imports': content = <><path d="M12 16V3m0 0L7 8m5-5 5 5" /><path d="M4 15v5h16v-5" /></>; break
    case 'api': content = <><path d="M4 7h16m0 0-4-4m4 4-4 4M20 17H4m0 0 4-4m-4 4 4 4" /></>; break
    case 'pipeline': content = <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>; break
    case 'quality': content = <><path d="m12 2 9 10-9 10L3 12z" /><path d="m8.5 12 2.3 2.3 4.9-5" /></>; break
    case 'runs': content = <><path d="M6 3h12v18H6zM9 7h6M9 11h6M9 15h6" /></>; break
    case 'catalog': content = <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M3 15h18M9 3v18M15 3v18" /></>; break
    case 'layers': content = <><path d="m12 2 9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5" /></>; break
    case 'issues': content = <><path d="M5 21V3m0 1h13l-3 5 3 5H5" /></>; break
    case 'sources': content = <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>; break
    default: content = <><path d="M12 3v18M3 12h18" /></>
  }
  return <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" {...shared}>{content}</svg>
}

export default function App() {
  const [page, setPage] = useState<Page>('overview')
  const [summary, setSummary] = useState<Summary>({ offers: 0, imports: 0, issues: 0, sources: 0 })
  const [dataStatus, setDataStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [imports, setImports] = useState<ImportRun[]>([])
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null)
  const [catalogQuery, setCatalogQuery] = useState('')
  const [catalogSource, setCatalogSource] = useState('')
  const [catalogSort, setCatalogSort] = useState<CatalogSort>('name_asc')
  const [catalogOffset, setCatalogOffset] = useState(0)
  const [catalogStatus, setCatalogStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [catalogError, setCatalogError] = useState('')
  const [catalogReload, setCatalogReload] = useState(0)
  const [catalogExportBusy, setCatalogExportBusy] = useState(false)
  const [catalogDetailId, setCatalogDetailId] = useState<number | null>(null)
  const [catalogDetail, setCatalogDetail] = useState<OfferLineage | null>(null)
  const [catalogDetailStatus, setCatalogDetailStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [catalogDetailError, setCatalogDetailError] = useState('')
  const catalogDetailRequest = useRef(0)
  const detailCloseButton = useRef<HTMLButtonElement | null>(null)
  const detailPreviousFocus = useRef<HTMLElement | null>(null)
  const [error, setError] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [mapping, setMapping] = useState<Mapping>({ external_id: '', name: '', price_eur: '', stock: '' })
  const [sourceName, setSourceName] = useState('Lieferant A')
  const [busy, setBusy] = useState(false)
  const [lastRun, setLastRun] = useState<ImportRun | null>(null)
  const [issues, setIssues] = useState<Issue[]>([])
  const [demoPreview, setDemoPreview] = useState<DemoPreview | null>(null)
  const [demoRun, setDemoRun] = useState<ImportRun | null>(null)
  const [demoIssues, setDemoIssues] = useState<Issue[]>([])
  const [demoBusy, setDemoBusy] = useState(false)
  const [selectedOffer, setSelectedOffer] = useState<OfferLineage | null>(null)
  const [selectedRun, setSelectedRun] = useState<RunRows | null>(null)
  const [detailBusy, setDetailBusy] = useState(false)
  const [pipeline, setPipeline] = useState<Pipeline | null>(null)
  const [executions, setExecutions] = useState<Execution[]>([])
  const [intervalMinutes, setIntervalMinutes] = useState(60)
  const [pipelineBusy, setPipelineBusy] = useState(false)
  const [quality, setQuality] = useState<QualityReport | null>(null)
  const [qualitySource, setQualitySource] = useState('')
  const [qualityBusy, setQualityBusy] = useState(false)
  const [auditFilter, setAuditFilter] = useState('all')


  async function refresh() {
    // Never present zero as a real database result when the request failed.
    setDataStatus('loading')
    try {
      const [newSummary, newImports] = await Promise.all([
        callApi<Summary>('/api/summary'), callApi<ImportRun[]>('/api/imports')
      ])
      setSummary(newSummary); setImports(newImports)
      setCatalogReload(n => n + 1)
      setDataStatus('ready')
      setError('')
    } catch (e) {
      setDataStatus('error')
      setError(apiErrorMessage(e, 'Verbindung zum Backend fehlgeschlagen'))
    }
  }
  useEffect(() => { void refresh() }, [])

  // The API searches the complete catalog, not just the first 100 records.
  // Debounce typing and cancel stale requests so older results cannot overwrite newer filters.
  useEffect(() => {
    if (page !== 'catalog') return
    const controller = new AbortController()
    setCatalogStatus('loading')
    const timer = window.setTimeout(async () => {
      const params = new URLSearchParams({
        search: catalogQuery.trim(), sort: catalogSort,
        offset: String(catalogOffset), limit: String(CATALOG_PAGE_SIZE)
      })
      if (catalogSource) params.set('source', catalogSource)
      try {
        const response = await callApi<CatalogResponse>(`/api/catalog/offers?${params}`, { signal: controller.signal })
        if (controller.signal.aborted) return
        setCatalog(response)
        setCatalogStatus('ready')
        setCatalogError('')
        // In case records were removed while viewing a later page.
        if (response.total > 0 && catalogOffset >= response.total) {
          setCatalogOffset(Math.floor((response.total - 1) / CATALOG_PAGE_SIZE) * CATALOG_PAGE_SIZE)
        }
      } catch (e) {
        if (controller.signal.aborted) return
        setCatalogStatus('error')
        setCatalogError(apiErrorMessage(e, 'Produktkatalog konnte nicht geladen werden'))
      }
    }, catalogQuery ? 280 : 0)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [page, catalogQuery, catalogSource, catalogSort, catalogOffset, catalogReload])

  // We keep the server as the single source of truth for catalog filters.
  // Export deliberately omits page offset, so it includes all filtered matches.
  async function exportCatalog() {
    if (catalogExportBusy) return
    setCatalogExportBusy(true)
    setError('')
    try {
      const params = new URLSearchParams({ search: catalogQuery.trim(), sort: catalogSort })
      if (catalogSource) params.set('source', catalogSource)
      const response = await fetch(`${API}/api/catalog/export.csv?${params}`)
      if (!response.ok) {
        const details: { detail?: string } = await response.json().catch(() => ({}))
        throw new Error(details.detail || `CSV-Export fehlgeschlagen (HTTP ${response.status})`)
      }
      const blob = await response.blob()
      const objectUrl = URL.createObjectURL(blob)
      try {
        const link = document.createElement('a')
        link.href = objectUrl
        link.download = 'databridge-catalog.csv'
        document.body.appendChild(link)
        link.click()
        link.remove()
      } finally {
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
      }
    } catch (e) {
      setError(apiErrorMessage(e, 'CSV-Export fehlgeschlagen'))
    } finally {
      setCatalogExportBusy(false)
    }
  }

  function closeCatalogDetail() {
    catalogDetailRequest.current += 1
    setCatalogDetailId(null)
    setCatalogDetail(null)
    detailPreviousFocus.current?.focus()
  }

  async function openCatalogDetail(offerId: number, trigger: HTMLElement) {
    const requestId = ++catalogDetailRequest.current
    detailPreviousFocus.current = trigger
    setCatalogDetailId(offerId)
    setCatalogDetail(null)
    setCatalogDetailError('')
    setCatalogDetailStatus('loading')
    try {
      const data = await callApi<OfferLineage>(`/api/offers/${offerId}/lineage`)
      if (catalogDetailRequest.current !== requestId) return
      setCatalogDetail(data)
      setCatalogDetailStatus('ready')
    } catch (e) {
      if (catalogDetailRequest.current !== requestId) return
      setCatalogDetailError(apiErrorMessage(e, 'Produktdetails konnten nicht geladen werden'))
      setCatalogDetailStatus('error')
    }
  }

  useEffect(() => {
    if (catalogDetailId === null) return
    detailCloseButton.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeCatalogDetail()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [catalogDetailId])

  async function selectFile(selected: File | undefined) {
    if (!selected) return
    setError(''); setLastRun(null); setIssues([]); setFile(null); setPreview(null)
    if (!selected.name.toLowerCase().endsWith('.csv')) {
      setError('Bitte eine CSV-Datei mit der Endung .csv auswählen.')
      return
    }
    if (selected.size > 5 * 1024 * 1024) {
      setError('Diese Datei überschreitet das Uploadlimit von 5 MB.')
      return
    }
    setFile(selected)
    const form = new FormData(); form.append('file', selected)
    setBusy(true)
    try {
      const result = await callApi<Preview>('/api/imports/preview', { method: 'POST', body: form })
      setPreview(result); setMapping(result.suggested_mapping)
    } catch (e) { setError(e instanceof Error ? e.message : 'Vorschau fehlgeschlagen') }
    finally { setBusy(false) }
  }

  async function startImport() {
    if (!file || !preview) return
    setError(''); setBusy(true)
    const form = new FormData()
    form.append('file', file); form.append('source_name', sourceName)
    form.append('mapping_json', JSON.stringify(Object.fromEntries(Object.entries(mapping).filter(([, v]) => Boolean(v)))))
    try {
      const run = await callApi<ImportRun>('/api/imports/upload', { method: 'POST', body: form })
      setLastRun(run)
      setIssues(await callApi<Issue[]>(`/api/imports/${run.id}/issues`))
      await refresh()
    } catch (e) { setError(e instanceof Error ? e.message : 'Import fehlgeschlagen') }
    finally { setBusy(false) }
  }

  async function previewApi() {
    setError(''); setDemoBusy(true); setDemoRun(null); setDemoIssues([])
    try {
      setDemoPreview(await callApi<DemoPreview>('/api/connectors/dummyjson/preview'))
    } catch (e) { setError(e instanceof Error ? e.message : 'API-Vorschau fehlgeschlagen') }
    finally { setDemoBusy(false) }
  }

  async function importApi() {
    setError(''); setDemoBusy(true)
    try {
      const run = await callApi<ImportRun>('/api/imports/dummyjson', { method: 'POST' })
      setDemoRun(run)
      setDemoIssues(await callApi<Issue[]>(`/api/imports/${run.id}/issues`))
      await refresh()
    } catch (e) { setError(e instanceof Error ? e.message : 'API-Import fehlgeschlagen') }
    finally { setDemoBusy(false) }
  }

  async function inspectOffer(offerId: number) {
    setError(''); setSelectedOffer(null); setDetailBusy(true); setPage('lineage')
    try { setSelectedOffer(await callApi<OfferLineage>(`/api/offers/${offerId}/lineage`)) }
    catch (e) { setError(e instanceof Error ? e.message : 'Datenherkunft konnte nicht geladen werden') }
    finally { setDetailBusy(false) }
  }

  async function inspectRun(runId: number, offset = 0) {
    setError(''); setSelectedRun(null); setDetailBusy(true); setPage('runs')
    if (offset === 0) setAuditFilter('all')
    try { setSelectedRun(await callApi<RunRows>(`/api/imports/${runId}/rows?offset=${offset}&limit=50`)) }
    catch (e) { setError(e instanceof Error ? e.message : 'Importdetails konnten nicht geladen werden') }
    finally { setDetailBusy(false) }
  }

  async function refreshPipeline() {
    try {
      const [current, history] = await Promise.all([
        callApi<Pipeline>('/api/pipelines/dummyjson'),
        callApi<Execution[]>('/api/pipelines/dummyjson/executions')
      ])
      setPipeline(current); setExecutions(history)
    } catch (e) { setError(e instanceof Error ? e.message : 'Pipeline-Status konnte nicht geladen werden') }
  }

  useEffect(() => {
    if (page !== 'pipeline') return
    void refreshPipeline()
    const timer = window.setInterval(() => { void refreshPipeline() }, 5000)
    return () => window.clearInterval(timer)
  }, [page])

  useEffect(() => {
    if (pipeline) setIntervalMinutes(pipeline.interval_minutes)
  }, [pipeline?.interval_minutes])

  async function configurePipeline(enabled: boolean) {
    setError(''); setPipelineBusy(true)
    try {
      const updated = await callApi<Pipeline>('/api/pipelines/dummyjson', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled, interval_minutes: intervalMinutes })
      })
      setPipeline(updated); await refreshPipeline()
    } catch (e) { setError(e instanceof Error ? e.message : 'Zeitplan konnte nicht gespeichert werden') }
    finally { setPipelineBusy(false) }
  }

  async function runPipelineNow() {
    setError(''); setPipelineBusy(true)
    try {
      await callApi('/api/pipelines/dummyjson/run-now', { method: 'POST' })
      await refreshPipeline()
    } catch (e) { setError(e instanceof Error ? e.message : 'Auftrag konnte nicht vorgemerkt werden') }
    finally { setPipelineBusy(false) }
  }

  useEffect(() => {
    if (page !== 'quality') return
    let cancelled = false
    setQualityBusy(true)
    callApi<QualityReport>(`/api/analytics/quality${qualitySource ? `?source=${encodeURIComponent(qualitySource)}` : ''}`)
      .then(report => { if (!cancelled) { setQuality(report); setError('') } })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Qualitätsanalyse fehlgeschlagen') })
      .finally(() => { if (!cancelled) setQualityBusy(false) })
    return () => { cancelled = true }
  }, [page, qualitySource])

  const canImport = !!file && !!preview && !!sourceName.trim() && !!mapping.external_id && !!mapping.name && !!mapping.price_eur &&
    new Set(Object.values(mapping).filter(Boolean)).size === Object.values(mapping).filter(Boolean).length

  const visibleAuditRows = selectedRun ? selectedRun.rows.filter(row => auditFilter === 'all' || row.action === auditFilter) : []
  const hasCsvImport = imports.some(run => run.filename.toLowerCase().endsWith('.csv'))
  const hasApiImport = imports.some(run => run.source_name === 'DummyJSON Demo')
  const hasChanges = imports.some(run => run.updated > 0)

  const nav = [{ key: 'overview' as Page, icon: '▤', title: 'Übersicht' }, { key: 'imports' as Page, icon: '⇪', title: 'Daten importieren' }, { key: 'api' as Page, icon: '⇄', title: 'API-Connector' }, { key: 'pipeline' as Page, icon: '◷', title: 'Automatisierung' }, { key: 'quality' as Page, icon: '◈', title: 'Datenqualität' }, { key: 'runs' as Page, icon: '▤', title: 'Importhistorie' }, { key: 'catalog' as Page, icon: '▦', title: 'Produktkatalog' }]

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Glyph name="brand" /></div><div><strong>DataBridge</strong><small>DATA OPERATIONS</small></div></div>
      <div className="sidebar-label">WORKSPACE</div>
      <nav aria-label="Hauptnavigation">
        {nav.map(x => <button key={x.key} className={`nav-link ${page === x.key ? 'active' : ''}`} onClick={() => { setPage(x.key); setError('') }}><span className="nav-icon"><Glyph name={x.key} /></span>{x.title}</button>)}
      </nav>
      <div className="sidebar-bottom"><span className="pulse" /> LOCAL DEVELOPMENT <small>v0.6.2 · Portfolio MVP</small></div>
    </aside>
    <main className="content">
      <header className="topbar"><div><span>Workspace</span><span className="crumb">/</span><strong>{page === 'lineage' ? 'Datenherkunft' : nav.find(x => x.key === page)?.title}</strong></div><span className="env-tag"><span className="env-dot" />ENTWICKLUNG</span></header>
      <div className="page-area">
        {error && <div role="alert" className="alert"><strong>Hinweis</strong> — {error}{dataStatus === 'error' && <button className="alert-retry" onClick={() => void refresh()}>Erneut verbinden ↻</button>}<button aria-label="Schließen" onClick={() => setError('')}>×</button></div>}
        {page === 'overview' && <>
          <div className="heading"><div className="eyebrow">DATA OPERATIONS CONTROL CENTER</div><h1>Steuerzentrale für Datenprozesse</h1><p>Importläufe, Datenqualität und Produktdaten zentral steuern, überwachen und optimieren.</p></div>
          <div className="metrics">
            {[['PRODUKTANGEBOTE', summary.offers, 'layers'], ['IMPORTVORGÄNGE', summary.imports, 'imports'], ['PRÜFFÄLLE', summary.issues, 'issues'], ['DATENQUELLEN', summary.sources, 'sources']].map(x => <div className="metric panel" key={x[0]}><div className="metric-header"><span>{x[0]}</span><span className="metric-icon"><Glyph name={String(x[2])} /></span></div><strong aria-busy={dataStatus === 'loading'}>{dataStatus === 'ready' ? x[1] : '–'}</strong><small>{dataStatus === 'error' ? 'Daten nicht verfügbar' : dataStatus === 'loading' ? 'Daten werden geladen' : 'Aktuelle Datenbankwerte'}</small></div>)}
          </div>
          {dataStatus === 'ready' && <section className="panel section demo-tour" aria-label="Demo-Rundgang">
            <div className="section-heading"><div><h2>Projekt-Demo in 3 Schritten</h2><p>CSV-Erfassung, API-Anbindung und nachvollziehbare Datenänderungen im Überblick.</p></div><span className="tour-progress">{Number(hasCsvImport) + Number(hasApiImport) + Number(hasChanges)} / 3 abgeschlossen</span></div>
            <div className="tour-grid">
              <button className="tour-card" onClick={() => setPage('imports')}><span className={hasCsvImport ? 'tour-check done' : 'tour-check'}>{hasCsvImport ? '✓' : '1'}</span><strong>CSV-Daten prüfen</strong><small>Mapping, Validierung und abgelehnte Zeilen</small><span className="tour-action">Import ansehen ↗</span></button>
              <button className="tour-card" onClick={() => setPage('api')}><span className={hasApiImport ? 'tour-check done' : 'tour-check'}>{hasApiImport ? '✓' : '2'}</span><strong>API-Daten erfassen</strong><small>Externe JSON-Daten über den Connector</small><span className="tour-action">Connector öffnen ↗</span></button>
              <button className="tour-card" onClick={() => setPage('runs')}><span className={hasChanges ? 'tour-check done' : 'tour-check'}>{hasChanges ? '✓' : '3'}</span><strong>Änderungen nachvollziehen</strong><small>Originalwerte, Aktualisierungen und Audit-Historie</small><span className="tour-action">Historie öffnen ↗</span></button>
            </div>
          </section>}
          <div className="twocol">
            <section className="panel section"><div className="section-heading"><div><h2>Letzte Importvorgänge</h2><p>Verlauf der verarbeiteten Datensätze</p></div><button className="subtle-btn" onClick={() => setPage('imports')}>Import starten ↗</button></div>
              {dataStatus !== 'ready' ? <div className="empty"><div>◌</div><strong>{dataStatus === 'error' ? 'Importhistorie nicht erreichbar' : 'Importhistorie wird geladen'}</strong><p>{dataStatus === 'error' ? 'Bitte die Verbindung prüfen und erneut versuchen.' : 'Wir laden deine letzten Importvorgänge.'}</p></div> : imports.length === 0 ? <div className="empty"><div>⇪</div><strong>Noch keine Daten importiert</strong><p>Beginne mit der Beispiel-CSV aus dem Ordner demo-data.</p><button className="primary-btn" onClick={() => setPage('imports')}>Ersten Import starten</button></div> : <div className="table-scroll"><table><thead><tr><th>QUELLE</th><th>STATUS</th><th>ZEILEN</th><th>NEU</th><th>DETAIL</th></tr></thead><tbody>{imports.slice(0, 7).map(run => <tr key={run.id}><td><strong>{run.source_name}</strong><small>{run.filename}</small></td><td><Status state={run.status} /></td><td>{run.total_rows}</td><td>{run.inserted}</td><td><button className="mini-link" onClick={() => void inspectRun(run.id)}>Ansehen ↗</button></td></tr>)}</tbody></table></div>}
            </section>
            <section className="panel section"><div className="section-heading"><div><h2>Pipeline-Architektur</h2><p>Gemeinsame Pipeline für CSV und REST API</p></div></div><div className="steps">{[['01','EXTRACT','CSV-Datei lesen oder REST API abfragen'],['02','NORMALIZE','Felder zuordnen und Werte bereinigen'],['03','VALIDATE','Datenregeln prüfen'],['04','LOAD','Angebote konsistent speichern']].map((s, i) => <div key={s[0]} className="step"><span className="step-number">{s[0]}</span><div><strong>{s[1]}</strong><small>{s[2]}</small></div><span className="step-right">{i < 3 ? '↓' : '✓'}</span></div>)}</div><div className="note">Jeder Datensatz behält seinen ursprünglichen Quellwert. Validierungsfehler werden pro Import dokumentiert.</div></section>
          </div>
        </>}
        {page === 'imports' && <>
          <div className="heading"><div className="eyebrow">DATENINTEGRATION</div><h1>Datenimport</h1><p>CSV-Dateien erfassen, Spalten zuordnen und Datensätze vor der Übernahme validieren.</p></div>
          <div className="import-grid">
            <div className="panel section">
              <div className="section-heading"><div><h2>01 / Datenquelle</h2><p>Importiere eine UTF-8-CSV-Datei (maximal 5 MB)</p></div></div>
              <label className="field-label" htmlFor="source-name">Name der Datenquelle</label><input id="source-name" value={sourceName} onChange={e => setSourceName(e.target.value)} maxLength={100} placeholder="z.B. Lieferant A" />
              <label className="dropzone"><input type="file" accept=".csv,text/csv" onChange={e => void selectFile(e.target.files?.[0])} /><span className="upload-symbol">⇧</span><strong>{file?.name ?? 'CSV-Datei auswählen'}</strong><small>{file ? `${(file.size / 1024).toFixed(1)} KB · ${preview?.total_rows ?? '…'} Datenzeilen` : 'Klicken, um eine CSV-Datei auszuwählen'}</small></label>
              {busy && <div className="loading">Verarbeite Daten …</div>}
              {preview && <><div className="section-heading with-top"><div><h2>02 / Spalten zuordnen</h2><p>Welche Quellspalte gehört zu welchem Zielfeld?</p></div></div>
                <div className="mapping-list">{(Object.entries(names) as [keyof Mapping, string][]).map(([key, label]) => <label key={key} className="mapping-row"><span>{label}</span><select value={mapping[key]} onChange={e => setMapping(m => ({ ...m, [key]: e.target.value }))}><option value="">{key === 'stock' ? 'Nicht zuordnen' : 'Spalte auswählen'}</option>{preview.headers.map(h => <option key={h} value={h}>{h}</option>)}</select></label>)}</div>
                <button className="primary-btn full" disabled={!canImport || busy} onClick={() => void startImport()}>{busy ? 'Importiere …' : 'Validieren und importieren →'}</button></>}
            </div>
            <div className="panel section"><div className="section-heading"><div><h2>Importvorschau</h2><p>{preview ? `${preview.total_rows} Zeilen · ${preview.headers.length} Spalten` : 'Noch keine Daten ausgewählt'}</p></div></div>
              {!preview ? <div className="empty"><div>▤</div><strong>Bereit für Daten</strong><p>Wähle links eine CSV-Datei aus, um ihre Struktur zu analysieren.</p></div> : <div className="table-scroll"><table><thead><tr>{preview.headers.map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{preview.preview.map((r, i) => <tr key={i}>{preview.headers.map(h => <td key={h}>{r[h]}</td>)}</tr>)}</tbody></table></div>}
              {lastRun && <div className="result"><div className="result-title"><span className="result-check">✓</span><strong>Import #{lastRun.id} verarbeitet</strong></div><div className="result-stats">{[['Neu', lastRun.inserted], ['Aktualisiert', lastRun.updated], ['Unverändert', lastRun.unchanged], ['Abgelehnt', lastRun.rejected]].map(([label, count]) => <div key={label}><strong>{count}</strong><small>{label}</small></div>)}</div>
                <button className="subtle-btn" onClick={() => void inspectRun(lastRun.id)}>Importlauf detailliert ansehen ↗</button>{issues.length > 0 && <><h3>Prüffälle</h3><div className="issue-list">{issues.slice(0, 30).map((issue, i) => <div key={i} className="issue"><span>Zeile {issue.row_number}</span><div><strong>{issue.field}</strong><small>{issue.message}</small></div></div>)}</div></>}
              </div>}
            </div>
          </div>
        </>}
        {page === 'api' && <>
          <div className="heading"><div className="eyebrow">DATENQUELLEN</div><h1>API-Connector</h1><p>Externe JSON-Daten abrufen, vereinheitlichen und über die zentrale Pipeline verarbeiten.</p></div>
          <div className="import-grid">
            <section className="panel section">
              <div className="section-heading"><div><h2>01 / Datenquelle verbinden</h2><p>Vorkonfigurierter, sicherer Demo-Connector – ohne API-Key.</p></div></div>
              <div className="connector-details"><span className="connector-symbol">⇄</span><div><strong>DummyJSON Products API</strong><small>https://dummyjson.com/products</small><small>Maximal 20 Beispielprodukte pro Anfrage</small></div></div>
              <p className="connector-explanation">Anders als beim CSV-Import ruft unser <strong>Python-Backend</strong> eine externe REST-API auf, prüft die JSON-Struktur und gibt jeden Datensatz an die gemeinsame Import-Engine weiter.</p>
              <div className="note">Die Produkte sind künstliche Testdaten, keine echten Lieferantenangebote. Die API weist keine verlässliche Preiswährung aus – wir speichern deshalb keine erfundenen EUR-Preise.</div>
              <div className="connector-actions"><button className="subtle-btn" disabled={demoBusy} onClick={() => void previewApi()}>{demoBusy ? 'Lädt …' : 'API-Vorschau laden ↻'}</button><button className="primary-btn" disabled={demoBusy} onClick={() => void importApi()}>{demoBusy ? 'Import läuft …' : '20 Produkte importieren →'}</button></div>
            </section>
            <section className="panel section"><div className="section-heading"><div><h2>02 / JSON-Vorschau und Import</h2><p>{demoPreview ? `${demoPreview.total_rows} Produkte vom externen API-Endpunkt` : 'Noch keine API-Daten abgerufen'}</p></div></div>
              {!demoPreview ? <div className="empty"><div>⇄</div><strong>Bereit für REST-Daten</strong><p>Klicke links auf „API-Vorschau laden“, um echte HTTP-Daten über unser Backend abzurufen.</p></div> : <div className="table-scroll"><table><thead><tr><th>API ID</th><th>PRODUKT</th><th>DEMO-PREIS*</th><th>BESTAND</th></tr></thead><tbody>{demoPreview.preview.map(item => <tr key={item.id}><td>{item.id}</td><td><strong>{item.title}</strong></td><td>{item.price}</td><td>{item.stock}</td></tr>)}</tbody></table><p className="table-note">* Zahlenwert aus DummyJSON, ohne belegte Währung. Kein Euro-Preis.</p></div>}
              {demoRun && <div className="result"><div className="result-title"><span className="result-check">✓</span><strong>API-Import #{demoRun.id} verarbeitet</strong></div><div className="result-stats">{[['Neu',demoRun.inserted],['Aktualisiert',demoRun.updated],['Unverändert',demoRun.unchanged],['Abgelehnt',demoRun.rejected]].map(([label,count]) => <div key={label}><strong>{count}</strong><small>{label}</small></div>)}</div><button className="subtle-btn" onClick={() => void inspectRun(demoRun.id)}>API-Import detailliert ansehen ↗</button>{demoIssues.length>0 && <><h3>Prüffälle</h3><div className="issue-list">{demoIssues.map((issue,i)=><div className="issue" key={i}><span>Eintrag {issue.row_number}</span><div><strong>{issue.field}</strong><small>{issue.message}</small></div></div>)}</div></>}</div>}
            </section>
          </div>
        </>}
        {page === 'pipeline' && <>
          <div className="heading"><div className="eyebrow">PROZESSÜBERWACHUNG</div><h1>Pipeline-Monitoring</h1><p>Geplante API-Abfragen, kontrollierte Wiederholungen und dokumentierte Ausführungen.</p></div>
          <div className="twocol">
            <section className="panel section">
              <div className="section-heading"><div><h2>Zeitgesteuerter API-Import</h2><p>Fest konfigurierte Quelle: DummyJSON Products (20 Demo-Produkte)</p></div><span className={`action-tag ${pipeline?.enabled ? 'inserted' : 'unchanged'}`}>{pipeline?.enabled ? 'Aktiviert' : 'Deaktiviert'}</span></div>
              <div className="connector-details"><div className="connector-symbol">◷</div><div><strong>DummyJSON / Products</strong><small>Serverseitiger Worker · Feste URL · Keine individuellen API-Schlüssel</small></div></div>
              <p className="connector-explanation">Die Automatik wird erst durch deine ausdrückliche Aktivierung gestartet. Bei einem Fehler speichert DataBridge den Versuch, zeigt die Ursache und plant eine begrenzte Wiederholung.</p>
              <label className="field-label" htmlFor="interval">Abrufintervall</label>
              <select id="interval" value={intervalMinutes} disabled={pipelineBusy || pipeline?.status === 'running'} onChange={e => setIntervalMinutes(Number(e.target.value))}>
                <option value={5}>Alle 5 Minuten (lokaler Funktionstest)</option>
                <option value={15}>Alle 15 Minuten</option>
                <option value={60}>Alle 60 Minuten</option>
                <option value={360}>Alle 6 Stunden</option>
                <option value={1440}>Täglich</option>
              </select>
              <div className="connector-actions">
                <button className="primary-btn" disabled={pipelineBusy || pipeline?.status === 'running'} onClick={() => void configurePipeline(!pipeline?.enabled)}>{pipelineBusy ? 'Speichert …' : pipeline?.enabled ? 'Automatik deaktivieren' : 'Automatik aktivieren'}</button>
                {pipeline?.enabled && <><button className="subtle-btn" disabled={pipelineBusy || pipeline?.status === 'running'} onClick={() => void configurePipeline(true)}>Intervall speichern</button><button className="subtle-btn" disabled={pipelineBusy || pipeline?.status === 'running' || pipeline?.next_run_at === null} onClick={() => void runPipelineNow()}>Jetzt ausführen ↗</button></>}
              </div>
              <div className="note">Nur lokale Demo: Ohne Anmeldung/Autorisierung darf dieser Endpunkt nicht öffentlich betrieben werden. „Jetzt ausführen“ reiht einen Auftrag ein; der separate Worker übernimmt ihn üblicherweise beim nächsten Poll.</div>
            </section>
            <section className="panel section">
              <div className="section-heading"><div><h2>Betriebszustand</h2><p>Persistenter Zeitplan aus PostgreSQL</p></div><button className="subtle-btn" onClick={() => void refreshPipeline()}>Aktualisieren ↻</button></div>
              <div className="monitor-rows">
                {[
                  ['Status', ({not_configured:'Nicht konfiguriert', idle:'Wartet', running:'Verarbeitet', completed:'Erfolgreich', failed:'Fehlgeschlagen'} as Record<string,string>)[pipeline?.status ?? 'not_configured'] ?? pipeline?.status ?? '–'],
                  ['Nächster Abruf', formatDate(pipeline?.next_run_at ?? null)],
                  ['Letzter Versuch', formatDate(pipeline?.last_attempt_at ?? null)],
                  ['Letzter Erfolg', formatDate(pipeline?.last_success_at ?? null)],
                  ['Fehler in Folge', pipeline?.consecutive_failures ?? 0],
                ].map(([label,value]) => <div className="monitor-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}
              </div>
              {pipeline?.last_error && <div className="audit-error" role="alert">Letzter Fehler: {pipeline.last_error}</div>}
              {pipeline?.status === 'failed' && <p className="audit-hint">Bei wiederholten Fehlern steigt die Wartezeit schrittweise bis maximal 15 Minuten. Danach wird erneut versucht.</p>}
            </section>
          </div>
          <section className="panel section detail-panel"><div className="section-heading"><div><h2>Ausführungsprotokoll</h2><p>Letzte 40 automatische Versuche · Aktualisierung alle 5 Sekunden</p></div></div>
            {executions.length === 0 ? <div className="empty"><div>◷</div><strong>Noch keine automatischen Ausführungen</strong><p>Aktiviere die Automatik und klicke auf „Jetzt ausführen“, um den ersten Lauf zu testen.</p></div> : <div className="table-scroll"><table><thead><tr><th>VERSUCH</th><th>START</th><th>STATUS</th><th>IMPORT</th><th>ERGEBNIS</th></tr></thead><tbody>
              {executions.map(exec => <tr key={exec.id}><td><strong>#{exec.id}</strong></td><td>{formatDate(exec.started_at)}</td><td><span className={`action-tag ${exec.status === 'completed' ? 'inserted' : exec.status === 'failed' ? 'rejected' : 'updated'}`}>{exec.status === 'completed' ? 'Erfolgreich' : exec.status === 'failed' ? 'Fehler' : 'Läuft'}</span></td><td>{exec.import_id ? <button className="mini-link" onClick={() => void inspectRun(exec.import_id!)}>Import #{exec.import_id} ↗</button> : '–'}</td><td className="monitor-error-cell">{exec.error || (exec.finished_at ? `Beendet: ${formatDate(exec.finished_at)}` : 'Wird verarbeitet …')}</td></tr>)}
            </tbody></table></div>}
          </section>
        </>}
        {page === 'quality' && <>
          <div className="heading"><div className="eyebrow">QUALITÄTSANALYSE</div><h1>Datenqualität</h1><p>Validierungsergebnisse und Qualitätskennzahlen auf Basis abgeschlossener Importläufe.</p></div>
          <section className="panel section quality-filter">
            <div><label htmlFor="quality-source" className="field-label">Datenquelle auswählen</label>
              <select id="quality-source" value={qualitySource} onChange={e => setQualitySource(e.target.value)}>
                <option value="">Alle Datenquellen</option>
                {quality?.available_sources.map(source => <option key={source} value={source}>{source}</option>)}
              </select>
            </div>
            <p className="audit-hint">Berechnet über alle abgeschlossenen Importläufe im gewählten Umfang. Wiederholte Imports zählen erneut als verarbeitete Zeilen, nicht als neue Produkte.</p>
          </section>
          {qualityBusy && <p className="loading">Berechne Qualitätskennzahlen …</p>}
          {quality && <>
            <div className="metrics quality-metrics">
              {[
                ['VERARBEITETE ZEILEN', quality.total_rows, '▤'],
                ['AKZEPTIERTE ZEILEN', quality.accepted, '✓'],
                ['ABGELEHNTE ZEILEN', quality.rejected, '!'],
                ['ANNAHMEQUOTE', displayQuality(quality.quality_percent), '◈'],
              ].map(m => <div className="metric panel" key={m[0]}><div className="metric-header"><span>{m[0]}</span><span className="metric-icon">{m[2]}</span></div><strong>{m[1]}</strong><small>Gemessen aus {quality.total_runs} Importläufen</small></div>)}
            </div>
            <div className="twocol">
              <section className="panel section">
                <div className="section-heading"><div><h2>Annahmequote je Quelle</h2><p>Gültige Zeilen geteilt durch gelesene Quellzeilen</p></div></div>
                {quality.by_source.length === 0 ? <div className="empty"><strong>Keine Imports vorhanden</strong><p>Importiere zunächst Daten über CSV oder API.</p></div> : <div className="quality-sources">
                  {quality.by_source.map(source => <div className="quality-source" key={source.source_name}>
                    <div className="quality-source-header"><strong>{source.source_name}</strong><span>{displayQuality(source.quality_percent)}</span></div>
                    <div className="quality-bar"><div style={{ width: `${source.quality_percent ?? 0}%` }} /></div>
                    <small>{source.accepted} akzeptiert · {source.rejected} abgelehnt · {source.runs} Läufe</small>
                  </div>)}
                </div>}
              </section>
              <section className="panel section">
                <div className="section-heading"><div><h2>Häufigste Prüfprobleme</h2><p>Fehler nach Feld und Fehlercode, nicht nur nach Zeilen</p></div></div>
                {quality.top_issues.length === 0 ? <div className="empty"><strong>Keine Validierungsfehler</strong><p>Für diesen Filter wurden keine Prüffälle gespeichert.</p></div> : <div className="table-scroll"><table><thead><tr><th>FELD</th><th>FEHLERCODE</th><th>ANZAHL</th></tr></thead><tbody>
                  {quality.top_issues.map(issue => <tr key={`${issue.field}:${issue.code}`}><td><strong>{fieldText[issue.field] ?? issue.field}</strong></td><td>{issue.code}</td><td>{issue.count}</td></tr>)}
                </tbody></table></div>}
              </section>
            </div>
            <section className="panel section detail-panel"><div className="section-heading"><div><h2>Letzte 15 Importläufe</h2><p>Inklusive Zeitstempel, Annahmequote und Direktlink zur Datenherkunft</p></div></div>
              {quality.recent_runs.length === 0 ? <div className="empty"><strong>Noch keine Importhistorie</strong></div> : <div className="table-scroll"><table><thead><tr><th>IMPORT</th><th>QUELLE</th><th>ZEILEN</th><th>AKZEPTIERT</th><th>ABGELEHNT</th><th>QUOTE</th><th>DETAILS</th></tr></thead><tbody>
                {quality.recent_runs.map(run => <tr key={run.id}><td><strong>#{run.id}</strong><small>{formatDate(run.created_at)}</small></td><td>{run.source_name}</td><td>{run.total_rows}</td><td>{run.accepted}</td><td>{run.rejected}</td><td><strong>{displayQuality(run.quality_percent)}</strong></td><td><button className="mini-link" onClick={() => void inspectRun(run.id)}>Ansehen ↗</button></td></tr>)}
              </tbody></table></div>}
            </section>
            <div className="note">Die Annahmequote ist eine technische Validierungskennzahl, kein universeller Qualitäts- oder Vertrauensscore. Fehlende historische Daten, Dubletten zwischen unterschiedlichen Quellen und semantische Fehler können damit nicht ausgeschlossen werden.</div>
          </>}
        </>}
        {page === 'catalog' && <>
          <div className="heading"><div className="eyebrow">NORMALISIERTE PRODUKTDATEN</div><h1>Produktkatalog</h1><p>Lieferantenangebote datenbankgestützt durchsuchen, filtern, sortieren und exportieren.</p></div>
          <div className="panel section">
            <div className="section-heading"><div><h2>Lieferantenangebote</h2><p>{catalogStatus === 'ready' && catalog ? `${catalog.total} Treffer · ${summary.offers} Angebote insgesamt` : 'Daten werden aus PostgreSQL geladen'}</p></div><div className="catalog-heading-actions"><button className="subtle-btn" disabled={catalogExportBusy || catalogStatus !== 'ready' || !catalog || catalog.total === 0} onClick={() => void exportCatalog()}>{catalogExportBusy ? 'Exportiere …' : 'CSV exportieren ↓'}</button><button className="subtle-btn" onClick={() => setCatalogReload(n => n + 1)}>Aktualisieren ↻</button></div></div>
            <div className="catalog-toolbar">
              <label className="catalog-search"><span>Produktname oder externe ID</span><input type="search" aria-label="Produktname oder externe ID suchen" placeholder="z. B. USB-C oder A-1001 ..." value={catalogQuery} maxLength={100} onChange={e => { setCatalogQuery(e.target.value); setCatalogOffset(0) }} /></label>
              <label className="catalog-select"><span>Datenquelle</span><select aria-label="Datenquelle filtern" value={catalogSource} onChange={e => { setCatalogSource(e.target.value); setCatalogOffset(0) }}><option value="">Alle Quellen</option>{(catalog?.sources ?? []).map(source => <option key={source} value={source}>{source}</option>)}</select></label>
              <label className="catalog-select"><span>Sortierung</span><select aria-label="Katalog sortieren" value={catalogSort} onChange={e => { setCatalogSort(e.target.value as CatalogSort); setCatalogOffset(0) }}><option value="name_asc">Produktname A–Z</option><option value="name_desc">Produktname Z–A</option><option value="stock_asc">Bestand aufsteigend</option><option value="stock_desc">Bestand absteigend</option><option value="source_asc">Datenquelle A–Z</option><option value="latest">Neueste Angebote</option></select></label>
              <button className="subtle-btn catalog-reset" disabled={!catalogQuery && !catalogSource && catalogSort === 'name_asc'} onClick={() => { setCatalogQuery(''); setCatalogSource(''); setCatalogSort('name_asc'); setCatalogOffset(0) }}>Zurücksetzen</button>
            </div>
            {catalogStatus === 'loading' && <div role="status" className="catalog-loading">Produkte werden gesucht …</div>}
            {catalogStatus === 'error' && <div className="empty" role="alert"><div>⚠</div><strong>Produktkatalog nicht erreichbar</strong><p>{catalogError}</p><button className="subtle-btn" onClick={() => setCatalogReload(n => n + 1)}>Erneut versuchen ↻</button></div>}
            {catalogStatus === 'ready' && catalog && (catalog.total === 0 ? <div className="empty"><div>⌕</div><strong>{catalogQuery || catalogSource ? 'Keine passenden Produkte' : 'Dein Katalog ist noch leer'}</strong><p>{catalogQuery || catalogSource ? 'Versuche einen anderen Suchbegriff oder setze die Filter zurück.' : 'Importiere eine Datei, damit hier Datensätze erscheinen.'}</p>{catalogQuery || catalogSource ? <button className="subtle-btn" onClick={() => { setCatalogQuery(''); setCatalogSource(''); setCatalogOffset(0) }}>Filter zurücksetzen</button> : <button className="primary-btn" onClick={() => setPage('imports')}>CSV importieren</button>}</div> : <>
              <div className="table-scroll"><table><thead><tr><th>PRODUKT</th><th>EXTERNE ID</th><th>QUELLE</th><th>PREIS / WÄHRUNG</th><th>BESTAND</th><th>DETAILS</th></tr></thead><tbody>{catalog.items.map(x => <tr key={x.id}><td><strong>{x.name}</strong></td><td>{x.external_id}</td><td>{x.source_name}</td><td><strong>{x.currency === 'EUR' ? Number(x.price_amount).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' }) : `${Number(x.price_amount).toLocaleString('de-DE')} · Demo-Wert (ohne Währung)`}</strong></td><td>{x.stock ?? '–'}</td><td><button className="mini-link" onClick={e => void openCatalogDetail(x.id, e.currentTarget)}>Details ↗</button></td></tr>)}</tbody></table></div>
              <div className="catalog-pagination"><span>Zeige {catalog.offset + 1}–{Math.min(catalog.offset + catalog.items.length, catalog.total)} von {catalog.total} Treffern</span><div><button className="subtle-btn" disabled={catalogOffset === 0} onClick={() => setCatalogOffset(Math.max(0, catalogOffset - CATALOG_PAGE_SIZE))}>← Zurück</button><span>Seite {Math.floor(catalog.offset / CATALOG_PAGE_SIZE) + 1} / {Math.ceil(catalog.total / CATALOG_PAGE_SIZE)}</span><button className="subtle-btn" disabled={catalog.offset + catalog.items.length >= catalog.total} onClick={() => setCatalogOffset(catalogOffset + CATALOG_PAGE_SIZE)}>Weiter →</button></div></div>
            </>)}
            <p className="catalog-footnote">Suche, Sortierung und CSV-Export verwenden dieselben Datenbankfilter. Der Export enthält alle Treffer (maximal 10.000), nicht nur die angezeigte Seite. Fremde Textwerte werden beim Export vor Tabellenformeln geschützt.</p>
          </div>
        </>}
        {page === 'runs' && <>
          <div className="heading"><div className="eyebrow">IMPORTPROTOKOLL</div><h1>Importhistorie</h1><p>Importläufe, Originaldaten und Validierungsergebnisse vollständig nachvollziehen.</p></div>
          <section className="panel section"><div className="section-heading"><div><h2>Importläufe</h2><p>Wähle einen Import für seine Originaldaten und Validierungsergebnisse.</p></div></div>
            {dataStatus !== 'ready' ? <p className="loading">{dataStatus === 'error' ? 'Importhistorie nicht erreichbar.' : 'Lade Importhistorie …'}</p> : imports.length === 0 ? <div className="empty"><strong>Noch keine Importläufe</strong><p>Starte einen CSV- oder API-Import, um die Verarbeitung nachzuvollziehen.</p></div> : <div className="table-scroll"><table><thead><tr><th>IMPORT</th><th>QUELLE</th><th>ZEILEN</th><th>ABGELEHNT</th><th>DETAILS</th></tr></thead><tbody>
              {imports.map(run => <tr key={run.id}><td><strong>#{run.id}</strong></td><td>{run.source_name}<small>{run.filename}</small></td><td>{run.total_rows}</td><td>{run.rejected}</td><td><button className="mini-link" onClick={() => void inspectRun(run.id)}>Öffnen ↗</button></td></tr>)}
            </tbody></table></div>}
          </section>
          {detailBusy && <p className="loading">Lade Importdetails …</p>}
          {selectedRun && <section className="panel section detail-panel">
            <div className="section-heading"><div><h2>Import #{selectedRun.run.id} · {selectedRun.run.source_name}</h2><p>{selectedRun.run.total_rows} Quellzeilen · {selectedRun.run.rejected} abgelehnt · Datensätze 1–50 je Seite</p></div><button className="subtle-btn" onClick={() => setSelectedRun(null)}>Schließen ×</button></div>
            <div className="audit-toolbar"><label htmlFor="audit-status">Zeilen filtern</label><select id="audit-status" value={auditFilter} onChange={e => setAuditFilter(e.target.value)}><option value="all">Alle Status</option><option value="inserted">Neu</option><option value="updated">Aktualisiert</option><option value="unchanged">Unverändert</option><option value="rejected">Abgelehnt</option></select><span>{visibleAuditRows.length} Treffer auf dieser Seite</span></div>
            {visibleAuditRows.length === 0 && <div className="empty"><strong>Keine passenden Zeilen</strong><p>Auf dieser Seite gibt es keine Zeilen mit diesem Status. Wechsle den Filter oder die Seite.</p></div>}
            {visibleAuditRows.map(row => <article className="audit-item" key={row.row_number}>
              <div className="audit-title"><strong>Zeile {row.row_number}</strong><span className={`action-tag ${row.action}`}>{actionText[row.action] ?? row.action}</span>{row.offer_id !== null && <button className="mini-link" onClick={() => void inspectOffer(row.offer_id!)}>Produkt ansehen ↗</button>}</div>
              <div className="audit-grid"><div><h3>Originaldaten</h3><pre>{pretty(row.raw)}</pre></div><div><h3>Normalisierter Datensatz</h3>{row.normalized ? <pre>{pretty(row.normalized)}</pre> : <p className="audit-hint">{row.issues.length ? 'Ungültige Eingabe – keine Speicherung' : 'Historie vor v0.3 nicht verfügbar. Erneut importieren.'}</p>}</div></div>
              {row.issues.map((issue, i) => <div className="audit-error" key={i}>{issue.field}: {issue.message}</div>)}
            </article>)}
            <div className="pagination"><button className="subtle-btn" disabled={detailBusy || selectedRun.offset === 0} onClick={() => void inspectRun(selectedRun.run.id, Math.max(0, selectedRun.offset - 50))}>← Zurück</button><span>Seite {Math.floor(selectedRun.offset / selectedRun.limit) + 1} von {Math.max(1, Math.ceil(selectedRun.run.total_rows / selectedRun.limit))} · Zeige {selectedRun.rows.length ? selectedRun.offset + 1 : 0}–{selectedRun.offset + selectedRun.rows.length} von {selectedRun.run.total_rows} Zeilen</span><button className="subtle-btn" disabled={detailBusy || selectedRun.offset + selectedRun.rows.length >= selectedRun.run.total_rows} onClick={() => void inspectRun(selectedRun.run.id, selectedRun.offset + 50)}>Weitere 50 →</button></div>
          </section>}
        </>}
        {page === 'lineage' && <>
          <div className="heading"><div className="eyebrow">DATA LINEAGE</div><h1>Datenherkunft</h1><p>Quellinformationen, normalisierte Werte und dokumentierte Zustandsänderungen.</p></div>
          <button className="subtle-btn back-btn" onClick={() => setPage('catalog')}>← Zurück zum Produktkatalog</button>
          {detailBusy && <p className="loading">Lade Herkunft …</p>}
          {selectedOffer && <>
            <section className="panel section"><div className="section-heading"><div><h2>{selectedOffer.offer.name}</h2><p>{selectedOffer.offer.source_name} · Externe ID {selectedOffer.offer.external_id} · Angebot #{selectedOffer.offer.id}</p></div><span className="action-tag">Aktueller Stand</span></div>
              <div className="snapshot-grid">{Object.entries({Preis:selectedOffer.offer.price_amount, Währung:selectedOffer.offer.currency, Bestand:selectedOffer.offer.stock ?? '–', 'Letzte Zustandsänderung':`Import #${selectedOffer.offer.last_changed_import_id}`}).map(([k,v]) => <div className="snapshot" key={k}><small>{k}</small><strong>{String(v)}</strong></div>)}</div>
              <div className="note">Ereignis-Historie ab v0.3. Ältere Imports bleiben erhalten, aber für sie werden keine früheren Zustände nachträglich erfunden. Importiere die Quelle erneut, um neue Ereignisse aufzuzeichnen.</div>
            </section>
            <section className="panel section detail-panel"><div className="section-heading"><div><h2>Verarbeitungsverlauf</h2><p>{selectedOffer.events.length} dokumentierte Ereignisse (neueste zuerst)</p></div></div>
              {selectedOffer.events.length === 0 ? <div className="empty"><strong>Noch keine v0.3-Ereignisse</strong><p>Dein Produkt wurde vor dem Update angelegt. Importiere seine Quelle erneut.</p></div> : selectedOffer.events.map(event => <article className="audit-item" key={event.id}>
                <div className="audit-title"><span className={`action-tag ${event.action}`}>{actionText[event.action] ?? event.action}</span><strong>Import #{event.import_id} · Zeile {event.row_number}</strong><span className="audit-date">{new Date(event.import_created_at).toLocaleString('de-DE')}</span><button className="mini-link" onClick={() => void inspectRun(event.import_id)}>Importdetails ↗</button></div>
                <p className="audit-hint">Quelle: {event.import_filename}</p>
                {event.changed_fields.length>0 && <div className="changes">Geänderte Felder: {event.changed_fields.map(k => <span key={k}>{fieldText[k] ?? k}</span>)}</div>}
                <div className="audit-grid"><div><h3>Rohdaten der Quelle</h3><pre>{pretty(event.raw)}</pre></div><div><h3>Normalisiert & gespeichert</h3><pre>{pretty(event.after)}</pre></div></div>
                {event.action === 'updated' && event.before && <details><summary>Vorherigen Zustand und Unterschiede anzeigen</summary><div className="diff-grid">{event.changed_fields.map(key => <div key={key} className="diff-row"><strong>{fieldText[key] ?? key}</strong><span>{String(event.before?.[key] ?? '–')}</span><span>→</span><span>{String(event.after[key] ?? '–')}</span></div>)}</div><pre>{pretty(event.before)}</pre></details>}
              </article>)}
              {selectedOffer.history_limited && <p className="audit-hint">Die Anzeige ist auf die letzten 100 Ereignisse begrenzt.</p>}
            </section>
          </>}
        </>}
        <footer className="footer">DataBridge · React · FastAPI · PostgreSQL · Lokale Entwicklungsumgebung</footer>
      </div>
    </main>
    {catalogDetailId !== null && <div className="catalog-modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) closeCatalogDetail() }}>
      <section className="catalog-detail-drawer" role="dialog" aria-modal="true" aria-labelledby="catalog-detail-title" aria-describedby="catalog-detail-subtitle">
        <div className="catalog-detail-top"><div><span className="eyebrow">DATA LINEAGE / PRODUCT</span><h2 id="catalog-detail-title">{catalogDetail?.offer.name ?? 'Produktdetails'}</h2><p id="catalog-detail-subtitle">Aktuelle Werte und dokumentierte Herkunft</p></div><button className="subtle-btn catalog-detail-close" ref={detailCloseButton} onClick={closeCatalogDetail} aria-label="Produktdetails schließen">Schließen ×</button></div>
        {catalogDetailStatus === 'loading' && <div className="catalog-detail-state" role="status">Lade Produktdetails …</div>}
        {catalogDetailStatus === 'error' && <div className="catalog-detail-state" role="alert"><strong>Details konnten nicht geladen werden.</strong><p>{catalogDetailError}</p><button className="subtle-btn" onClick={e => void openCatalogDetail(catalogDetailId, e.currentTarget)}>Erneut versuchen</button></div>}
        {catalogDetailStatus === 'ready' && catalogDetail && <>
          <div className="catalog-detail-fields">
            <div><span>Datenquelle</span><strong>{catalogDetail.offer.source_name}</strong></div>
            <div><span>Externe ID</span><strong>{catalogDetail.offer.external_id}</strong></div>
            <div><span>Preis / Währung</span><strong>{catalogDetail.offer.currency === 'EUR' ? Number(catalogDetail.offer.price_amount).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' }) : `${Number(catalogDetail.offer.price_amount).toLocaleString('de-DE')} · Demo-Wert (ohne Währung)`}</strong></div>
            <div><span>Lagerbestand</span><strong>{catalogDetail.offer.stock ?? 'Nicht angegeben'}</strong></div>
            <div><span>Letzte Änderung</span><strong>Import #{catalogDetail.offer.last_changed_import_id}</strong></div>
          </div>
          <h3 className="catalog-detail-subheading">Letztes dokumentiertes Ereignis</h3>
          {catalogDetail.events.length > 0 ? <div className="catalog-detail-event"><span className={`action-tag ${catalogDetail.events[0].action}`}>{actionText[catalogDetail.events[0].action] ?? catalogDetail.events[0].action}</span><strong>Import #{catalogDetail.events[0].import_id}</strong><small>{formatDate(catalogDetail.events[0].import_created_at)}</small><p>Quelldatei: {catalogDetail.events[0].import_filename}</p><p>{catalogDetail.events[0].changed_fields.length ? `Geänderte Felder: ${catalogDetail.events[0].changed_fields.map(key => fieldText[key] ?? key).join(', ')}` : 'Keine Werte verändert'}</p></div> : <div className="catalog-detail-event"><p>Noch keine dokumentierten Ereignisse vorhanden. Für ältere Importe vor v0.3 wird keine Historie erfunden.</p></div>}
          <div className="catalog-detail-footer"><button className="primary-btn" onClick={() => { const id = catalogDetail.offer.id; closeCatalogDetail(); void inspectOffer(id) }}>Vollständigen Verlauf öffnen ↗</button></div>
        </>}
      </section>
    </div>}
  </div>
}
