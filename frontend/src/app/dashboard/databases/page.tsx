import Link from "next/link";
import { redirect } from "next/navigation";
import { Database, HardDrive, RefreshCw } from "lucide-react";
import AppShell from "@/components/layout/app-shell";
import AnalyticsRefresh from "@/components/analytics/analytics-refresh";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";

type Snapshot = { run_id: string; connection_id: string; role: string; database_name: string; physical_bytes: number; measurement_kind: string; captured_at: string };
function formatBytes(value: number) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), 4);
  return (value / Math.pow(1024, index)).toFixed(index ? 1 : 0) + " " + units[index];
}

export default async function DatabaseMonitoringPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/dashboard/databases");
  let rows: Snapshot[] = [];
  let error = "";
  try {
    const { token } = await auth0.getAccessToken();
    if (!token) throw new Error("No API access token.");
    rows = await apiRequest<Snapshot[]>("/analytics/databases", token, { cache: "no-store" });
  } catch (err) { error = err instanceof Error ? err.message : "Unable to load database measurements."; }
  const latest = new Map<string, Snapshot>();
  rows.forEach((row) => { const key = row.role + ":" + row.database_name; if (!latest.has(key)) latest.set(key, row); });
  const sources = Array.from(latest.values()).filter((row) => row.role === "source");
  const destinations = Array.from(latest.values()).filter((row) => row.role === "destination");
  return <AppShell userLabel={session.user.name ?? session.user.email}>
    <div className="conduit-enter space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="conduit-eyebrow">Observability / Databases</p><h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">Database monitoring</h1><p className="mt-2 text-sm text-slate-500">Physical database storage snapshots collected during migration runs.</p></div><span className="inline-flex items-center gap-2 text-xs text-slate-500"><RefreshCw size={13}/> Auto-refresh <AnalyticsRefresh /></span></div>
      {error && <p className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</p>}
      <div className="grid gap-4 md:grid-cols-2"><StorageGroup title="Source databases" rows={sources}/><StorageGroup title="Destination databases" rows={destinations}/></div>
      <section className="conduit-card overflow-hidden"><div className="border-b border-slate-200 px-5 py-4"><p className="conduit-eyebrow">Measurement history</p><h2 className="mt-1 text-base font-semibold">Latest database snapshots</h2></div>
        {rows.length ? <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th className="px-5 py-3">Role</th><th className="px-3 py-3">Database</th><th className="px-3 py-3">Physical size</th><th className="px-3 py-3">Measurement</th><th className="px-3 py-3">Captured</th><th className="px-5 py-3">Run</th></tr></thead><tbody className="divide-y divide-slate-100">{rows.map((row, index) => <tr key={row.run_id + row.role + index}><td className="px-5 py-3 capitalize">{row.role}</td><td className="px-3 py-3 font-medium text-slate-800">{row.database_name}</td><td className="px-3 py-3 tabular-nums">{formatBytes(row.physical_bytes)}</td><td className="px-3 py-3 capitalize">{row.measurement_kind}</td><td className="px-3 py-3">{new Date(row.captured_at).toLocaleString()}</td><td className="px-5 py-3"><Link className="text-orange-700 hover:text-orange-800" href={"/dashboard/migration-runs/" + row.run_id}>View run</Link></td></tr>)}</tbody></table></div> : <div className="px-5 py-12 text-center"><HardDrive size={24} className="mx-auto text-slate-400"/><p className="mt-3 text-sm font-semibold">No database measurements yet</p><p className="mt-1 text-xs text-slate-500">Snapshots are collected when migration runs connect to their source and destination.</p></div>}
      </section>
    </div>
  </AppShell>;
}

function StorageGroup({ title, rows }: { title: string; rows: Snapshot[] }) {
  return <section className="conduit-card p-5"><p className="conduit-eyebrow">{title}</p>{rows.length ? <div className="mt-4 space-y-3">{rows.map((row) => <div key={row.connection_id} className="flex items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-md bg-orange-50 text-orange-700"><Database size={17}/></span><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{row.database_name}</p><p className="text-[10px] text-slate-400">{new Date(row.captured_at).toLocaleString()}</p></div></div><strong className="shrink-0 text-sm tabular-nums">{formatBytes(row.physical_bytes)}</strong></div>)}</div> : <p className="mt-4 text-xs text-slate-500">No snapshots collected.</p>}</section>;
}