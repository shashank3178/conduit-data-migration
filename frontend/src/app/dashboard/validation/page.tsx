import { redirect } from "next/navigation";
import Link from "next/link";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import AppShell from "@/components/layout/app-shell";
import { ArrowUpRight, CheckCircle2, FileCheck2, ShieldAlert } from "lucide-react";

type Project={id:string;name:string};
type Plan={id:string;name:string;status:string};
type Run={id:string;status:string;created_at:string;validation_status:string;mismatch_rows:number;total_rows:number;failed_rows:number;inserted_rows:number;updated_rows:number;skipped_rows:number};
type Item={project:Project;plan:Plan;run:Run};

export default async function ValidationPage(){
 const session=await auth0.getSession();if(!session)redirect("/auth/login?returnTo=/dashboard/validation");
 let items:Item[]=[];let error="";
 try{
  const {token}=await auth0.getAccessToken();if(!token)throw new Error("No API access token was returned.");
  const projects=await apiRequest<Project[]>("/projects",token,{cache:"no-store"});
  const grouped=await Promise.all(projects.map(async project=>{
   const plans=await apiRequest<Plan[]>(`/projects/${project.id}/migration-plans`,token,{cache:"no-store"});
   return Promise.all(plans.map(async plan=>({project,plan,runs:await apiRequest<Run[]>(`/projects/${project.id}/migration-plans/${plan.id}/runs`,token,{cache:"no-store"})})));
  }));
  items=grouped.flat().flatMap(group=>group.runs.map(run=>({project:group.project,plan:group.plan,run}))).sort((a,b)=>new Date(b.run.created_at).getTime()-new Date(a.run.created_at).getTime());
 }catch(e){error=e instanceof Error?e.message:"Could not load validation records."}
 const checked=items.filter(x=>!["pending","not_started",""].includes(x.run.validation_status??"pending"));
 const mismatches=checked.reduce((sum,x)=>sum+(x.run.mismatch_rows??0),0);
 const passed=checked.filter(x=>x.run.validation_status==="passed"||(x.run.validation_status==="completed"&&x.run.mismatch_rows===0)).length;
 const attention=checked.filter(x=>(x.run.mismatch_rows??0)>0||x.run.failed_rows>0).length;
 return <AppShell userLabel={session.user.name??session.user.email}><div className="conduit-enter space-y-7">
  <div><p className="conduit-eyebrow">Data quality</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Validation center</h1><p className="mt-2 text-sm text-slate-500">Review source-to-destination reconciliation and identify runs that need investigation.</p></div>
  {error&&<div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}</div>}
  <div className="grid gap-4 sm:grid-cols-3"><Stat label="Validated runs" value={checked.length} icon={<FileCheck2 size={18}/>} /><Stat label="Passed validation" value={passed} icon={<CheckCircle2 size={18}/>} /><Stat label="Rows mismatched" value={mismatches.toLocaleString()} icon={<ShieldAlert size={18}/>} /></div>
  <section className="conduit-card overflow-hidden"><div className="border-b border-slate-100 px-5 py-5 sm:px-6"><p className="conduit-eyebrow">Reconciliation results</p><h2 className="mt-1 text-lg font-semibold">Validation history</h2></div>
   {checked.length?<div className="divide-y divide-slate-100">{checked.map(({project,plan,run})=><div key={run.id} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6"><div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{plan.name}</p><p className="mt-1 text-[11px] text-slate-400">{project.name} · {new Date(run.created_at).toLocaleString()}</p></div><div className="flex flex-wrap items-center gap-3"><div className="text-right"><p className="text-xs font-semibold text-slate-800">{(run.mismatch_rows??0).toLocaleString()} mismatches</p><p className="text-[10px] text-slate-400">{(run.failed_rows??0).toLocaleString()} failed rows</p></div><span className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${(run.mismatch_rows??0)===0&&run.failed_rows===0?"bg-emerald-50 text-emerald-700":"bg-amber-50 text-amber-700"}`}>{(run.mismatch_rows??0)===0&&run.failed_rows===0?"No mismatches":"Review required"}</span><Link href="/dashboard/migration-planning" className="rounded-lg border border-slate-200 p-2 text-slate-500 hover:bg-slate-50 hover:text-indigo-700" aria-label="Open migration plan"><ArrowUpRight size={14}/></Link></div></div>)}</div>:<div className="px-6 py-14 text-center"><FileCheck2 size={26} className="mx-auto text-slate-400"/><h3 className="mt-3 text-sm font-semibold">No validation results yet</h3><p className="mt-1 text-xs text-slate-500">Once a migration completes, its reconciliation results will be available here.</p><Link href="/dashboard/migration-planning" className="mt-4 inline-flex rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white">Open migration planner</Link></div>}
  </section>
 </div></AppShell>
}
function Stat({label,value,icon}:{label:string;value:number|string;icon:React.ReactNode}){return <div className="conduit-card p-5"><div className="flex items-center justify-between"><span className="text-xs font-medium text-slate-500">{label}</span><span className="rounded-lg bg-slate-100 p-2 text-slate-600">{icon}</span></div><p className="mt-3 text-2xl font-semibold">{value}</p></div>}
