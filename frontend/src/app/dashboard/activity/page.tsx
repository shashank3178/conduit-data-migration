import { redirect } from "next/navigation";
import Link from "next/link";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import AppShell from "@/components/layout/app-shell";
import { Activity, ArrowUpRight, Clock3, Database, RefreshCw } from "lucide-react";

type Project={id:string;name:string};
type Plan={id:string;name:string;status:string};
type Run={id:string;status:string;created_at:string;total_rows:number;migrated_rows:number;inserted_rows:number;updated_rows:number;skipped_rows:number;failed_rows:number;validation_status:string;mismatch_rows:number;write_strategy:string};
type Item={project:Project;plan:Plan;run:Run};
const tone:Record<string,string>={completed:"bg-emerald-50 text-emerald-700",running:"bg-sky-50 text-sky-700",queued:"bg-amber-50 text-amber-700",failed:"bg-rose-50 text-rose-700",partially_failed:"bg-orange-50 text-orange-700",cancelled:"bg-slate-100 text-slate-600"};

export default async function ActivityPage(){
 const session=await auth0.getSession(); if(!session) redirect("/auth/login?returnTo=/dashboard/activity");
 let items:Item[]=[];let error="";
 try{
  const {token}=await auth0.getAccessToken();if(!token)throw new Error("No API access token was returned.");
  const projects=await apiRequest<Project[]>("/projects",token,{cache:"no-store"});
  const grouped=await Promise.all(projects.map(async project=>{
   const plans=await apiRequest<Plan[]>(`/projects/${project.id}/migration-plans`,token,{cache:"no-store"});
   return Promise.all(plans.map(async plan=>({project,plan,runs:await apiRequest<Run[]>(`/projects/${project.id}/migration-plans/${plan.id}/runs`,token,{cache:"no-store"})})));
  }));
  items=grouped.flat().flatMap(group=>group.runs.map(run=>({project:group.project,plan:group.plan,run}))).sort((a,b)=>new Date(b.run.created_at).getTime()-new Date(a.run.created_at).getTime());
 }catch(e){error=e instanceof Error?e.message:"Could not load migration activity."}
 const active=items.filter(x=>["queued","running","cancel_requested"].includes(x.run.status)).length;
 const failed=items.filter(x=>["failed","partially_failed"].includes(x.run.status)).length;
 const completed=items.filter(x=>x.run.status==="completed").length;
 return <AppShell userLabel={session.user.name??session.user.email}><div className="conduit-enter space-y-7">
  <div><p className="conduit-eyebrow">Operations</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Run activity</h1><p className="mt-2 text-sm text-slate-500">Track migration jobs across projects, inspect outcomes, and jump back into a plan.</p></div>
  {error&&<div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}
  <div className="grid gap-4 sm:grid-cols-3"><Stat label="Active runs" value={active} icon={<RefreshCw size={18}/>} /><Stat label="Completed runs" value={completed} icon={<Activity size={18}/>} /><Stat label="Needs attention" value={failed} icon={<Clock3 size={18}/>} /></div>
  <section className="conduit-card overflow-hidden"><div className="flex items-center justify-between border-b border-slate-100 px-5 py-5 sm:px-6"><div><p className="conduit-eyebrow">Migration history</p><h2 className="mt-1 text-lg font-semibold">Recent runs</h2></div><span className="rounded-full bg-slate-100 px-3 py-1 text-[10px] font-semibold text-slate-600">{items.length} total</span></div>
  {items.length?<div className="divide-y divide-slate-100">{items.slice(0,30).map(({project,plan,run})=><div key={run.id} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6"><div className="flex min-w-0 items-center gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600"><Database size={18}/></span><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{plan.name}</p><p className="mt-1 truncate text-[11px] text-slate-400">{project.name} · {new Date(run.created_at).toLocaleString()}</p></div></div><div className="flex flex-wrap items-center gap-3"><span className="text-[11px] text-slate-500">{run.migrated_rows.toLocaleString()} / {run.total_rows.toLocaleString()} rows</span><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold capitalize ${tone[run.status]??"bg-slate-100 text-slate-600"}`}>{run.status.replaceAll("_"," ")}</span><Link href={"/dashboard/migration-runs/" + run.id} className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50 hover:text-indigo-700" aria-label="Open migration run details"><ArrowUpRight size={14}/></Link></div></div>)}</div>:<div className="px-6 py-14 text-center"><Activity size={26} className="mx-auto text-slate-400"/><h3 className="mt-3 text-sm font-semibold">No migration runs yet</h3><p className="mt-1 text-xs text-slate-500">Queued and completed migrations will appear here.</p><Link href="/dashboard/migration-planning" className="mt-4 inline-flex rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white">Create a migration plan</Link></div>}</section>
 </div></AppShell>
}
function Stat({label,value,icon}:{label:string;value:number;icon:React.ReactNode}){return <div className="conduit-card p-5"><div className="flex items-center justify-between"><span className="text-xs font-medium text-slate-500">{label}</span><span className="rounded-lg bg-slate-100 p-2 text-slate-600">{icon}</span></div><p className="mt-3 text-2xl font-semibold">{value}</p></div>}
