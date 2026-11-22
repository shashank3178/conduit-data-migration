import { redirect } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight, ArrowUpRight, Boxes, Cable, CheckCircle2, CircleAlert,
  Database, GitBranch, Plus, ShieldCheck, Workflow, Zap,
} from "lucide-react";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import AppShell from "@/components/layout/app-shell";

interface BackendUser { id: string; email: string | null; }
interface Project { id: string; name: string; status?: string; created_at?: string; }
interface Connection { id: string; name: string; role: "source" | "destination"; database: string; host: string; port: number; }
interface Plan { id: string; name: string; status: string; }
interface RecentRun { id: string; status: string; created_at: string; plan_id: string; project_id: string; }

const statusTone: Record<string, string> = {
  ready: "bg-emerald-50 text-emerald-700",
  schema_prepared: "bg-sky-50 text-sky-700",
  draft: "bg-slate-100 text-slate-600",
  failed: "bg-rose-50 text-rose-700",
};

export default async function DashboardPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/dashboard");

  let backendStatus = "Connected";
  let backendUser: BackendUser | null = null;
  let projects: Project[] = [];
  let connections: Connection[] = [];
  let plans: Plan[] = [];
  let recentRuns: Array<{ run: RecentRun; plan: Plan; project: Project }> = [];
  let apiError: string | null = null;

  try {
    const { token } = await auth0.getAccessToken();
    if (!token) throw new Error("Auth0 did not return an API access token.");
    const [me, projectRows] = await Promise.all([
      apiRequest<BackendUser>("/users/me", token, { cache: "no-store" }),
      apiRequest<Project[]>("/projects", token, { cache: "no-store" }),
    ]);
    backendUser = me;
    projects = projectRows;
    const workspaceData = await Promise.all(projectRows.map(async (project) => {
      const [projectConnections, projectPlans] = await Promise.all([
        apiRequest<Connection[]>(`/projects/${project.id}/connections`, token, { cache: "no-store" }),
        apiRequest<Plan[]>(`/projects/${project.id}/migration-plans`, token, { cache: "no-store" }),
      ]);
      const planRuns = await Promise.all(projectPlans.map(async (plan) => {
        try {
          const runs = await apiRequest<RecentRun[]>(`/projects/${project.id}/migration-plans/${plan.id}/runs`, token, { cache: "no-store" });
          return runs.map((run) => ({ run, plan, project }));
        } catch { return []; }
      }));
      return { projectConnections, projectPlans, planRuns: planRuns.flat() };
    }));
    connections = workspaceData.flatMap((item) => item.projectConnections);
    plans = workspaceData.flatMap((item) => item.projectPlans);
    recentRuns = workspaceData.flatMap((item) => item.planRuns).sort((a,b) => new Date(b.run.created_at).getTime() - new Date(a.run.created_at).getTime()).slice(0,8);
  } catch (error) {
    backendStatus = "Needs attention";
    apiError = error instanceof Error ? error.message : "Unable to load workspace data.";
  }

  const sourceCount = connections.filter((item) => item.role === "source").length;
  const destinationCount = connections.filter((item) => item.role === "destination").length;
  const providerCounts = connections.reduce((counts, connection) => {
    const host = connection.host.toLowerCase();
    const provider = host.includes("supabase") ? "Supabase" : host.includes("neon.tech") ? "Neon" : host.includes("render.com") ? "Render" : "PostgreSQL / other";
    counts[provider] = (counts[provider] ?? 0) + 1;
    return counts;
  }, {} as Record<string, number>);
  const readyCount = plans.filter((item) => ["ready", "schema_prepared"].includes(item.status)).length;
  const draftCount = plans.filter((item) => item.status === "draft").length;
  const userLabel = session.user.name ?? session.user.email ?? "Workspace user";

  return (
    <AppShell userLabel={userLabel}>
      <div className="conduit-enter space-y-8">
        <section className="conduit-card flex flex-col justify-between gap-6 px-6 py-7 sm:flex-row sm:items-end sm:px-8 sm:py-8">
          <div className="max-w-2xl">
            <p className="conduit-eyebrow">Migration command center</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 sm:text-[38px]">Move data with confidence.</h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-500">Orchestrate database migrations from discovery to validation. Your projects, connections, and migration plans live in one workspace.</p>
            <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-500">
              <span className="inline-flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${backendStatus === "Connected" ? "bg-emerald-500" : "bg-amber-500"}`}/>{backendStatus === "Connected" ? "API connected" : "API connection needs attention"}</span>
              <span className="inline-flex items-center gap-2"><ShieldCheck size={13}/> Authenticated workspace</span>
              <span className="inline-flex items-center gap-2"><Zap size={13}/> Batch-based execution</span>
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Link href="/dashboard/discovery" className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"><Database size={15}/> Discover databases</Link>
            <Link href="/dashboard/migration-planning" className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-indigo-700"><Plus size={16}/> Create migration plan <ArrowUpRight size={15}/></Link>
          </div>
        </section>

        {apiError && <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800"><CircleAlert size={18} className="mt-0.5 shrink-0"/><div><p className="font-semibold">Workspace data could not be fully loaded</p><p className="mt-1 break-words text-xs">{apiError}</p></div></div>}

        <section>
          <div className="mb-4 flex items-end justify-between gap-3">
            <div><p className="conduit-eyebrow">Workspace snapshot</p><h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">Your migration landscape</h2></div>
            <span className="text-xs text-slate-400">Live workspace records</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Projects" value={projects.length} detail="Organized migration workspaces" icon={<Boxes size={18}/>} tone="indigo"/>
            <MetricCard label="Connections" value={connections.length} detail={`${sourceCount} sources · ${destinationCount} destinations`} icon={<Cable size={18}/>} tone="sky"/>
            <MetricCard label="Migration plans" value={plans.length} detail={`${readyCount} ready · ${draftCount} in draft`} icon={<Workflow size={18}/>} tone="violet"/>
            <MetricCard label="Backend status" value={backendStatus === "Connected" ? "Online" : "Check"} detail="Authenticated API connectivity" icon={<Database size={18}/>} tone={backendStatus === "Connected" ? "emerald" : "amber"}/>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <div className="conduit-card p-5 sm:p-6">
            <p className="conduit-eyebrow">Connection providers</p><h2 className="mt-1 text-lg font-semibold">Database footprint</h2>
            <p className="mt-1 text-xs text-slate-500">Provider grouping is inferred from the saved hostname.</p>
            <div className="mt-4 space-y-3">{Object.entries(providerCounts).sort((a,b)=>b[1]-a[1]).map(([provider,count])=><div key={provider} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2.5"><span className="text-sm font-medium text-slate-700">{provider}</span><span className="text-sm font-semibold tabular-nums text-slate-900">{count}</span></div>)}</div>
          </div>
          <div className="conduit-card p-5 sm:p-6">
            <div className="flex items-center justify-between gap-2"><div><p className="conduit-eyebrow">Execution history</p><h2 className="mt-1 text-lg font-semibold">Recent migrations</h2></div><Link href="/dashboard/activity" className="text-xs font-semibold text-indigo-700">All activity <ArrowRight size={12} className="inline"/></Link></div>
            {recentRuns.length ? <div className="mt-4 divide-y divide-slate-100">{recentRuns.map(({run,plan,project})=><Link key={run.id} href={`/dashboard/migration-runs/${run.id}`} className="flex items-center justify-between gap-3 py-3"><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{plan.name}</p><p className="mt-0.5 truncate text-[11px] text-slate-500">{project.name} · {new Date(run.created_at).toLocaleString()}</p></div><span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold capitalize text-slate-600">{run.status.replaceAll("_"," ")}</span></Link>)}</div> : <p className="mt-4 rounded-lg bg-slate-50 p-4 text-xs text-slate-500">No migration runs have been queued yet.</p>}
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.45fr_1fr]">
          <div className="conduit-card p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3">
              <div><p className="conduit-eyebrow">Get started</p><h2 className="mt-1 text-lg font-semibold">Migration workflow</h2><p className="mt-1 text-xs text-slate-500">A clear path from source database to verified destination.</p></div>
              <span className="rounded-lg bg-indigo-50 p-2 text-indigo-700"><GitBranch size={18}/></span>
            </div>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <WorkflowCard number="01" title="Connect databases" description="Register source and destination systems, then test connectivity." icon={<Cable size={18}/>} href="/dashboard/connections" action="Manage connections"/>
              <WorkflowCard number="02" title="Discover databases" description="Verify connections and inspect schemas, tables, and columns." icon={<Database size={18}/>} href="/dashboard/discovery" action="Open discovery"/>
              <WorkflowCard number="03" title="Prepare & execute" description="Validate the plan, preview DDL, and queue a batch migration." icon={<Zap size={18}/>} href="/dashboard/migration-planning" action="Configure execution"/>
              <WorkflowCard number="04" title="Verify results" description="Review row outcomes, reconciliation, and downloadable reports." icon={<ShieldCheck size={18}/>} href="/dashboard/validation" action="View validation"/>
            </div>
          </div>

          <div className="conduit-card p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3"><div><p className="conduit-eyebrow">Plan readiness</p><h2 className="mt-1 text-lg font-semibold">Migration plans</h2><p className="mt-1 text-xs text-slate-500">Current preparation status across projects.</p></div><ListIcon/></div>
            <div className="mt-7 space-y-5">
              <StatusBar label="Ready to execute" count={readyCount} total={plans.length} color="bg-emerald-500"/>
              <StatusBar label="Draft plans" count={draftCount} total={plans.length} color="bg-indigo-500"/>
              <StatusBar label="Other statuses" count={Math.max(0, plans.length-readyCount-draftCount)} total={plans.length} color="bg-slate-400"/>
            </div>
            <div className="mt-7 rounded-xl bg-slate-50 p-4">
              <p className="text-xs font-semibold text-slate-800">A good migration starts with a validated plan.</p>
              <p className="mt-1 text-xs leading-5 text-slate-500">Check table selection, column mappings, and destination readiness before queuing execution.</p>
              <Link href="/dashboard/migration-planning" className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-indigo-700 hover:text-indigo-900">Review plans <ArrowRight size={13}/></Link>
            </div>
          </div>
        </section>

        <section className="conduit-card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-5 sm:px-6">
            <div><p className="conduit-eyebrow">Your workspace</p><h2 className="mt-1 text-lg font-semibold">Recent projects</h2></div>
            <Link href="/dashboard/projects" className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-700 hover:text-indigo-900">All projects <ArrowRight size={14}/></Link>
          </div>
          {projects.length ? <div className="divide-y divide-slate-100">
            {projects.slice(0,5).map((project) => {
              return <div key={project.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 transition hover:bg-slate-50/70 sm:px-6">
                <div className="flex min-w-0 items-center gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600"><Boxes size={18}/></span><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{project.name}</p><p className="mt-0.5 text-[11px] text-slate-400">Project workspace · {project.status ?? "Active"}</p></div></div>
                <div className="flex items-center gap-4"><Link href="/dashboard/migration-planning" className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700">Open <ArrowUpRight size={13}/></Link></div>
              </div>;
            })}
          </div> : <div className="px-6 py-12 text-center"><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500"><Boxes size={21}/></div><p className="mt-3 text-sm font-semibold text-slate-800">No projects yet</p><p className="mt-1 text-xs text-slate-500">Create your first project to start organizing database migrations.</p><Link href="/dashboard/projects" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700"><Plus size={14}/> Create project</Link></div>}
        </section>

        <footer className="flex flex-wrap items-center justify-between gap-2 pb-2 text-[10px] text-slate-400"><span>CONDUIT · Enterprise data migration workspace</span><span>{backendUser?.email ?? session.user.email ?? "Signed in"}</span></footer>
      </div>
    </AppShell>
  );
}

function MetricCard({label,value,detail,icon,tone}:{label:string;value:string|number;detail:string;icon:React.ReactNode;tone:string}) {
  const tones:Record<string,string>={indigo:"bg-indigo-50 text-indigo-700",sky:"bg-sky-50 text-sky-700",violet:"bg-violet-50 text-violet-700",emerald:"bg-emerald-50 text-emerald-700",amber:"bg-amber-50 text-amber-700"};
  return <div className="conduit-card p-5 transition hover:-translate-y-0.5 hover:shadow-md"><div className="flex items-center justify-between"><span className="text-xs font-semibold text-slate-500">{label}</span><span className={`flex h-9 w-9 items-center justify-center rounded-xl ${tones[tone] ?? tones.indigo}`}>{icon}</span></div><p className="mt-4 text-[30px] font-semibold tracking-tight text-slate-900">{value}</p><p className="mt-1 text-[11px] text-slate-400">{detail}</p></div>;
}

function WorkflowCard({number,title,description,icon,href,action}:{number:string;title:string;description:string;icon:React.ReactNode;href:string;action:string}) {
  return <Link href={href} className="group rounded-2xl border border-slate-200 p-4 transition hover:border-indigo-200 hover:bg-indigo-50/40 hover:shadow-sm"><div className="flex items-center justify-between"><span className="text-[10px] font-bold tracking-[.14em] text-slate-300">{number}</span><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-600 transition group-hover:bg-indigo-100 group-hover:text-indigo-700">{icon}</span></div><h3 className="mt-4 text-sm font-semibold text-slate-800">{title}</h3><p className="mt-1 min-h-[40px] text-xs leading-5 text-slate-500">{description}</p><span className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-700">{action} <ArrowUpRight size={12}/></span></Link>;
}

function StatusBar({label,count,total,color}:{label:string;count:number;total:number;color:string}) {
  const percent=total?Math.round(count/total*100):0;
  return <div><div className="mb-2 flex items-center justify-between gap-3"><span className="text-xs font-medium text-slate-600">{label}</span><span className="text-xs font-semibold tabular-nums text-slate-800">{count}<span className="font-normal text-slate-400"> / {total}</span></span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${color}`} style={{width:`${percent}%`}}/></div></div>;
}

function ListIcon(){return <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700"><CheckCircle2 size={18}/></span>}
