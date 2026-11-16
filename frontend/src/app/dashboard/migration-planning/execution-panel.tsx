"use client";

import { useState } from "react";
import { cancelMigrationRun, getMigrationRun, getMigrationRunTables, listMigrationRuns, startMigrationRun } from "./execution-actions";

const terminal = ["completed", "failed", "cancelled", "partially_failed"];
type Run = { id: string; status: string; batch_size: number; total_tables: number; completed_tables: number; total_rows: number; migrated_rows: number; failed_rows: number; error_message?: string | null; created_at: string };

export default function ExecutionPanel({ projectId, planId, planStatus }: { projectId: string; planId: string; planStatus: string }) {
  const [batchSize, setBatchSize] = useState(1000);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<Run | null>(null);
  const [tableProgress, setTableProgress] = useState<any[]>([]);
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
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Could not refresh migration runs."); }
    finally { setBusy(false); }
  }

  async function start() {
    setBusy(true); setError("");
    try {
      const run = await startMigrationRun(projectId, planId, batchSize);
      setSelected(run);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start migration."); }
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

  const percent = selected?.total_rows ? Math.min(100, Math.round(selected.migrated_rows / selected.total_rows * 100)) : 0;
  return <section className="rounded-xl border bg-white p-6 shadow-sm space-y-4">
    <div><p className="text-xs font-semibold uppercase tracking-wide text-blue-700">Data execution</p><h2 className="mt-1 text-lg font-semibold">5. Run migration</h2>
      <p className="mt-1 text-sm text-slate-600">Transfers selected table rows in bounded batches. Destination schema must already be prepared.</p></div>
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">Batch size <select value={batchSize} onChange={(e) => setBatchSize(Number(e.target.value))} className="ml-2 rounded border p-2"><option value={500}>500</option><option value={1000}>1,000</option><option value={2500}>2,500</option><option value={5000}>5,000</option><option value={10000}>10,000</option></select></label>
      <button disabled={busy || !["ready","schema_prepared"].includes(planStatus)} onClick={start} className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">Start migration</button>
      <button disabled={busy} onClick={refresh} className="rounded-lg border px-4 py-2 text-sm">Refresh status</button>
      {selected && ["queued","running","cancel_requested"].includes(selected.status) && <button disabled={busy || selected.status==="cancel_requested"} onClick={cancel} className="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-700">Cancel run</button>}
    </div>
    {!["ready","schema_prepared"].includes(planStatus) && <p className="text-sm text-amber-700">Validate the plan and prepare destination tables before execution.</p>}
    {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {selected && <div className="rounded-lg border p-4 space-y-3">
      <div className="flex flex-wrap justify-between gap-2"><strong className="text-sm">Run {selected.id.slice(0,8)}</strong><span className="rounded bg-slate-100 px-2 py-1 text-xs">{selected.status.replaceAll("_"," ")}</span></div>
      <div className="h-2 overflow-hidden rounded bg-slate-100"><div className="h-full bg-blue-600 transition-all" style={{width:`${percent}%`}} /></div>
      <div className="grid gap-3 text-sm sm:grid-cols-4"><div><span className="text-slate-500">Rows inserted</span><p className="font-semibold">{selected.migrated_rows.toLocaleString()}</p></div><div><span className="text-slate-500">Tables done</span><p className="font-semibold">{selected.completed_tables}/{selected.total_tables}</p></div><div><span className="text-slate-500">Failed rows</span><p className="font-semibold">{selected.failed_rows}</p></div><div><span className="text-slate-500">Batch size</span><p className="font-semibold">{selected.batch_size.toLocaleString()}</p></div></div>
      {selected.error_message && <p className="text-sm text-red-700">{selected.error_message}</p>}
      <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="border-b text-slate-500"><tr><th className="p-2">Source</th><th className="p-2">Destination</th><th className="p-2">Status</th><th className="p-2">Rows</th></tr></thead><tbody>{tableProgress.map((t:any)=><tr key={t.id} className="border-b"><td className="p-2">{t.source_schema}.{t.source_table}</td><td className="p-2">{t.destination_schema}.{t.destination_table}</td><td className="p-2">{t.status}</td><td className="p-2">{t.migrated_rows.toLocaleString()}</td></tr>)}</tbody></table></div>
    </div>}
    {runs.length>1 && <label className="text-sm">Previous runs <select value={selected?.id ?? ""} onChange={async(e)=>{const item=runs.find(r=>r.id===e.target.value);if(item){setSelected(item);setTableProgress(await getMigrationRunTables(projectId,planId,item.id));}}} className="ml-2 rounded border p-2">{runs.map(r=><option key={r.id} value={r.id}>{r.created_at} · {r.status}</option>)}</select></label>}
    <p className="text-xs text-slate-500">Execution uses a server-side worker task for this development build. Each destination batch commits separately; duplicate primary keys are skipped with ON CONFLICT DO NOTHING. Use a dedicated durable queue/worker before production deployment.</p>
  </section>;
}
