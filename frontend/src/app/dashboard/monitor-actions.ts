"use server";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";

async function token() {
  if (!(await auth0.getSession())) throw new Error("Your session has expired.");
  const result = await auth0.getAccessToken();
  if (!result.token) throw new Error("Auth0 did not return an API access token.");
  return result.token;
}
export async function loadRunMonitor(projectId:string, planId:string, runId:string) {
  const t=await token(), base=`/projects/${projectId}/migration-plans/${planId}/runs/${runId}`;
  const [run,tables,batches,metrics,events]=await Promise.all([
    apiRequest<any>(base,t,{cache:"no-store"}),
    apiRequest<any[]>(base+"/tables",t,{cache:"no-store"}),
    apiRequest<any[]>(base+"/batches",t,{cache:"no-store"}),
    apiRequest<any>(base+"/metrics",t,{cache:"no-store"}),
    apiRequest<any[]>(base+"/events",t,{cache:"no-store"})
  ]);
  return {run,tables,batches,metrics,events};
}
export async function loadLiveRuns() {
  const t=await token(), projects=await apiRequest<any[]>("/projects",t,{cache:"no-store"}), runs:any[]=[];
  for(const project of projects){
    const plans=await apiRequest<any[]>(`/projects/${project.id}/migration-plans`,t,{cache:"no-store"});
    for(const plan of plans){
      const items=await apiRequest<any[]>(`/projects/${project.id}/migration-plans/${plan.id}/runs`,t,{cache:"no-store"});
      for(const run of items) runs.push({...run,projectId:project.id,projectName:project.name,planId:plan.id,planName:plan.name});
    }
  }
  const enriched = await Promise.all(runs.map(async (run) => ({ ...run, metrics: await apiRequest<any>(`/projects/${run.projectId}/migration-plans/${run.planId}/runs/${run.id}/metrics`, t, { cache: "no-store" }) })));
  return enriched.sort((a,b)=>new Date(b.created_at).getTime()-new Date(a.created_at).getTime());
}
