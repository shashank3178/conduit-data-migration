import Link from "next/link";
import {redirect} from "next/navigation";
import {auth0} from "@/lib/auth0";
import {apiRequest} from "@/lib/api";
import LiveRunsClient from "./live-runs-client";
export const dynamic="force-dynamic";
export default async function LiveRunsPage(){
 const session=await auth0.getSession();if(!session)redirect("/auth/login?returnTo=/dashboard/runs");
 const {token}=await auth0.getAccessToken();if(!token)redirect("/auth/login");
 const projects=await apiRequest<any[]>("/projects",token,{cache:"no-store"}),runs:any[]=[];
 for(const p of projects){const plans=await apiRequest<any[]>(`/projects/${p.id}/migration-plans`,token,{cache:"no-store"});for(const plan of plans){const list=await apiRequest<any[]>(`/projects/${p.id}/migration-plans/${plan.id}/runs`,token,{cache:"no-store"});for(const run of list)runs.push({...run,projectId:p.id,projectName:p.name,planId:plan.id,planName:plan.name})}}
 runs.sort((a,b)=>new Date(b.created_at).getTime()-new Date(a.created_at).getTime());
 return <main className="min-h-screen bg-[#10100e] text-[#f2eadb]"><div className="run-artwash min-h-screen"><header className="border-b border-[#d9bd8a]/20 bg-[#15130f]/90"><div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4"><Link href="/dashboard" className="font-serif text-2xl">CONDUIT</Link><nav className="flex gap-5 text-sm"><Link href="/dashboard">Workspace</Link><Link href="/dashboard/migration-planning">Planning</Link></nav></div></header><div className="mx-auto max-w-7xl px-5 py-10"><p className="eyebrow">Operations / Persistent execution</p><h1 className="display-title mt-3 font-serif text-7xl md:text-8xl">Live <em>runs.</em></h1><p className="mt-4 max-w-2xl text-sm text-[#c7b99f]">Workers continue independently of this browser view. Reopen a run to restore its persisted metrics.</p><LiveRunsClient initial={runs}/></div></div></main>;
}
