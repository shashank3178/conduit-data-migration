"use client";

import { useState } from "react";
import {
  cancelMigrationRun, downloadMigrationRunCsv, getMigrationRun, getMigrationRunErrors,
  getMigrationRunEvents, getMigrationRunReport, getMigrationRunTables, listMigrationRuns, resumeMigrationRun,
  startMigrationRun,
} from "./execution-actions";

type Run = {
  id: string; status: string; batch_size: number; write_strategy: "INSERT_ONLY" | "UPSERT";
  total_tables: number; completed_tables: number; total_rows: number; migrated_rows: number;
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

  async function refresh() {
    setBusy(true); setError("");
    try {
      const latest = await listMigrationRuns(projectId, planId);
      setRuns(latest);
      const current = selected ? latest.find((item) => item.id === selected.id) ?? latest[0] : latest[0];
      if (current) {
        const detail = await getMigrationRun(projectId, planId, current.id);
        setSelected(detail);
        setTableProgress(await getMigrationRunTables(projectId, planId, current.id));
        setRowErrors(await getMigrationRunErrors(projectId, planId, current.id));
        setEvents(await getMigrationRunEvents(projectId, planId, current.id));
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Could not refresh migration runs."); }
    finally { setBusy(false); }
  }

  async function start() {
    setBusy(true); setError("");
    try {
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

  const percent = selected?.total_rows ? Math.min(100, Math.round(selected.migrated_rows / selected.total_rows * 100)) : 0;
  return <section className="rounded-xl border bg-white p-6 shadow-sm space-y-4">
    <div><p className="text-xs font-semibold uppercase tracking-wide text-blue-700">Data execution</p><h2 className="mt-1 text-lg font-semibold">5. Run migration</h2>
      <p className="mt-1 text-sm text-slate-600">Queue a durable migration job. A separate backend worker processes queued jobs and persists checkpoints.</p></div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">Batch size <select value={batchSize} onChange={(e) => setBatchSize(Number(e.target.value))} className="ml-2 rounded border p-2"><option value={500}>500</option><option value={1000}>1,000</option><option value={2500}>2,500</option><option value={5000}>5,000</option><option value={10000}>10,000</option></select></label>
      <label className="text-sm">Write strategy <select value={writeStrategy} onChange={(e) => setWriteStrategy(e.target.value as "INSERT_ONLY" | "UPSERT")} className="ml-2 rounded border p-2"><option value="INSERT_ONLY">INSERT_ONLY</option><option value="UPSERT">UPSERT</option></select></label>
      <button disabled={busy || !["ready","schema_prepared"].includes(planStatus)} onClick={start} className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">Queue migration</button>
      <button disabled={busy} onClick={refresh} className="rounded-lg border px-4 py-2 text-sm">Refresh status</button>
      {selected && ["queued","running","cancel_requested"].includes(selected.status) && <button disabled={busy || selected.status==="cancel_requested"} onClick={cancel} className="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-700">Cancel run</button>}
      {selected && ["failed","cancelled"].includes(selected.status) && <button disabled={busy} onClick={resume} className="rounded-lg border px-4 py-2 text-sm">Resume from checkpoint</button>}
      {selected && <button disabled={busy} onClick={() => downloadReport('json')} className="rounded-lg border px-4 py-2 text-sm">Export JSON</button>}
      {selected && <button disabled={busy} onClick={() => downloadReport('csv')} className="rounded-lg border px-4 py-2 text-sm">Export CSV</button>}
    </div>
    {writeStrategy === "UPSERT" && <p className="text-xs text-amber-700">UPSERT requires mapped source primary-key columns and a matching unique/primary-key constraint on the destination. Source values are authoritative.</p>}
    {![ "ready", "schema_prepared" ].includes(planStatus) && <p className="text-sm text-amber-700">Validate the plan and prepare destination tables before execution.</p>}
    {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {selected && <div className="rounded-lg border p-4 space-y-3">
      <div className="flex flex-wrap justify-between gap-2"><strong className="text-sm">Run {selected.id.slice(0,8)}</strong><span className="rounded bg-slate-100 px-2 py-1 text-xs">{selected.status.replaceAll("_"," ")}</span></div>
      <div className="h-2 overflow-hidden rounded bg-slate-100"><div className="h-full bg-blue-600 transition-all" style={{width:`${percent}%`}} /></div>
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
      {selected.error_message && <p className="text-sm text-red-700">{selected.error_message}</p>}
      <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="border-b text-slate-500"><tr><th className="p-2">Source</th><th className="p-2">Destination</th><th className="p-2">Status</th><th className="p-2">Inserted</th><th className="p-2">Updated</th><th className="p-2">Skipped</th><th className="p-2">Failed</th><th className="p-2">Validation</th></tr></thead><tbody>{tableProgress.map((t:any)=><tr key={t.id} className="border-b"><td className="p-2">{t.source_schema}.{t.source_table}</td><td className="p-2">{t.destination_schema}.{t.destination_table}</td><td className="p-2">{t.status}</td><td className="p-2">{t.inserted_rows.toLocaleString()}</td><td className="p-2">{t.updated_rows.toLocaleString()}</td><td className="p-2">{t.skipped_rows.toLocaleString()}</td><td className="p-2">{t.failed_rows.toLocaleString()}</td><td className="p-2">{t.validation_status}: {t.mismatch_rows}</td></tr>)}</tbody></table></div>
      {events.length > 0 && <div className="space-y-2"><h3 className="text-sm font-semibold">Execution activity</h3><ol className="max-h-40 space-y-1 overflow-auto rounded border p-3 text-xs">{events.slice(-100).reverse().map((item:any)=><li key={item.id} className="flex justify-between gap-3 border-b py-1 last:border-0"><span>{item.event_type.replaceAll('_',' ')} {item.details?.duration_ms ? '· ' + item.details.duration_ms + ' ms' : ''}</span><time className="shrink-0 text-slate-500">{new Date(item.created_at).toLocaleString()}</time></li>)}</ol></div>}
      {rowErrors.length > 0 && <div className="space-y-2"><h3 className="text-sm font-semibold">Row-level errors (first {rowErrors.length})</h3><div className="max-h-56 overflow-auto rounded border"><table className="w-full text-left text-xs"><thead className="sticky top-0 bg-slate-50"><tr><th className="p-2">Source key</th><th className="p-2">Error</th><th className="p-2">Attempts</th></tr></thead><tbody>{rowErrors.map((item:any)=><tr key={item.id} className="border-t"><td className="p-2">{JSON.stringify(item.source_key)}</td><td className="p-2">{item.error_message}</td><td className="p-2">{item.attempts}</td></tr>)}</tbody></table></div></div>}
    </div>}
    {runs.length>1 && <label className="text-sm">Previous runs <select value={selected?.id ?? ""} onChange={async(e)=>{const item=runs.find(r=>r.id===e.target.value);if(item){setSelected(item);setTableProgress(await getMigrationRunTables(projectId,planId,item.id));setRowErrors(await getMigrationRunErrors(projectId,planId,item.id));setEvents(await getMigrationRunEvents(projectId,planId,item.id));}}} className="ml-2 rounded border p-2">{runs.map(r=><option key={r.id} value={r.id}>{r.created_at} · {r.status}</option>)}</select></label>}
    <p className="text-xs text-slate-500">Start the durable worker from the backend directory with: <code>python -m app.worker</code>. Keep at least one worker running to process queued migrations. Keyset checkpoints require mapped primary keys. Reconciliation compares mapped values in bounded batches.</p>
  </section>;
}
