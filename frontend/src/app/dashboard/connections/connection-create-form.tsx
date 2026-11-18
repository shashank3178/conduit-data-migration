"use client";

import { FormEvent, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Cable, Plus, X } from "lucide-react";
import { createAndTestConnection } from "./actions";

type Project = { id: string; name: string };
export default function ConnectionCreateForm({ projects }: { projects: Project[] }) {
  const router = useRouter();
  const [open,setOpen]=useState(false);
  const [projectId,setProjectId]=useState(projects[0]?.id??"");
  const [name,setName]=useState("");
  const [role,setRole]=useState<"source"|"destination">("source");
  const [host,setHost]=useState("localhost");
  const [port,setPort]=useState("5432");
  const [database,setDatabase]=useState("");
  const [username,setUsername]=useState("");
  const [password,setPassword]=useState("");
  const [sslmode,setSslmode]=useState<"disable"|"allow"|"prefer"|"require"|"verify-ca"|"verify-full">("prefer");
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const [pending,startTransition]=useTransition();

  function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setError("");setMessage("");
    startTransition(async()=>{
      try{
        const result=await createAndTestConnection(projectId,{name:name.trim(),role,host:host.trim(),port:Number(port),database:database.trim(),username:username.trim(),password,sslmode});
        setMessage(result.test.success ? `Connection saved and verified. ${result.test.server_version ?? ""}` : `Connection saved, but the test failed: ${result.test.message}`);
        setName("");setDatabase("");setUsername("");setPassword("");setOpen(false);router.refresh();
      }catch(cause){setError(cause instanceof Error?cause.message:"Could not create connection.");}
    });
  }

  return <div className="conduit-card p-5 sm:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="conduit-eyebrow">Register database</p><h2 className="mt-1 text-sm font-semibold">Add a connection</h2><p className="mt-1 text-xs text-slate-500">Credentials are sent to the API and stored using the backend encryption service.</p></div><button disabled={!projects.length} onClick={()=>setOpen(!open)} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40">{open?<X size={14}/>:<Plus size={14}/>} {open?"Close":"New connection"}</button></div>
    {open&&<form onSubmit={submit} className="mt-5 space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Project"><select required value={projectId} onChange={e=>setProjectId(e.target.value)} className="field"><option value="">Select project</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
        <Field label="Connection name"><input required value={name} onChange={e=>setName(e.target.value)} placeholder="Production source" className="field"/></Field>
        <Field label="Role"><select value={role} onChange={e=>setRole(e.target.value as "source"|"destination")} className="field"><option value="source">Source database</option><option value="destination">Destination database</option></select></Field>
        <Field label="Host"><input required value={host} onChange={e=>setHost(e.target.value)} placeholder="localhost or hostname" className="field"/></Field>
        <Field label="Port"><input required type="number" min="1" max="65535" value={port} onChange={e=>setPort(e.target.value)} className="field"/></Field>
        <Field label="Database name"><input required value={database} onChange={e=>setDatabase(e.target.value)} placeholder="database_name" className="field"/></Field>
        <Field label="Username"><input required value={username} onChange={e=>setUsername(e.target.value)} placeholder="Database user" className="field"/></Field>
        <Field label="Password"><input required type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Database password" className="field" autoComplete="new-password"/></Field>
        <Field label="SSL mode"><select value={sslmode} onChange={e=>setSslmode(e.target.value as typeof sslmode)} className="field"><option value="prefer">Prefer</option><option value="require">Require</option><option value="verify-ca">Verify CA</option><option value="verify-full">Verify full</option><option value="allow">Allow</option><option value="disable">Disable</option></select></Field>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4"><p className="max-w-xl text-[11px] leading-5 text-slate-400"><Cable size={12} className="mr-1 inline"/>The connection is saved first, then CONDUIT attempts a connectivity test. Do not share database credentials outside the secure form.</p><button disabled={pending||!projectId} className="rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">{pending?"Saving & testing…":"Save and test connection"}</button></div>
    </form>}
    {message&&<p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">{message}</p>}
    {error&&<p className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">{error}</p>}
    <style jsx>{`.field{margin-top:6px;width:100%;border:1px solid #dfe3ec;border-radius:10px;background:#fff;padding:10px 12px;font-size:13px;color:#263248;outline:none}.field:focus{border-color:#7770ec;box-shadow:0 0 0 3px rgba(81,69,229,.10)}`}</style>
  </div>;
}
function Field({label,children}:{label:string;children:React.ReactNode}){return <label className="block text-xs font-semibold text-slate-600">{label}{children}</label>}
