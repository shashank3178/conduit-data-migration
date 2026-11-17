import { redirect } from "next/navigation";
import Link from "next/link";
import {
  ArrowRight, ArrowUpRight, Boxes, Cable, CheckCircle2, CircleAlert,
  Database, GitBranch, Plus, ShieldCheck, Sparkles, Workflow, Zap,
} from "lucide-react";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import AppShell from "@/components/layout/app-shell";

interface BackendUser { id: string; email: string | null; }
interface Project { id: string; name: string; status?: string; created_at?: string; }
interface Connection { id: string; name: string; role: "source" | "destination"; database: string; host: string; port: number; }
interface Plan { id: string; name: string; status: string; }

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
      return { projectConnections, projectPlans };
    }));
    connections = workspaceData.flatMap((item) => item.projectConnections);
    plans = workspaceData.flatMap((item) => item.projectPlans);
  } catch (error) {
    backendStatus = "Needs attention";
    apiError = error instanceof Error ? error.message : "Unable to load workspace data.";
  }

  const sourceCount = connections.filter((item) => item.role === "source").length;
  const destinationCount = connections.filter((item) => item.role === "destination").length;
  const readyCount = plans.filter((item) => ["ready", "schema_prepared"].includes(item.status)).length;
  const draftCount = plans.filter((item) => item.status === "draft").length;
  const userLabel = session.user.name ?? session.user.email ?? "Workspace user";

  return (
    <AppShell userLabel={userLabel}>
      <div className="conduit-enter space-y-8">
        <section className="relative overflow-hidden rounded-[24px] bg-[#17233d] px-6 py-7 text-white shadow-[0_18px_50px_rgba(23,35,61,.14)] sm:px-8 sm:py-9">
          <div className="conduit-grid-bg pointer-events-none absolute inset-0 opacity-50"/>
          <div className="absolute -right-16 -top-28 h-72 w-72 rounded-full bg-indigo-500/25 blur-3xl"/>
          <div className="absolute bottom-[-110px] right-[25%] h-64 w-64 rounded-full bg-sky-400/10 blur-3xl"/>
          <div className="relative z-10 flex flex-col justify-between gap-7 lg:flex-row lg:items-end">
            <div className="max-w-2xl">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.07] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[.15em] text-indigo-200">
                <Sparkles size={12}/> Migration command center
              </div>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-[38px]">Move data with confidence.</h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">Orchestrate database migrations from discovery to validation. Your projects, connections, and migration plans live in one workspace.</p>
            </div>
            <Link href="/dashboard/migration-planning" className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-slate-900 shadow-lg transition hover:-translate-y-0.5 hover:bg-indigo-50">
              <Plus size={16}/> Create migration plan <ArrowUpRight size={15}/>
            </Link>
          </div>
          <div className="relative z-10 mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-white/10 pt-5 text-xs text-slate-300">
            <span className="inline-flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${backendStatus === "Connected" ? "bg-emerald-400" : "bg-amber-400"}`}/>{backendStatus === "Connected" ? "API connected" : "API connection needs attention"}</span>
            <span className="inline-flex items-center gap-2"><ShieldCheck size={13}/> Authenticated workspace</span>
            <span className="inline-flex items-center gap-2"><Zap size={13}/> Batch-based execution</span>
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

        <section className="grid gap-5 xl:grid-cols-[1.45fr_1fr]">
          <div className="conduit-card p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3">
              <div><p className="conduit-eyebrow">Get started</p><h2 className="mt-1 text-lg font-semibold">Migration workflow</h2><p className="mt-1 text-xs text-slate-500">A clear path from source database to verified destination.</p></div>
              <span className="rounded-lg bg-indigo-50 p-2 text-indigo-700"><GitBranch size={18}/></span>
            </div>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <WorkflowCard number="01" title="Connect databases" description="Register source and destination systems, then test connectivity." icon={<Cable size={18}/>} href="/dashboard/connections" action="Manage connections"/>
              <WorkflowCard number="02" title="Discover & map" description="Inspect schemas, choose tables, and map source columns." icon={<Database size={18}/>} href="/dashboard/migration-planning" action="Open migration planner"/>
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
              const projectConnections = connections.filter((item) => true);
              const projectPlans = plans.filter((item) => true);
              return <div key={project.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 transition hover:bg-slate-50/70 sm:px-6">
                <div className="flex min-w-0 items-center gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600"><Boxes size={18}/></span><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{project.name}</p><p className="mt-0.5 text-[11px] text-slate-400">Project workspace · {project.status ?? "Active"}</p></div></div>
                <div className="flex items-center gap-4"><span className="hidden text-xs text-slate-500 sm:inline">{projectConnections.length} connections</span><Link href="/dashboard/migration-planning" className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700">Open <ArrowUpRight size={13}/></Link></div>
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
