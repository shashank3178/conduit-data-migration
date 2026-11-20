import Link from "next/link";
import { redirect } from "next/navigation";
import { Activity, ArrowUpRight, CircleAlert, Clock3, Database, Gauge, Layers3, Rows3 } from "lucide-react";

import AppShell from "@/components/layout/app-shell";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import AnalyticsRefresh from "@/components/analytics/analytics-refresh";

type Analytics = {
  summary: {
    total_runs: number; metrics_runs_count: number; active_runs: number; completed_runs: number; failed_runs: number;
    rows_committed: number; rows_inserted: number; rows_updated: number; rows_skipped: number;
    rows_failed: number; logical_bytes: number; rows_fetched: number; batches_committed: number;
    average_rows_per_second: number; average_logical_bytes_per_second: number;
  };
  recent_runs: Array<{
    id: string; project_id: string; plan_id: string; status: string; created_at: string;
    total_rows: number; migrated_rows: number; inserted_rows: number; updated_rows: number;
    skipped_rows: number; failed_rows: number; worker_id: string | null;
    logical_bytes: number | null; rows_per_second: number | null;
  }>;
};

function bytes(value: number) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}
function number(value: number) { return value.toLocaleString(); }

export default async function AnalyticsPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/dashboard/analytics");
  let data: Analytics | null = null;
  let error = "";
  try {
    const { token } = await auth0.getAccessToken();
    if (!token) throw new Error("No API access token was returned.");
    data = await apiRequest<Analytics>("/analytics/overview", token, { cache: "no-store" });
  } catch (err) {
    error = err instanceof Error ? err.message : "Unable to load migration analytics.";
  }
  const summary = data?.summary;
  const maxRows = Math.max(1, ...((data?.recent_runs ?? []).map((run) => run.migrated_rows)));
  return (
    <AppShell userLabel={session.user.name ?? session.user.email}>
      <div className="conduit-enter space-y-7">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="conduit-eyebrow">Observability / Workspace</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">Migration analytics</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-500">Operational visibility across migration runs, committed rows, throughput and payload volume.</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500"><span className="h-2 w-2 rounded-full bg-emerald-500"/> Auto-refresh every 5 seconds <AnalyticsRefresh /></div>
        </div>
        {error && <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700"><CircleAlert className="mr-2 inline" size={16}/>{error}</div>}
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Total runs" value={number(summary?.total_runs ?? 0)} detail={`${number(summary?.active_runs ?? 0)} active now`} icon={<Activity size={18}/>} />
          <Metric label="Rows committed" value={number(summary?.rows_committed ?? 0)} detail={`${number(summary?.rows_fetched ?? 0)} rows fetched`} icon={<Rows3 size={18}/>} />
          <Metric label="Logical payload" value={summary?.metrics_runs_count ? bytes(summary.logical_bytes) : "Not collected"} detail="Serialized row payload estimate" icon={<Database size={18}/>} />
          <Metric label="Average throughput" value={summary?.metrics_runs_count ? `${summary.average_rows_per_second.toFixed(1)} rows/s` : "—"} detail={summary?.metrics_runs_count ? `${bytes(summary.average_logical_bytes_per_second)}/s` : "No run metrics yet"} icon={<Gauge size={18}/>} />
        </section>
        <section className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
          <div className="conduit-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div><p className="conduit-eyebrow">Execution history</p><h2 className="mt-1 text-base font-semibold">Recent migration runs</h2></div>
              <Link href="/dashboard/activity" className="inline-flex items-center gap-1 text-xs font-semibold text-orange-700 hover:text-orange-800">Run activity <ArrowUpRight size={14}/></Link>
            </div>
            {(data?.recent_runs.length ?? 0) ? <div className="divide-y divide-slate-100">
              {data!.recent_runs.map((run) => <Link key={run.id} href={`/dashboard/migration-runs/${run.id}`} className="block px-5 py-4 transition hover:bg-slate-50">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">Run {run.id.slice(0, 8)}</p><p className="mt-1 text-xs text-slate-500">{new Date(run.created_at).toLocaleString()} · {run.worker_id ?? "Worker pending"}</p></div>
                  <span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold capitalize ${run.status === "completed" ? "bg-emerald-50 text-emerald-700" : run.status === "running" ? "bg-sky-50 text-sky-700" : ["failed", "partially_failed"].includes(run.status) ? "bg-rose-50 text-rose-700" : "bg-slate-100 text-slate-600"}`}>{run.status.replaceAll("_", " ")}</span>
                </div>
                <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-500"><span>{number(run.migrated_rows)} / {number(run.total_rows)} rows</span><span>{run.logical_bytes === null ? "Metrics not collected" : bytes(run.logical_bytes)}</span></div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-orange-500" style={{ width: `${Math.min(100, run.total_rows ? run.migrated_rows / run.total_rows * 100 : 0)}%` }}/></div>
              </Link>)}
            </div> : <div className="px-5 py-12 text-center"><Layers3 className="mx-auto text-slate-400" size={24}/><p className="mt-3 text-sm font-semibold">No migration runs yet</p><p className="mt-1 text-xs text-slate-500">Metrics will appear here after your first migration.</p></div>}
          </div>
          <div className="space-y-4">
            <div className="conduit-card p-5">
              <p className="conduit-eyebrow">Run outcomes</p><h2 className="mt-1 text-base font-semibold">Execution status</h2>
              <div className="mt-5 space-y-4">
                <Outcome label="Completed" value={summary?.completed_runs ?? 0} total={summary?.total_runs ?? 0} tone="bg-emerald-500"/>
                <Outcome label="Active" value={summary?.active_runs ?? 0} total={summary?.total_runs ?? 0} tone="bg-sky-500"/>
                <Outcome label="Needs attention" value={summary?.failed_runs ?? 0} total={summary?.total_runs ?? 0} tone="bg-rose-500"/>
              </div>
            </div>
            <div className="conduit-card p-5">
              <p className="conduit-eyebrow">Committed row outcomes</p><h2 className="mt-1 text-base font-semibold">Write accounting</h2>
              <div className="mt-5 space-y-3 text-sm">
                <Row label="Inserted" value={summary?.rows_inserted ?? 0} />
                <Row label="Updated" value={summary?.rows_updated ?? 0} />
                <Row label="Skipped" value={summary?.rows_skipped ?? 0} />
                <Row label="Failed" value={summary?.rows_failed ?? 0} />
                <Row label="Batches committed" value={summary?.batches_committed ?? 0} />
              </div>
            </div>
          </div>
        </section>
        <section className="conduit-card p-5">
          <div className="flex items-center justify-between"><div><p className="conduit-eyebrow">Volume comparison</p><h2 className="mt-1 text-base font-semibold">Rows migrated by recent run</h2></div><span className="text-[10px] text-slate-400">Committed row counts</span></div>
          <div className="mt-5 space-y-3">
            {(data?.recent_runs ?? []).slice(0, 8).map((run) => <div key={run.id} className="grid grid-cols-[76px_1fr_80px] items-center gap-3 text-xs"><span className="font-medium text-slate-500">{run.id.slice(0, 8)}</span><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-orange-500" style={{ width: `${run.migrated_rows / maxRows * 100}%` }}/></div><span className="text-right tabular-nums text-slate-600">{number(run.migrated_rows)}</span></div>)}
          </div>
        </section>
      </div>
    </AppShell>
  );
}

function Metric({label,value,detail,icon}:{label:string;value:string;detail:string;icon:React.ReactNode}) {
  return <div className="conduit-card p-5"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-slate-500">{label}</span><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-orange-50 text-orange-700">{icon}</span></div><p className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">{value}</p><p className="mt-1 text-[11px] text-slate-500">{detail}</p></div>;
}
function Outcome({label,value,total,tone}:{label:string;value:number;total:number;tone:string}) {
  return <div><div className="mb-2 flex justify-between text-xs"><span className="text-slate-600">{label}</span><strong className="tabular-nums text-slate-800">{number(value)}</strong></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${tone}`} style={{width:`${total ? value / total * 100 : 0}%`}}/></div></div>;
}
function Row({label,value}:{label:string;value:number}) { return <div className="flex justify-between gap-3"><span className="text-slate-500">{label}</span><strong className="tabular-nums text-slate-800">{number(value)}</strong></div>; }
