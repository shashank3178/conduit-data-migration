"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Pencil, Trash2, DatabaseZap, X, Save } from "lucide-react";
import { deleteConnection, discoverConnection, updateConnection } from "./actions";

type Connection = {
  id: string; name: string; role: "source" | "destination"; host: string;
  port: number; database: string; username: string; sslmode: string;
};

export default function ConnectionManagement({ projectId, connection }: { projectId: string; connection: Connection }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(connection.name);
  const [role, setRole] = useState(connection.role);
  const [host, setHost] = useState(connection.host);
  const [port, setPort] = useState(String(connection.port));
  const [database, setDatabase] = useState(connection.database);
  const [username, setUsername] = useState(connection.username);
  const [password, setPassword] = useState("");
  const [sslmode, setSslmode] = useState(connection.sslmode);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, startTransition] = useTransition();

  function run(work: () => Promise<unknown>, success: string) {
    setError(""); setMessage("");
    startTransition(async () => {
      try { await work(); setMessage(success); router.refresh(); }
      catch (cause) { setError(cause instanceof Error ? cause.message : "The operation failed."); }
    });
  }

  return <div className="mt-4 space-y-3">
    <div className="flex flex-wrap gap-2">
      <button disabled={pending} onClick={() => run(() => discoverConnection(projectId, connection.id), "Discovery completed. The latest database metadata is now available.")} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"><DatabaseZap size={13}/> Discover</button>
      <button disabled={pending} onClick={() => setEditing(!editing)} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">{editing ? <X size={13}/> : <Pencil size={13}/>} {editing ? "Close editor" : "Edit connection"}</button>
      <button disabled={pending} onClick={() => { if (window.confirm("Delete this connection? Plans referencing it may also be deleted by database constraints. This cannot be undone.")) run(() => deleteConnection(projectId, connection.id), "Connection deleted."); }} className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 px-3 py-2 text-[11px] font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50"><Trash2 size={13}/> Delete</button>
    </div>
    {editing && <form onSubmit={(event) => { event.preventDefault(); run(() => updateConnection(projectId, connection.id, { name, role, host, port: Number(port), database, username, sslmode, ...(password ? { password } : {}) }), "Connection updated."); setEditing(false); }} className="grid gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:grid-cols-2 lg:grid-cols-3">
      <Field label="Name"><input required value={name} onChange={e=>setName(e.target.value)}/></Field>
      <Field label="Role"><select value={role} onChange={e=>setRole(e.target.value as typeof role)}><option value="source">Source</option><option value="destination">Destination</option></select></Field>
      <Field label="Host"><input required value={host} onChange={e=>setHost(e.target.value)}/></Field>
      <Field label="Port"><input required type="number" min="1" max="65535" value={port} onChange={e=>setPort(e.target.value)}/></Field>
      <Field label="Database"><input required value={database} onChange={e=>setDatabase(e.target.value)}/></Field>
      <Field label="Username"><input required value={username} onChange={e=>setUsername(e.target.value)}/></Field>
      <Field label="New password (optional)"><input type="password" autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Leave blank to keep current"/></Field>
      <Field label="SSL mode"><select value={sslmode} onChange={e=>setSslmode(e.target.value)}>{["prefer","require","verify-ca","verify-full","allow","disable"].map(value=><option key={value}>{value}</option>)}</select></Field>
      <div className="flex items-end"><button disabled={pending} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white disabled:opacity-50"><Save size={13}/> {pending ? "Saving…" : "Save changes"}</button></div>
    </form>}
    {message && <p className="text-xs text-emerald-700">{message}</p>}
    {error && <p className="text-xs text-rose-700">{error}</p>}
    <style jsx>{".field{width:100%;margin-top:5px;border:1px solid #dbe1ea;border-radius:8px;background:#fff;padding:9px 10px;font-size:12px;color:#334155}input,select{width:100%;margin-top:5px;border:1px solid #dbe1ea;border-radius:8px;background:#fff;padding:9px 10px;font-size:12px;color:#334155}"}</style>
  </div>;
}
function Field({label,children}:{label:string;children:React.ReactNode}) { return <label className="block text-[11px] font-semibold text-slate-600">{label}{children}</label>; }
