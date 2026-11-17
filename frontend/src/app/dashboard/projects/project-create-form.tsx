"use client";

import { FormEvent, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Plus, X } from "lucide-react";
import { createProjectAction } from "./actions";

export default function ProjectCreateForm() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [pending, startTransition] = useTransition();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    startTransition(async () => {
      try {
        await createProjectAction({ name: name.trim(), description: description.trim() });
        setName(""); setDescription(""); setOpen(false); router.refresh();
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Could not create project.");
      }
    });
  }

  return <div className="conduit-card p-5 sm:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><p className="conduit-eyebrow">New workspace</p><h2 className="mt-1 text-sm font-semibold">Create a project</h2><p className="mt-1 text-xs text-slate-500">Give a migration initiative a clear name and description.</p></div>
      <button onClick={() => setOpen(!open)} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">{open ? <X size={14}/> : <Plus size={14}/>} {open ? "Close" : "New project"}</button>
    </div>
    {open && <form onSubmit={submit} className="mt-5 grid gap-3 sm:grid-cols-[1fr_1.5fr_auto] sm:items-end">
      <label className="text-xs font-semibold text-slate-600">Project name<input required maxLength={200} value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. Customer data modernization" className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-normal"/></label>
      <label className="text-xs font-semibold text-slate-600">Description <span className="font-normal text-slate-400">(optional)</span><input value={description} onChange={e=>setDescription(e.target.value)} placeholder="What are you migrating?" className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-normal"/></label>
      <button disabled={pending||!name.trim()} className="rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">{pending?"Creating…":"Create project"}</button>
      {error&&<p className="text-xs text-rose-600 sm:col-span-3">{error}</p>}
    </form>}
  </div>;
}
