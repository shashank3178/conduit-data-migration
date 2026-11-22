import { redirect } from "next/navigation";
import Link from "next/link";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import AppShell from "@/components/layout/app-shell";
import { ArrowUpRight, Boxes, Cable, Plus, Workflow } from "lucide-react";
import ProjectCreateForm from "./project-create-form";
import ConnectionCreateForm from "../connections/connection-create-form";
import DiscoveryClient from "../discovery/discovery-client";

type Project = { id: string; name: string; status?: string; created_at?: string };
type Connection = { id: string; name: string; role: "source" | "destination"; database: string; host: string; port: number };
type Plan = { id: string; name: string; status: string };

export default async function ProjectsPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/dashboard/projects");
  let projects: Project[] = [];
  let summaries: { connections: Connection[]; plans: Plan[] }[] = [];
  let error = "";
  try {
    const { token } = await auth0.getAccessToken();
    if (!token) throw new Error("No API access token was returned.");
    projects = await apiRequest<Project[]>("/projects", token, { cache: "no-store" });
    summaries = await Promise.all(projects.map(async (project) => {
      const [connections, plans] = await Promise.all([
        apiRequest<Connection[]>(`/projects/${project.id}/connections`, token, { cache: "no-store" }),
        apiRequest<Plan[]>(`/projects/${project.id}/migration-plans`, token, { cache: "no-store" }),
      ]);
      return { connections, plans };
    }));
  } catch (e) { error = e instanceof Error ? e.message : "Could not load projects."; }

  return <AppShell userLabel={session.user.name ?? session.user.email}>
    <div className="conduit-enter space-y-7">
      <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="conduit-eyebrow">Workspace</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Projects</h1><p className="mt-2 text-sm text-slate-500">Keep each migration initiative, its database connections, and plans organized.</p></div><Link href="/dashboard/migration-planning" className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-3 text-xs font-semibold text-white hover:bg-indigo-700"><Plus size={15}/> Start a migration <ArrowUpRight size={14}/></Link></div>
      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}
      <ProjectCreateForm />
      <ConnectionCreateForm projects={projects} />
      <section className="conduit-card p-5 sm:p-6">
        <div className="mb-4"><p className="conduit-eyebrow">Project database discovery</p><h2 className="mt-1 text-lg font-semibold">Discover project connections</h2><p className="mt-1 text-xs text-slate-500">Run discovery directly from the Projects page after registering a connection.</p></div>
        <DiscoveryClient key={projects.map((project,index)=>project.id+":"+(summaries[index]?.connections??[]).map(connection=>connection.id).join(",")).join("|")} projects={projects} connectionsByProject={Object.fromEntries(projects.map((project,index)=>[project.id,summaries[index]?.connections??[]]))} initialProjectId={projects[0]?.id} />
      </section>
      <div className="grid gap-4 sm:grid-cols-3">
        <Summary label="Total projects" value={projects.length} icon={<Boxes size={18}/>} />
        <Summary label="Database connections" value={summaries.reduce((n,x)=>n+x.connections.length,0)} icon={<Cable size={18}/>} />
        <Summary label="Migration plans" value={summaries.reduce((n,x)=>n+x.plans.length,0)} icon={<Workflow size={18}/>} />
      </div>
      {projects.length ? <div className="grid gap-4 lg:grid-cols-2">
        {projects.map((project,index) => {
          const summary=summaries[index] ?? {connections:[],plans:[]};
          const sources=summary.connections.filter(x=>x.role==="source").length;
          const destinations=summary.connections.filter(x=>x.role==="destination").length;
          return <article key={project.id} className="conduit-card p-5 transition hover:-translate-y-0.5 hover:shadow-md sm:p-6">
            <div className="flex items-start justify-between"><span className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700"><Boxes size={20}/></span><span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-semibold text-emerald-700">{project.status ?? "Active"}</span></div>
            <h2 className="mt-5 text-lg font-semibold text-slate-900">{project.name}</h2><p className="mt-1 text-[11px] text-slate-400">Project ID · {project.id.slice(0,8)}</p>
            <div className="mt-5 grid grid-cols-3 gap-2"><Mini label="Connections" value={summary.connections.length}/><Mini label="Source / target" value={`${sources} / ${destinations}`}/><Mini label="Plans" value={summary.plans.length}/></div>
            <div className="mt-5 flex flex-wrap gap-2"><Link href="/dashboard/connections" className="rounded-lg border border-slate-200 px-3 py-2 text-[11px] font-semibold text-slate-600 hover:bg-slate-50">Manage connections</Link><Link href={`/dashboard/discovery?projectId=${project.id}`} className="rounded-lg border border-slate-200 px-3 py-2 text-[11px] font-semibold text-slate-600 hover:bg-slate-50">Discover databases</Link><Link href="/dashboard/migration-planning" className="rounded-lg bg-slate-900 px-3 py-2 text-[11px] font-semibold text-white hover:bg-slate-700">Open planner <ArrowUpRight size={12} className="ml-1 inline"/></Link></div>
          </article>;
        })}
      </div> : <div className="conduit-card px-6 py-14 text-center"><Boxes size={26} className="mx-auto text-slate-400"/><h2 className="mt-3 text-sm font-semibold">No projects found</h2><p className="mt-1 text-xs text-slate-500">Create a project through the project API to begin organizing migrations.</p></div>}
    </div>
  </AppShell>;
}
function Summary({label,value,icon}:{label:string;value:number;icon:React.ReactNode}) { return <div className="conduit-card p-5"><div className="flex items-center justify-between"><span className="text-xs font-medium text-slate-500">{label}</span><span className="rounded-lg bg-slate-100 p-2 text-slate-600">{icon}</span></div><p className="mt-3 text-2xl font-semibold">{value}</p></div>; }
function Mini({label,value}:{label:string;value:string|number}) { return <div className="rounded-xl bg-slate-50 p-3"><p className="text-[10px] text-slate-400">{label}</p><p className="mt-1 text-sm font-semibold text-slate-800">{value}</p></div>; }
