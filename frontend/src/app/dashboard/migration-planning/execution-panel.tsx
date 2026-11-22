"use client";

import { useEffect, useState } from "react";
import {
  cancelMigrationRun, downloadMigrationRunCsv, getMigrationRun, getMigrationRunErrors,
  getMigrationRunEvents, getMigrationRunReport, getMigrationRunTables, listMigrationRuns, resumeMigrationRun, retryMigrationRunErrors,
  startMigrationRun, getMigrationPlanMetrics, getMigrationRunMetrics,
} from "./execution-actions";

type Run = {
  id: string; status: string; batch_size: number; write_strategy: "INSERT_ONLY" | "UPSERT";
  total_tables: number; completed_tables: number; total_rows: number; migrated_rows: number;
  worker_id?: string | null; heartbeat_at?: string | null; started_at?: string | null;
  inserted_rows: number; updated_rows: number; skipped_rows: number; failed_rows: number;
  validation_status: string; mismatch_rows: number; error_message?: string | null; created_at: string;
};

export default function ExecutionPanel({ projectId, planId, planStatus }: { projectId: string; planId: string; planStatus: string }) {
  const [batchSize, setBatchSize] = useState(1000);
  const [writeStrategy, setWriteStrategy] = useState<"INSERT_ONLY" | "UPSERT">("INSERT_ONLY");
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<Run | null>(null);
  const [tableProgress, setTableProgress] = useState<any[]>([]);
  const [rowErrors, setRowErrors] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [planMetrics, setPlanMetrics] = useState<any>(null);
  const [runMetrics, setRunMetrics] = useState<any>(null);
  const [metricsBusy, setMetricsBusy] = useState(false);

  async function refreshMetrics() {
    setMetricsBusy(true);
    try { setPlanMetrics(await getMigrationPlanMetrics(projectId, planId)); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load database size metadata."); }
    finally { setMetricsBusy(false); }
  }

  useEffect(() => {
    let active = true;
    getMigrationPlanMetrics(projectId, planId)
      .then((result) => { if (active) setPlanMetrics(result); })
      .catch((e) => { if (active) setError(e instanceof Error ? e.message : "Could not load database size metadata."); });
    return () => { active = false; };
  }, [projectId, planId]);

  async function refresh() {
    setBusy(true); setError("");
    try {
      await refreshMetrics();
      const latest = await listMigrationRuns(projectId, planId);
      setRuns(latest);
      const current = selected ? latest.find((item) => item.id === selected.id) ?? latest[0] : latest[0];
      if (current) {
        const detail = await getMigrationRun(projectId, planId, current.id);
        setSelected(detail);
        setTableProgress(await getMigrationRunTables(projectId, planId, current.id));
        setRowErrors(await getMigrationRunErrors(projectId, planId, current.id));
        setEvents(await getMigrationRunEvents(projectId, planId, current.id));
        setRunMetrics(await getMigrationRunMetrics(projectId, planId, current.id));
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Could not refresh migration runs."); }
    finally { setBusy(false); }
  }

  async function start() {
    setBusy(true); setError("");
    try {
      await refreshMetrics();
      const run = await startMigrationRun(projectId, planId, batchSize, writeStrategy);
      setSelected(run);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not queue migration."); }
    finally { setBusy(false); }
  }

  async function cancel() {
    if (!selected) return;
    setBusy(true);
    try {
      setSelected(await cancelMigrationRun(projectId, planId, selected.id));
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not request cancellation."); }
    finally { setBusy(false); }
  }

  async function retryErrors() {
    if (!selected) return;
    setBusy(true);
    try {
      setSelected(await retryMigrationRunErrors(projectId, planId, selected.id));
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not retry quarantined rows.'); }
    finally { setBusy(false); }
  }

  async function downloadReport(format: 'json' | 'csv') {
    if (!selected) return;
    try {
      const report = format === 'json' ? JSON.stringify(await getMigrationRunReport(projectId, planId, selected.id), null, 2) : await downloadMigrationRunCsv(projectId, planId, selected.id);
      const blob = new Blob([report], { type: format === 'json' ? 'application/json' : 'text/csv' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'conduit-run-' + selected.id + '.' + format;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not download report.'); }
  }

  async function resume() {
    if (!selected) return;
    setBusy(true);
    try {
      setSelected(await resumeMigrationRun(projectId, planId, selected.id));
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not resume migration."); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    if (!selected || !["queued", "running", "cancel_requested"].includes(selected.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await listMigrationRuns(projectId, planId);
        setRuns(latest);
        const current = latest.find((item) => item.id === selected.id);
        if (current) {
          const detail = await getMigrationRun(projectId, planId, current.id);
          setSelected(detail);
          setTableProgress(await getMigrationRunTables(projectId, planId, current.id));
          setRowErrors(await getMigrationRunErrors(projectId, planId, current.id));
          setEvents(await getMigrationRunEvents(projectId, planId, current.id));
          setRunMetrics(await getMigrationRunMetrics(projectId, planId, current.id));
        }
      } catch (e) { setError(e instanceof Error ? e.message : "Live status refresh failed."); }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [projectId, planId, selected?.id, selected?.status]);

  const formatBytes = (value: number | null | undefined) => {
    if (value == null) return "Unavailable";
    if (value < 1024) return `${value} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let amount = value / 1024;
    let index = 0;
    while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
    return `${amount.toFixed(2)} ${units[index]}`;
  };
  const estimatedSourceBytes = planMetrics?.tables?.filter((item:any) => item.selected).reduce((sum:number,item:any) => sum + (item.source_physical_bytes ?? 0), 0) ?? 0;
  const observedPayloadBytes = runMetrics?.run?.logical_bytes ?? 0;
  const percent = estimatedSourceBytes > 0 ? Math.min(100, Math.round(observedPayloadBytes / estimatedSourceBytes * 100)) : 0;
  const runMetric = runMetrics?.run;
  const formatRate = (value: number | null | undefined) => value == null ? "—" : `${formatBytes(value)}/s`;
  const plannedCheckpoints = planMetrics?.tables?.filter((item:any) => item.selected).reduce((sum:number,item:any) => sum + Math.ceil((item.estimated_rows ?? 0) / (selected?.batch_size ?? batchSize)), 0) ?? 0;
  const etaSeconds = runMetric?.logical_bytes_per_second > 0 && planMetrics?.tables?.length
    ? Math.max(0, (planMetrics.tables.filter((item:any) => item.selected).reduce((sum:number,item:any) => sum + (item.source_physical_bytes ?? 0), 0) - (runMetric.logical_bytes ?? 0)) / runMetric.logical_bytes_per_second)
    : null;
  return <section className="rounded-xl border bg-white p-6 shadow-sm space-y-4">
    <div><p className="text-xs font-semibold uppercase tracking-wide text-blue-700">Data execution</p><h2 className="mt-1 text-lg font-semibold">5. Run migration</h2>
      <p className="mt-1 text-sm text-slate-600">Queue a durable migration job. A separate backend worker processes queued jobs and persists checkpoints.</p></div>
    <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h3 className="text-sm font-semibold text-slate-800">Database & table footprint</h3><p className="mt-1 text-xs text-slate-500">Live PostgreSQL storage measurements and discovery metadata. Row counts are estimates.</p></div>
        <button disabled={metricsBusy} onClick={refreshMetrics} className="rounded-lg border bg-white px-3 py-2 text-xs font-medium disabled:opacity-50">{metricsBusy ? "Measuring…" : "Refresh measurements"}</button>
      </div>
      {planMetrics && <>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border bg-white p-3"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Source · {planMetrics.source?.database ?? "Database"}</p><p className="mt-1 text-xl font-semibold">{formatBytes(planMetrics.source?.physical_bytes)}</p><p className="text-xs text-slate-500">{planMetrics.source?.name}</p>{planMetrics.source?.error && <p className="mt-2 text-xs text-amber-700">{planMetrics.source.error}</p>}</div>
          <div className="rounded-lg border bg-white p-3"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Destination · {planMetrics.destination?.database ?? "Database"}</p><p className="mt-1 text-xl font-semibold">{formatBytes(planMetrics.destination?.physical_bytes)}</p><p className="text-xs text-slate-500">{planMetrics.destination?.name}</p>{planMetrics.destination?.error && <p className="mt-2 text-xs text-amber-700">{planMetrics.destination.error}</p>}</div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div><p className="text-xs text-slate-500">Selected tables</p><p className="font-semibold">{planMetrics.summary?.selected_tables ?? 0} / {planMetrics.summary?.candidate_tables ?? 0}</p></div>
          <div><p className="text-xs text-slate-500">Selected source footprint</p><p className="font-semibold">{formatBytes((planMetrics.tables ?? []).filter((item:any) => item.selected).reduce((sum:number,item:any) => sum + (item.source_physical_bytes ?? 0), 0))}</p></div>
          <div><p className="text-xs text-slate-500">Estimated source rows</p><p className="font-semibold">{(planMetrics.summary?.estimated_source_rows ?? 0).toLocaleString()}</p></div>
          <div><p className="text-xs text-slate-500">Measured</p><p className="font-semibold text-xs">{planMetrics.measured_at ? new Date(planMetrics.measured_at).toLocaleString() : "—"}</p></div>
          <div><p className="text-xs text-slate-500">Size semantics</p><p className="font-semibold text-xs">Includes indexes / TOAST</p></div>
        </div>
        <div className="mt-3 max-h-64 overflow-auto rounded-lg border bg-white"><table className="w-full min-w-[760px] text-left text-xs"><thead className="sticky top-0 border-b bg-slate-100 text-slate-600"><tr><th className="p-2">Table</th><th className="p-2">Selected</th><th className="p-2">Est. rows</th><th className="p-2">Columns / mapped</th><th className="p-2">PK columns</th><th className="p-2">Source size</th><th className="p-2">Target size</th></tr></thead><tbody>{(planMetrics.tables ?? []).map((item:any) => <tr key={item.id} className="border-b last:border-0"><td className="p-2 font-medium">{item.source}</td><td className="p-2">{item.selected ? "Yes" : "No"}</td><td className="p-2">{item.estimated_rows?.toLocaleString() ?? "—"}</td><td className="p-2">{item.column_count} / {item.mapped_columns}</td><td className="p-2">{item.primary_key_columns?.join(", ") || "Missing"}</td><td className="p-2">{formatBytes(item.source_physical_bytes)}</td><td className="p-2">{formatBytes(item.destination_physical_bytes)}</td></tr>)}</tbody></table></div>
      </>}
      {!planMetrics && <p className="mt-3 text-xs text-slate-500">Loading database and table measurements…</p>}
    </div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">Batch size <select value={batchSize} onChange={(e) => setBatchSize(Number(e.target.value))} className="ml-2 rounded border p-2"><option value={500}>500</option><option value={1000}>1,000</option><option value={2500}>2,500</option><option value={5000}>5,000</option><option value={10000}>10,000</option></select></label>
      <div className="w-full">
        <p className="mb-2 text-xs font-semibold text-slate-600">Choose write strategy</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" onClick={() => setWriteStrategy("INSERT_ONLY")} className={`rounded-xl border p-4 text-left transition ${writeStrategy === "INSERT_ONLY" ? "border-indigo-300 bg-indigo-50/70 ring-2 ring-indigo-100" : "border-slate-200 bg-white hover:border-slate-300"}`}>
            <span className="flex items-center justify-between"><span className="text-sm font-semibold text-slate-800">Insert only</span><span className={`h-3 w-3 rounded-full border-2 ${writeStrategy === "INSERT_ONLY" ? "border-indigo-600 bg-indigo-600 ring-2 ring-indigo-100" : "border-slate-300"}`}/></span>
            <span className="mt-1 block text-[11px] leading-5 text-slate-500">Add new rows and leave existing destination records unchanged.</span>
            <span className="mt-2 inline-flex rounded-md bg-slate-100 px-2 py-1 text-[9px] font-bold tracking-wide text-slate-600">INSERT_ONLY</span>
          </button>
          <button type="button" onClick={() => setWriteStrategy("UPSERT")} className={`rounded-xl border p-4 text-left transition ${writeStrategy === "UPSERT" ? "border-indigo-300 bg-indigo-50/70 ring-2 ring-indigo-100" : "border-slate-200 bg-white hover:border-slate-300"}`}>
            <span className="flex items-center justify-between"><span className="text-sm font-semibold text-slate-800">Insert & update</span><span className={`h-3 w-3 rounded-full border-2 ${writeStrategy === "UPSERT" ? "border-indigo-600 bg-indigo-600 ring-2 ring-indigo-100" : "border-slate-300"}`}/></span>
            <span className="mt-1 block text-[11px] leading-5 text-slate-500">Insert new rows and update matching destination records when values differ.</span>
            <span className="mt-2 inline-flex rounded-md bg-slate-100 px-2 py-1 text-[9px] font-bold tracking-wide text-slate-600">UPSERT</span>
          </button>
        </div>
      </div>
      <button disabled={busy || !["ready","schema_prepared"].includes(planStatus)} onClick={start} className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">Queue migration</button>
      <button disabled={busy} onClick={refresh} className="rounded-lg border px-4 py-2 text-sm">Refresh status</button>
      {selected && ["queued","running","cancel_requested"].includes(selected.status) && <button disabled={busy || selected.status==="cancel_requested"} onClick={cancel} className="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-700">Cancel run</button>}
      {selected && ["failed","cancelled"].includes(selected.status) && <button disabled={busy} onClick={resume} className="rounded-lg border px-4 py-2 text-sm">Resume from checkpoint</button>}
      {selected && selected.status === "partially_failed" && selected.failed_rows > 0 && <button disabled={busy} onClick={retryErrors} className="rounded-lg border px-4 py-2 text-sm">Retry quarantined rows</button>}
      {selected && <button disabled={busy} onClick={() => downloadReport('json')} className="rounded-lg border px-4 py-2 text-sm">Export JSON</button>}
      {selected && <button disabled={busy} onClick={() => downloadReport('csv')} className="rounded-lg border px-4 py-2 text-sm">Export CSV</button>}
    </div>
    {writeStrategy === "UPSERT" && <p className="text-xs text-amber-700">UPSERT requires mapped source primary-key columns and a matching unique/primary-key constraint on the destination. Source values are authoritative.</p>}
    {![ "ready", "schema_prepared" ].includes(planStatus) && <p className="text-sm text-amber-700">Validate the plan and prepare destination tables before execution.</p>}
    {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {selected && <div className="rounded-lg border p-4 space-y-3">
      <div className="flex flex-wrap justify-between gap-2"><strong className="text-sm">Run {selected.id.slice(0,8)}</strong><span className="rounded bg-slate-100 px-2 py-1 text-xs">{selected.status.replaceAll("_"," ")}</span></div>
      <div><div className="mb-1 flex justify-between text-xs"><span className="font-semibold text-slate-700">Approximate byte progress</span><span className="tabular-nums text-slate-500">{formatBytes(observedPayloadBytes)} / {formatBytes(estimatedSourceBytes)}</span></div><div className="h-2 overflow-hidden rounded bg-slate-100"><div className="h-full bg-blue-600 transition-all" style={{width:`${percent}%`}} /></div><p className="mt-1 text-[10px] text-slate-400">Indicative only: serialized payload and physical relation size use different storage semantics.</p></div>
      <div className="grid gap-3 text-sm sm:grid-cols-4">
        <div><span className="text-slate-500">Inserted</span><p className="font-semibold">{selected.inserted_rows.toLocaleString()}</p></div>
        <div><span className="text-slate-500">Updated</span><p className="font-semibold">{selected.updated_rows.toLocaleString()}</p></div>
        <div><span className="text-slate-500">Skipped</span><p className="font-semibold">{selected.skipped_rows.toLocaleString()}</p></div>
        <div><span className="text-slate-500">Failed</span><p className="font-semibold">{selected.failed_rows.toLocaleString()}</p></div>
        <div><span className="text-slate-500">Tables done</span><p className="font-semibold">{selected.completed_tables}/{selected.total_tables}</p></div>
        <div><span className="text-slate-500">Total rows</span><p className="font-semibold">{selected.total_rows.toLocaleString()}</p></div>
        <div><span className="text-slate-500">Validation</span><p className="font-semibold">{selected.validation_status} ({selected.mismatch_rows} mismatches)</p></div>
        <div><span className="text-slate-500">Strategy</span><p className="font-semibold">{selected.write_strategy}</p></div>
      </div>
      {runMetric && <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-sm font-semibold text-slate-800">Transfer performance</h3><p className="mt-1 text-[11px] text-slate-500">Logical payload bytes are estimated from serialized fetched rows, not wire-level packet counters.</p></div><span className="text-xs font-semibold text-indigo-700">{formatRate(runMetric.logical_bytes_per_second)}</span></div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Payload observed" value={formatBytes(runMetric.logical_bytes)}/>
          <Metric label="Source fetch time" value={`${(runMetric.source_fetch_duration_ms/1000).toFixed(1)} s`}/>
          <Metric label="Destination write time" value={`${(runMetric.destination_write_duration_ms/1000).toFixed(1)} s`}/>
          <Metric label="Checkpoints crossed / planned" value={`${(runMetric.batches_committed ?? 0).toLocaleString()} / ${plannedCheckpoints.toLocaleString()}`}/>
          <Metric label="Source round trip" value={runMetric.source_network_rtt_ms == null ? "Unavailable" : `${runMetric.source_network_rtt_ms} ms`}/>
          <Metric label="Destination round trip" value={runMetric.destination_network_rtt_ms == null ? "Unavailable" : `${runMetric.destination_network_rtt_ms} ms`}/>
          <Metric label="Observed row rate" value={`${Math.round(runMetric.rows_per_second ?? 0).toLocaleString()} rows/s`}/>
          <Metric label="Rough remaining time" value={etaSeconds == null ? "Calculating…" : etaSeconds < 60 ? `${Math.ceil(etaSeconds)} sec` : `${Math.ceil(etaSeconds/60)} min`}/>
        </div>
        <p className="mt-2 text-[10px] text-slate-500">ETA is indicative only: it compares serialized payload throughput with PostgreSQL physical table footprint, which can differ due to indexes, TOAST, compression, and type encoding.</p>
        {runMetrics.recent_batches?.length > 0 && <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[650px] text-left text-[11px]"><thead><tr className="border-b border-indigo-100 text-slate-500"><th className="py-2">Batch</th><th className="py-2">Payload</th><th className="py-2">Fetch</th><th className="py-2">Write + commit</th><th className="py-2">Total</th><th className="py-2">DB RTT</th></tr></thead><tbody>{runMetrics.recent_batches.slice(-8).reverse().map((batch:any)=><tr key={`${batch.run_table_id}-${batch.sequence}`} className="border-b border-indigo-100/70"><td className="py-2">{batch.sequence}</td><td className="py-2">{formatBytes(batch.logical_bytes)}</td><td className="py-2">{batch.source_fetch_duration_ms} ms</td><td className="py-2">{batch.destination_write_duration_ms} ms</td><td className="py-2">{batch.duration_ms} ms</td><td className="py-2">{batch.network_rtt_ms ?? "—"} ms</td></tr>)}</tbody></table></div>}
      </div>}
      {selected.status === "queued" && <p className="rounded bg-amber-50 p-3 text-xs text-amber-800">This run is queued and has not yet been claimed by a worker. Confirm that <code>python -m app.worker</code> is running against the same metadata database. The page refreshes status automatically.</p>}
      {selected.status === "running" && <p className="text-xs text-slate-500">Worker: {selected.worker_id ?? "claiming"} · Last heartbeat: {selected.heartbeat_at ? new Date(selected.heartbeat_at).toLocaleString() : "not reported"}</p>}
      {selected.error_message && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{selected.error_message}</p>}
      <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="border-b text-slate-500"><tr><th className="p-2">Source</th><th className="p-2">Destination</th><th className="p-2">Status</th><th className="p-2">Payload</th><th className="p-2">Checkpoints crossed / planned</th><th className="p-2">Inserted</th><th className="p-2">Updated</th><th className="p-2">Skipped</th><th className="p-2">Failed</th><th className="p-2">Validation</th></tr></thead><tbody>{tableProgress.map((t:any)=><tr key={t.id} className="border-b"><td className="p-2">{t.source_schema}.{t.source_table}</td><td className="p-2">{t.destination_schema}.{t.destination_table}</td><td className="p-2">{t.status}</td><td className="p-2">{formatBytes(runMetrics?.tables?.find((metric:any) => metric.run_table_id === t.id)?.logical_bytes)}</td><td className="p-2">{runMetrics?.tables?.find((metric:any) => metric.run_table_id === t.id)?.batches_committed ?? 0} / {Math.ceil((t.total_rows ?? 0) / (selected?.batch_size ?? batchSize))}</td><td className="p-2">{t.inserted_rows.toLocaleString()}</td><td className="p-2">{t.updated_rows.toLocaleString()}</td><td className="p-2">{t.skipped_rows.toLocaleString()}</td><td className="p-2">{t.failed_rows.toLocaleString()}</td><td className="p-2">{t.validation_status}: {t.mismatch_rows}</td></tr>)}</tbody></table></div>
      {events.length > 0 && <div className="space-y-2"><h3 className="text-sm font-semibold">Execution activity</h3><ol className="max-h-40 space-y-1 overflow-auto rounded border p-3 text-xs">{events.slice(-100).reverse().map((item:any)=><li key={item.id} className="flex justify-between gap-3 border-b py-1 last:border-0"><span>{item.event_type.replaceAll('_',' ')} {item.details?.duration_ms ? '· ' + item.details.duration_ms + ' ms' : ''}</span><time className="shrink-0 text-slate-500">{new Date(item.created_at).toLocaleString()}</time></li>)}</ol></div>}
      {rowErrors.length > 0 && <div className="space-y-2"><h3 className="text-sm font-semibold">Row-level errors (first {rowErrors.length})</h3><div className="max-h-56 overflow-auto rounded border"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-slate-50"><tr><th className="p-2">Source key</th><th className="p-2">Error</th><th className="p-2">Attempts</th></tr></thead><tbody>{rowErrors.map((item:any)=><tr key={item.id} className="border-t"><td className="p-2">{JSON.stringify(item.source_key)}</td><td className="p-2">{item.error_message}</td><td className="p-2">{item.attempts}</td></tr>)}</tbody></table></div></div>}
    </div>}
    {runs.length>1 && <label className="text-sm">Previous runs <select value={selected?.id ?? ""} onChange={async(e)=>{const item=runs.find(r=>r.id===e.target.value);if(item){setSelected(item);setTableProgress(await getMigrationRunTables(projectId,planId,item.id));setRowErrors(await getMigrationRunErrors(projectId,planId,item.id));setEvents(await getMigrationRunEvents(projectId,planId,item.id));setRunMetrics(await getMigrationRunMetrics(projectId,planId,item.id));}}} className="ml-2 rounded border p-2">{runs.map(r=><option key={r.id} value={r.id}>{r.created_at} · {r.status}</option>)}</select></label>}
    <p className="text-xs text-slate-500">Start the durable worker from the backend directory with: <code>python -m app.worker</code>. Keep at least one worker running to process queued migrations. Keyset checkpoints require mapped primary keys. Reconciliation compares mapped values in bounded batches.</p>
  </section>;
}

function Metric({label,value}:{label:string;value:string}) {
  return <div className="rounded-lg border border-white bg-white/80 p-3"><p className="text-[10px] text-slate-500">{label}</p><p className="mt-1 text-sm font-semibold text-slate-800">{value}</p></div>;
}
