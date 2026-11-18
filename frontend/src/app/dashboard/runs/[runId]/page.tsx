import {notFound,redirect} from "next/navigation";
import {auth0} from "@/lib/auth0";
import {apiRequest} from "@/lib/api";
import RunMonitor from "../../run-monitor";
export const dynamic="force-dynamic";
export default async function RunPage({params,searchParams}:{params:Promise<{runId:string}>;searchParams:Promise<{projectId?:string;planId?:string}>}){
 const [{runId},q]=await Promise.all([params,searchParams]);if(!q.projectId||!q.planId)notFound();
 const session=await auth0.getSession();if(!session)redirect("/auth/login?returnTo=/dashboard/runs");
 const {token}=await auth0.getAccessToken();if(!token)redirect("/auth/login");
 const base=`/projects/${q.projectId}/migration-plans/${q.planId}/runs/${runId}`;
 try{const [run,tables,batches,metrics,events]=await Promise.all([apiRequest<any>(base,token,{cache:"no-store"}),apiRequest<any[]>(base+"/tables",token,{cache:"no-store"}),apiRequest<any[]>(base+"/batches",token,{cache:"no-store"}),apiRequest<any>(base+"/metrics",token,{cache:"no-store"}),apiRequest<any[]>(base+"/events",token,{cache:"no-store"})]);return <RunMonitor projectId={q.projectId} planId={q.planId} runId={runId} initial={{run,tables,batches,metrics,events}}/>}catch{notFound()}
}
