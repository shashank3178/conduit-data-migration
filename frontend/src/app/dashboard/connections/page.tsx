import { redirect } from "next/navigation";
import Link from "next/link";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import AppShell from "@/components/layout/app-shell";
import { ArrowUpRight, Cable, Database, Server, ShieldCheck } from "lucide-react";
import ConnectionCreateForm from "./connection-create-form";

type Project = { id: string; name: string };
type Connection = { id: string; name: string; role: "source" | "destination"; database: string; host: string; port: number; status?: string; db_type?: string };

export default async function ConnectionsPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/dashboard/connections");
  let rows: { project: Project; connection: Connection }[] = [];
  let projects: Project[] = [];
  let error = "";
  try {
    const { token } = await auth0.getAccessToken();
    if (!token) throw new Error("No API access token was returned.");
    projects = await apiRequest<Project[]>("/projects", token, { cache: "no-store" });
    const groups = await Promise.all(projects.map(async (project) => ({
      project,
      connections: await apiRequest<Connection[]>(`/projects/${project.id}/connections`, token, { cache: "no-store" }),
    })));
    rows = groups.flatMap(group => group.connections.map(connection => ({project:group.project,connection})));
  } catch (e) { error = e instanceof Error ? e.message : "Could not load connections."; }
  const sources=rows.filter(x=>x.connection.role==="source").length;
  const targets=rows.filter(x=>x.connection.role==="destination").length;
  return <AppShell userLabel={session.user.name ?? session.user.email}>
    <div className="conduit-enter space-y-7">
      <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="conduit-eyebrow">Infrastructure</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Database connections</h1><p className="mt-2 text-sm text-slate-500">A unified view of the source and destination databases registered in your projects.</p></div><Link href="/dashboard/migration-planning" className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-xs font-semibold text-white hover:bg-indigo-700">Use in migration plan <ArrowUpRight size={14}/></Link></div>
      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}
      <ConnectionCreateForm projects={projects} />
      <div className="grid gap-4 sm:grid-cols-3"><Stat label="All connections" value={rows.length} icon={<Cable size={18}/>} /><Stat label="Source systems" value={sources} icon={<Database size={18}/>} /><Stat label="Destination systems" value={targets} icon={<ShieldCheck size={18}/>} /></div>
      {rows.length ? <div className="grid gap-4 xl:grid-cols-2">{rows.map(({project,connection})=><article key={connection.id} className="conduit-card p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3"><div className="flex items-center gap-3"><span className={`flex h-11 w-11 items-center justify-center rounded-xl ${connection.role==="source"?"bg-sky-50 text-sky-700":"bg-violet-50 text-violet-700"}`}><Database size={20}/></span><div><h2 className="text-sm font-semibold text-slate-900">{connection.name}</h2><p className="mt-0.5 text-[11px] text-slate-400">{project.name}</p></div></div><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide ${connection.role==="source"?"bg-sky-50 text-sky-700":"bg-violet-50 text-violet-700"}`}>{connection.role}</span></div>
        <div className="mt-5 grid gap-3 rounded-xl bg-slate-50 p-4 sm:grid-cols-2"><Detail label="Host" value={connection.host}/><Detail label="Database" value={connection.database}/><Detail label="Port" value={String(connection.port)}/><Detail label="Connection type" value={connection.db_type ?? "PostgreSQL / configured"}/></div>
        <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-500"><Server size={13}/> Connection details are shown without credentials.</div>
      </article>)}</div> : <div className="conduit-card px-6 py-14 text-center"><Cable size={26} className="mx-auto text-slate-400"/><h2 className="mt-3 text-sm font-semibold">No connections registered</h2><p className="mt-1 text-xs text-slate-500">Add source and destination connections to a project before creating a migration plan.</p><Link href="/dashboard/migration-planning" className="mt-4 inline-flex rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white">Open migration planner</Link></div>}
    </div>
  </AppShell>;
}
function Stat({label,value,icon}:{label:string;value:number;icon:React.ReactNode}) { return <div className="conduit-card p-5"><div className="flex items-center justify-between"><span className="text-xs font-medium text-slate-500">{label}</span><span className="rounded-lg bg-slate-100 p-2 text-slate-600">{icon}</span></div><p className="mt-3 text-2xl font-semibold">{value}</p></div>; }
function Detail({label,value}:{label:string;value:string}) { return <div><p className="text-[10px] uppercase tracking-wider text-slate-400">{label}</p><p className="mt-1 break-all text-xs font-semibold text-slate-700">{value}</p></div>; }
