import Link from "next/link";
import { redirect, notFound } from "next/navigation";
import { ArrowLeft, Clock3, Database, Gauge, Layers3, Rows3 } from "lucide-react";

import AppShell from "@/components/layout/app-shell";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import AnalyticsRefresh from "@/components/analytics/analytics-refresh";

type Detail = {
  run: {
    id: string; status: string; worker_id: string | null; batch_size: number; write_strategy: string;
    total_rows: number; migrated_rows: number; inserted_rows: number; updated_rows: number;
    skipped_rows: number; failed_rows: number; validation_status: string; mismatch_rows: number;
    heartbeat_at: string | null; started_at: string | null; finished_at: string | null; error_message: string | null;
  };
  metrics: null | { rows_fetched: number; rows_committed: number; batches_committed: number; logical_bytes: number; processing_duration_ms: number; rows_per_second: number; logical_bytes_per_second: number; source_fetch_duration_ms: number; destination_write_duration_ms: number; source_network_rtt_ms: number | null; destination_network_rtt_ms: number | null };
  tables: Array<{id:string;source:string;destination:string;status:string;total_rows:number;inserted_rows:number;updated_rows:number;skipped_rows:number;failed_rows:number;validation_status:string;metrics:null|{logical_bytes:number;source_physical_bytes:number|null;destination_physical_bytes:number|null;batches_committed:number}}>;
  batches: Array<{id:string;sequence:number;rows_fetched:number;rows_inserted:number;rows_updated:number;rows_skipped:number;rows_failed:number;logical_bytes:number;duration_ms:number;source_fetch_duration_ms:number;destination_write_duration_ms:number;network_rtt_ms:number|null;created_at:string}>;
  databases: Array<{role:string;database_name:string;physical_bytes:number;measurement_kind:string;captured_at:string}>;
};
function bytes(value:number){if(!value)return "0 B";const u=["B","KB","MB","GB","TB"];const i=Math.min(Math.floor(Math.log(value)/Math.log(1024)),4);return `${(value/1024**i).toFixed(i?1:0)} ${u[i]}`;}
export default async function MigrationRunDetailPage({params}:{params:Promise<{runId:string}>}) {
  const {runId}=await params;
  const session=await auth0.getSession();
  if(!session)redirect(`/auth/login?returnTo=/dashboard/migration-runs/${runId}`);
  let detail:Detail;
  try { const {token}=await auth0.getAccessToken(); if(!token)throw new Error("No API token."); detail=await apiRequest<Detail>(`/analytics/runs/${runId}`,token,{cache:"no-store"}); }
  catch { notFound(); }
  const run=detail.run;
  const committedRows=run.inserted_rows+run.updated_rows;
  const processedRows=committedRows+run.skipped_rows+run.failed_rows;
  const estimatedBytes=detail.tables.reduce((sum,table)=>sum+(table.metrics?.source_physical_bytes??0),0);
  const observedBytes=detail.metrics?.logical_bytes??0;
  const progress=estimatedBytes?Math.min(100,observedBytes/estimatedBytes*100):0;
  return <AppShell userLabel={session.user.name??session.user.email}>
    <div className="conduit-enter space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><Link href="/dashboard/analytics" className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-orange-700"><ArrowLeft size={13}/> Analytics</Link><p className="conduit-eyebrow">Migration run</p><h1 className="mt-1 text-2xl font-semibold tracking-tight">Run {run.id.slice(0,8)}</h1><p className="mt-1 text-xs text-slate-500">Started {run.started_at?new Date(run.started_at).toLocaleString():"Not started"} · {run.worker_id??"Worker unassigned"}</p></div>
        <div className="flex items-center gap-3"><span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold capitalize text-slate-700">{run.status.replaceAll("_"," ")}</span><AnalyticsRefresh runId={run.id}/></div>
      </div>
      <section className="conduit-card p-5">
        <div className="flex flex-wrap justify-between gap-2"><div><p className="conduit-eyebrow">Execution progress</p><p className="mt-1 text-xl font-semibold tabular-nums">{progress.toFixed(1)}%</p></div><div className="text-right text-xs text-slate-500">{bytes(observedBytes)} payload / {bytes(estimatedBytes)} source footprint</div></div>
        <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-orange-500" style={{width:`${progress}%`}}/></div><p className="mt-1 text-[10px] text-slate-400">Approximate byte progress: serialized payload size and PostgreSQL physical relation size are not identical measurements.</p>
        {run.error_message&&<p className="mt-4 rounded-lg bg-rose-50 p-3 text-xs text-rose-700">{run.error_message}</p>}
      </section>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Rows committed" value={committedRows.toLocaleString()} icon={<Rows3 size={17}/>} />
        <Metric label="Logical payload" value={detail.metrics?bytes(detail.metrics.logical_bytes):"Not collected"} icon={<Database size={17}/>} />
        <Metric label="Payload throughput" value={detail.metrics?`${bytes(detail.metrics.logical_bytes_per_second)}/s`:"—"} icon={<Gauge size={17}/>} />
        <Metric label="Committed batches" value={detail.metrics?detail.metrics.batches_committed.toLocaleString():"—"} icon={<Layers3 size={17}/>} />
        <Metric label="Source fetch time" value={detail.metrics?`${(detail.metrics.source_fetch_duration_ms/1000).toFixed(1)} s`:"—"} icon={<Clock3 size={17}/>} />
        <Metric label="Destination write time" value={detail.metrics?`${(detail.metrics.destination_write_duration_ms/1000).toFixed(1)} s`:"—"} icon={<Database size={17}/>} />
        <Metric label="Source DB round trip" value={detail.metrics?.source_network_rtt_ms==null?"—":`${detail.metrics.source_network_rtt_ms} ms`} icon={<Clock3 size={17}/>} />
        <Metric label="Destination DB round trip" value={detail.metrics?.destination_network_rtt_ms==null?"—":`${detail.metrics.destination_network_rtt_ms} ms`} icon={<Clock3 size={17}/>} />
      </section>
      <section className="conduit-card overflow-hidden">
        <div className="border-b border-slate-200 px-5 py-4"><p className="conduit-eyebrow">Table-level execution</p><h2 className="mt-1 text-base font-semibold">Migrated tables</h2></div>
        <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th className="px-5 py-3">Source → destination</th><th className="px-3 py-3">Status</th><th className="px-3 py-3">Committed</th><th className="px-3 py-3">Batches</th><th className="px-3 py-3">Logical bytes</th><th className="px-5 py-3">Physical size (source / destination)</th></tr></thead><tbody className="divide-y divide-slate-100">{detail.tables.map((table)=><tr key={table.id}><td className="px-5 py-3"><p className="font-semibold text-slate-800">{table.source}</p><p className="mt-1 text-slate-400">→ {table.destination}</p></td><td className="px-3 py-3 capitalize">{table.status}</td><td className="px-3 py-3 tabular-nums">{(table.inserted_rows+table.updated_rows).toLocaleString()}</td><td className="px-3 py-3">{table.metrics?.batches_committed??"—"}</td><td className="px-3 py-3">{table.metrics?bytes(table.metrics.logical_bytes):"—"}</td><td className="px-5 py-3">{table.metrics?(`${table.metrics.source_physical_bytes===null?"—":bytes(table.metrics.source_physical_bytes)} / ${table.metrics.destination_physical_bytes===null?"—":bytes(table.metrics.destination_physical_bytes)}`):"Not collected"}</td></tr>)}</tbody></table></div>
      </section>
      <section className="grid gap-4 xl:grid-cols-2">
        <div className="conduit-card overflow-hidden"><div className="border-b border-slate-200 px-5 py-4"><p className="conduit-eyebrow">Batch history</p><h2 className="mt-1 text-base font-semibold">Latest committed batches</h2></div><div className="divide-y divide-slate-100">{detail.batches.length?detail.batches.map(batch=><div key={batch.id} className="flex items-center justify-between gap-3 px-5 py-3 text-xs"><div><p className="font-semibold text-slate-800">Batch #{batch.sequence}</p><p className="mt-1 text-slate-400">{bytes(batch.logical_bytes)} · fetch {batch.source_fetch_duration_ms} ms · write {batch.destination_write_duration_ms} ms · RTT {batch.network_rtt_ms ?? "—"} ms · {new Date(batch.created_at).toLocaleString()}</p></div><div className="text-right"><p className="font-semibold tabular-nums">{batch.rows_fetched.toLocaleString()} rows · {bytes(batch.logical_bytes)}</p><p className="mt-1 text-slate-400">{batch.duration_ms.toFixed(0)} ms</p></div></div>):<p className="p-5 text-xs text-slate-500">No batch metrics have been collected for this run.</p>}</div></div>
        <div className="conduit-card overflow-hidden"><div className="border-b border-slate-200 px-5 py-4"><p className="conduit-eyebrow">Database measurements</p><h2 className="mt-1 text-base font-semibold">Physical database size</h2></div><div className="divide-y divide-slate-100">{detail.databases.length?detail.databases.map((db,index)=><div key={index} className="flex items-center justify-between gap-3 px-5 py-3 text-xs"><div><p className="font-semibold capitalize text-slate-800">{db.role} · {db.database_name}</p><p className="mt-1 text-slate-400">{new Date(db.captured_at).toLocaleString()} · {db.measurement_kind}</p></div><strong>{bytes(db.physical_bytes)}</strong></div>):<p className="p-5 text-xs text-slate-500">Database size snapshots are not available.</p>}</div></div>
      </section>
      <div className="flex flex-wrap gap-4 text-xs text-slate-500"><span><Clock3 className="mr-1 inline" size={13}/> Heartbeat: {run.heartbeat_at?new Date(run.heartbeat_at).toLocaleString():"—"}</span><span>Validation: {run.validation_status}</span><span>Mismatches: {run.mismatch_rows.toLocaleString()}</span><span>Batch size: {run.batch_size}</span><span>Strategy: {run.write_strategy}</span></div>
    </div>
  </AppShell>;
}
function Metric({label,value,icon}:{label:string;value:string;icon:React.ReactNode}){return <div className="conduit-card p-5"><div className="flex items-center justify-between text-xs font-semibold text-slate-500">{label}<span className="rounded-lg bg-orange-50 p-2 text-orange-700">{icon}</span></div><p className="mt-4 text-2xl font-semibold text-slate-900">{value}</p></div>}
