"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle, CheckCircle2, ChevronRight, Database,
  Layers3, LoaderCircle, Play, RefreshCw, Search, ShieldCheck, Table2,
} from "lucide-react";
import {
  DiscoveredSchema, DiscoveredTable, DiscoveredTableDetail, DiscoverySnapshot,
  loadDiscoveredTableDetailAction, loadDiscoveryAction, runDiscoveryAction, verifyConnectionAction,
} from "./actions";

type Project = { id: string; name: string };
type Connection = {
  id: string; name: string; role: "source" | "destination";
  database: string; host: string; port: number;
};

export default function DiscoveryClient({
  projects, connectionsByProject,
}: {
  projects: Project[];
  connectionsByProject: Record<string, Connection[]>;
}) {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const connections = connectionsByProject[projectId] ?? [];
  const [connectionId, setConnectionId] = useState(connections[0]?.id ?? "");
  const [snapshot, setSnapshot] = useState<DiscoverySnapshot | null>(null);
  const [schemas, setSchemas] = useState<DiscoveredSchema[]>([]);
  const [tables, setTables] = useState<DiscoveredTable[]>([]);
  const [schemaFilter, setSchemaFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [selectedTable, setSelectedTable] = useState<DiscoveredTableDetail | null>(null);
  const [busy, setBusy] = useState<"verify" | "discover" | "load" | "">("");
  const [verification, setVerification] = useState<{success:boolean;message:string;server_version?:string|null}|null>(null);
  const [error, setError] = useState("");

  const visibleTables = useMemo(() => tables.filter((table) =>
    (schemaFilter === "all" || table.schema_name === schemaFilter) &&
    `${table.schema_name}.${table.name}`.toLowerCase().includes(search.toLowerCase()),
  ), [tables, schemaFilter, search]);

  function changeProject(id: string) {
    setProjectId(id);
    const next = connectionsByProject[id] ?? [];
    setConnectionId(next[0]?.id ?? "");
    setSnapshot(null); setSchemas([]); setTables([]); setSelectedTable(null);
    setVerification(null); setError(""); setSchemaFilter("all");
  }

  async function verify() {
    if (!projectId || !connectionId) return;
    setBusy("verify"); setError(""); setVerification(null);
    try {
      setVerification(await verifyConnectionAction(projectId, connectionId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Connection verification failed.");
    } finally { setBusy(""); }
  }

  async function discover() {
    if (!projectId || !connectionId) return;
    setBusy("discover"); setError(""); setSelectedTable(null);
    try {
      const result = await runDiscoveryAction(projectId, connectionId);
      setSnapshot(result.snapshot); setSchemas(result.schemas); setTables(result.tables);
      setSchemaFilter("all");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Database discovery failed.");
    } finally { setBusy(""); }
  }

  async function loadPrevious() {
    if (!projectId || !connectionId) return;
    setBusy("load"); setError("");
    try {
      const result = await loadDiscoveryAction(projectId, connectionId);
      setSnapshot(result.snapshot); setSchemas(result.schemas); setTables(result.tables);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No discovery snapshot could be loaded.");
    } finally { setBusy(""); }
  }

  async function inspectTable(table: DiscoveredTable) {
    setBusy("load"); setError("");
    try {
      setSelectedTable(await loadDiscoveredTableDetailAction(projectId, connectionId, table.id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load table details.");
    } finally { setBusy(""); }
  }

  const selectedConnection = connections.find((item) => item.id === connectionId);
  const busyLabel = busy === "verify" ? "Verifying…" : busy === "discover" ? "Discovering…" : "Loading…";

  if (!projects.length) {
    return <section className="conduit-card p-8 text-center">
      <Database className="mx-auto text-slate-400" size={28}/>
      <h2 className="mt-3 text-base font-semibold text-slate-900">No projects available</h2>
      <p className="mt-1 text-sm text-slate-500">Create a project and add a database connection before running discovery.</p>
      <Link href="/dashboard/projects" className="mt-4 inline-flex rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white">Create a project</Link>
    </section>;
  }

  return <div className="space-y-6">
    <section className="conduit-card p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700"><Database size={19}/></span>
        <div><h2 className="text-base font-semibold text-slate-900">Select a database</h2><p className="mt-1 text-xs leading-5 text-slate-500">Choose a project and either its source or destination connection. Discovery reads database metadata; it does not modify application data.</p></div>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="block text-xs font-semibold text-slate-600">Project
          <select value={projectId} onChange={(event) => changeProject(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-normal">
            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </label>
        <label className="block text-xs font-semibold text-slate-600">Database connection
          <select value={connectionId} onChange={(event) => { setConnectionId(event.target.value); setSnapshot(null); setSchemas([]); setTables([]); setSelectedTable(null); setVerification(null); setError(""); }} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-normal" disabled={!connections.length}>
            {connections.length ? connections.map((connection) => <option key={connection.id} value={connection.id}>{connection.name} · {connection.role}</option>) : <option value="">No connections in this project</option>}
          </select>
        </label>
      </div>
      {selectedConnection && <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl bg-slate-50 px-4 py-3 text-xs text-slate-600">
        <span className="font-semibold text-slate-800">{selectedConnection.name}</span>
        <span>{selectedConnection.host}:{selectedConnection.port}</span>
        <span>Database: {selectedConnection.database}</span>
        <span className={selectedConnection.role === "source" ? "font-semibold text-sky-700" : "font-semibold text-violet-700"}>{selectedConnection.role.toUpperCase()}</span>
      </div>}
      <div className="mt-5 flex flex-wrap gap-2">
        <button onClick={verify} disabled={!connectionId || !!busy} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">
          {busy === "verify" ? <LoaderCircle size={15} className="animate-spin"/> : <ShieldCheck size={15}/>} Verify connection
        </button>
        <button onClick={discover} disabled={!connectionId || !!busy} className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50">
          {busy === "discover" ? <LoaderCircle size={15} className="animate-spin"/> : <Play size={14}/>} {snapshot ? "Run discovery again" : "Run discovery"}
        </button>
        <button onClick={loadPrevious} disabled={!connectionId || !!busy} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50">
          <RefreshCw size={14}/> Load latest results
        </button>
      </div>
      {busy && <p className="mt-3 text-xs text-slate-500">{busyLabel} Keep this page open while the request completes.</p>}
      {verification && <div className={`mt-4 flex items-start gap-2 rounded-xl border p-3 text-xs ${verification.success ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"}`}>
        {verification.success ? <CheckCircle2 size={16}/> : <AlertCircle size={16}/>}
        <div><p className="font-semibold">{verification.success ? "Connection verified" : "Connection test failed"}</p><p className="mt-1">{verification.message}{verification.server_version ? ` · ${verification.server_version}` : ""}</p></div>
      </div>}
      {error && <div className="mt-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700"><AlertCircle size={16}/><p className="break-words">{error}</p></div>}
    </section>

    {snapshot && <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Summary label="Database" value={snapshot.database_name} icon={<Database size={17}/>} />
        <Summary label="Schemas" value={snapshot.schema_count} icon={<Layers3 size={17}/>} />
        <Summary label="Tables & views" value={snapshot.table_count} icon={<Table2 size={17}/>} />
        <Summary label="Discovery status" value={snapshot.status} icon={<CheckCircle2 size={17}/>} />
      </section>
      <section className="conduit-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 sm:px-6">
          <div><h2 className="text-sm font-semibold text-slate-900">Discovered objects</h2><p className="mt-1 text-xs text-slate-500">{snapshot.server_version ?? "Server version unavailable"}{snapshot.discovered_at ? ` · Completed ${new Date(snapshot.discovered_at).toLocaleString()}` : ""}</p></div><Link href="/dashboard/migration-planning" className="inline-flex items-center rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-700">Continue to migration planning</Link>
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">{snapshot.status}</span>
        </div>
        <div className="grid gap-0 lg:grid-cols-[240px_minmax(0,1fr)]">
          <aside className="border-b border-slate-100 p-4 lg:border-b-0 lg:border-r">
            <p className="mb-3 text-[10px] font-bold uppercase tracking-wider text-slate-400">Schemas</p>
            <button onClick={() => setSchemaFilter("all")} className={`mb-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs ${schemaFilter === "all" ? "bg-indigo-50 font-semibold text-indigo-700" : "text-slate-600 hover:bg-slate-50"}`}><span>All schemas</span><span>{tables.length}</span></button>
            {schemas.filter((schema) => !schema.is_system).map((schema) => <button key={schema.id} onClick={() => setSchemaFilter(schema.name)} className={`mb-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs ${schemaFilter === schema.name ? "bg-indigo-50 font-semibold text-indigo-700" : "text-slate-600 hover:bg-slate-50"}`}><span className="truncate">{schema.name}</span><span>{schema.table_count}</span></button>)}
          </aside>
          <div className="min-w-0 p-4 sm:p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div><h3 className="text-sm font-semibold text-slate-800">{schemaFilter === "all" ? "All discovered tables" : schemaFilter}</h3><p className="mt-1 text-[11px] text-slate-400">{visibleTables.length} objects</p></div>
              <label className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-500"><Search size={14}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search tables" className="w-36 border-0 p-0 text-xs outline-none focus:ring-0"/></label>
            </div>
            {visibleTables.length ? <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="border-b border-slate-100"><th className="py-3 pr-3">Object</th><th className="py-3 pr-3">Schema</th><th className="py-3 pr-3">Type</th><th className="py-3 pr-3 text-right">Estimated rows</th><th className="py-3 text-right">Details</th></tr></thead><tbody className="divide-y divide-slate-100">{visibleTables.map((table) => <tr key={table.id} className="hover:bg-slate-50"><td className="py-3 pr-3 font-semibold text-slate-800">{table.name}</td><td className="py-3 pr-3 text-slate-500">{table.schema_name}</td><td className="py-3 pr-3 capitalize text-slate-500">{table.table_type.replace("_", " ")}</td><td className="py-3 pr-3 text-right tabular-nums text-slate-600">{table.estimated_rows?.toLocaleString() ?? "—"}</td><td className="py-3 text-right"><button onClick={() => inspectTable(table)} disabled={!!busy} className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50">Inspect <ChevronRight size={13}/></button></td></tr>)}</tbody></table></div> : <p className="rounded-xl bg-slate-50 px-4 py-8 text-center text-xs text-slate-500">No tables match this filter.</p>}
          </div>
        </div>
      </section>
      {selectedTable && <section className="conduit-card p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3"><div><p className="conduit-eyebrow">Table definition</p><h2 className="mt-1 text-lg font-semibold text-slate-900">{selectedTable.schema_name}.{selectedTable.name}</h2><p className="mt-1 text-xs text-slate-500">{selectedTable.comment ?? selectedTable.table_type}</p></div><button onClick={() => setSelectedTable(null)} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50">Close details</button></div>
        <div className="mt-5 flex flex-wrap gap-4 text-xs text-slate-500"><span>{selectedTable.columns.length} columns</span><span>Primary key: {selectedTable.primary_key?.constrained_columns?.join(", ") || "Not defined"}</span><span>{selectedTable.foreign_keys.length} foreign keys</span><span>{selectedTable.indexes.length} indexes</span></div>
        <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="border-b border-slate-100"><th className="py-3 pr-3">Column</th><th className="py-3 pr-3">Type</th><th className="py-3 pr-3">Nullable</th><th className="py-3">Default</th></tr></thead><tbody className="divide-y divide-slate-100">{selectedTable.columns.map((column, index) => <tr key={String(column.name ?? index)}><td className="py-3 pr-3 font-semibold text-slate-800">{String(column.name ?? "—")}</td><td className="py-3 pr-3 text-slate-600">{String(column.type ?? "—")}</td><td className="py-3 pr-3 text-slate-600">{column.nullable === true ? "Yes" : column.nullable === false ? "No" : "—"}</td><td className="py-3 text-slate-500">{String(column.default ?? "—")}</td></tr>)}</tbody></table></div>
      </section>}
    </>}
    {!snapshot && <section className="conduit-card px-6 py-12 text-center"><Database size={28} className="mx-auto text-slate-300"/><h2 className="mt-3 text-sm font-semibold text-slate-800">No discovery results loaded</h2><p className="mt-1 text-xs text-slate-500">Verify the selected connection, then run discovery to inspect database metadata.</p></section>}
  </div>;
}

function Summary({label,value,icon}:{label:string;value:string|number;icon:React.ReactNode}) {
  return <div className="conduit-card p-4"><div className="flex items-center justify-between"><p className="text-[11px] font-medium text-slate-500">{label}</p><span className="rounded-lg bg-slate-100 p-2 text-slate-600">{icon}</span></div><p className="mt-3 truncate text-lg font-semibold capitalize text-slate-900">{typeof value === "number" ? value.toLocaleString() : value}</p></div>;
}
