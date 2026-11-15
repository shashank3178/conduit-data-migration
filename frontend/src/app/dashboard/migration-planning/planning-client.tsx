"use client";

import { useMemo, useState } from "react";
import {
  applyDestinationDDL,
  createMigrationPlan,
  loadPlanTables,
  loadProjectPlanningData,
  previewDestinationDDL,
  regenerateMappingSuggestions,
  saveColumnMappings,
  saveTableSelection,
  validateMigrationPlan,
} from "./actions";

type Project = { id: string; name: string };
type Connection = { id: string; name: string; role: "source" | "destination"; database: string; host: string; port: number };
type Plan = { id: string; name: string; status: string; source_connection_id: string; destination_connection_id: string };
type Mapping = {
  id: string;
  source_column: string;
  destination_column: string | null;
  source_type: string;
  destination_type: string | null;
  included: boolean;
  compatible: boolean;
  match_strategy: string;
};
type PlanTable = {
  id: string;
  source_schema: string;
  source_table: string;
  source_table_type: string;
  destination_schema: string;
  destination_table: string;
  selected: boolean;
  destination_exists: boolean;
  estimated_rows: number | null;
  column_count: number;
  mappings: Mapping[];
};

export default function MigrationPlanningClient({
  projects,
  initialConnections,
  initialPlans,
}: {
  projects: Project[];
  initialConnections: Connection[];
  initialPlans: Plan[];
}) {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [connections, setConnections] = useState<Connection[]>(initialConnections);
  const [plans, setPlans] = useState<Plan[]>(initialPlans);
  const [planId, setPlanId] = useState("");
  const [planName, setPlanName] = useState("PostgreSQL migration");
  const [sourceId, setSourceId] = useState(initialConnections.find((item) => item.role === "source")?.id ?? "");
  const [destinationId, setDestinationId] = useState(initialConnections.find((item) => item.role === "destination")?.id ?? "");
  const [tables, setTables] = useState<PlanTable[]>([]);
  const [activeTableId, setActiveTableId] = useState("");
  const [validation, setValidation] = useState<any>(null);
  const [ddl, setDdl] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const activeTable = useMemo(
    () => tables.find((table) => table.id === activeTableId) ?? null,
    [tables, activeTableId],
  );

  async function refreshPlansAndConnections(id: string) {
    const data = await loadProjectPlanningData(id);
    setConnections(data.connections);
    setPlans(data.plans);
    setPlanId("");
    setTables([]);
    setActiveTableId("");
    setValidation(null);
    setDdl(null);
    setSourceId(data.connections.find((item: Connection) => item.role === "source")?.id ?? "");
    setDestinationId(data.connections.find((item: Connection) => item.role === "destination")?.id ?? "");
  }

  async function run<T>(work: () => Promise<T>, success?: (result: T) => void | Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await work();
      await success?.(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function openPlan(id: string) {
    setPlanId(id);
    setValidation(null);
    setDdl(null);
    await run(() => loadPlanTables(projectId, id), (result: any) => {
      setTables(result);
      setActiveTableId(result[0]?.id ?? "");
    });
  }

  async function createPlan() {
    await run(
      () => createMigrationPlan(projectId, {
        name: planName,
        source_connection_id: sourceId,
        destination_connection_id: destinationId,
        create_schemas: true,
      }),
      async (result: any) => {
        setPlans((current) => [result, ...current]);
        setPlanId(result.id);
        const nextTables = await loadPlanTables(projectId, result.id);
        setTables(nextTables);
        setActiveTableId(nextTables[0]?.id ?? "");
        setNotice("Migration plan created. Select the source tables to include.");
      },
    );
  }

  function updateTableLocal(tableId: string, patch: Partial<PlanTable>) {
    setTables((current) => current.map((table) => table.id === tableId ? { ...table, ...patch } : table));
  }

  async function saveSelection() {
    if (!planId) return;
    await run(
      () => saveTableSelection(projectId, planId, tables.map((table) => ({
        table_id: table.id,
        selected: table.selected,
        destination_schema: table.destination_schema,
        destination_table: table.destination_table,
      }))),
      (result: any) => {
        setTables(result);
        setValidation(null);
        setDdl(null);
        setNotice("Table selection and destination names saved.");
      },
    );
  }

  async function suggestMappings() {
    if (!planId) return;
    await run(
      () => regenerateMappingSuggestions(projectId, planId),
      (result: any) => {
        setTables(result);
        setValidation(null);
        setDdl(null);
        setNotice("Column mapping suggestions regenerated.");
      },
    );
  }

  function updateMappingLocal(sourceColumn: string, patch: Partial<Mapping>) {
    if (!activeTable) return;
    setTables((current) => current.map((table) => table.id === activeTable.id
      ? { ...table, mappings: table.mappings.map((mapping) => mapping.source_column === sourceColumn ? { ...mapping, ...patch } : mapping) }
      : table));
  }

  async function saveMappings() {
    if (!activeTable || !planId) return;
    await run(
      () => saveColumnMappings(projectId, planId, activeTable.id, activeTable.mappings.map((mapping) => ({
        source_column: mapping.source_column,
        destination_column: mapping.destination_column,
        destination_type: mapping.destination_type,
        included: mapping.included,
      }))),
      (result: any) => {
        setTables((current) => current.map((table) => table.id === activeTable.id ? { ...table, mappings: result } : table));
        setValidation(null);
        setDdl(null);
        setNotice("Column mappings saved.");
      },
    );
  }

  async function validate() {
    if (!planId) return;
    await run(() => validateMigrationPlan(projectId, planId), (result: any) => {
      setValidation(result);
      setNotice(result.valid ? "Plan validation passed." : "Resolve the validation errors before preparing the destination schema.");
      setPlans((current) => current.map((plan) => plan.id === planId ? { ...plan, status: result.valid ? "ready" : "draft" } : plan));
    });
  }

  async function preview() {
    if (!planId) return;
    await run(() => previewDestinationDDL(projectId, planId), (result: any) => {
      setDdl(result);
      setNotice("Destination DDL preview generated. Review every statement before applying.");
    });
  }

  async function applyDDL() {
    if (!planId) return;
    if (!window.confirm("Apply the displayed CREATE SCHEMA / CREATE TABLE statements to the destination database? No rows will be transferred.")) return;
    await run(() => applyDestinationDDL(projectId, planId), async (result: any) => {
      setNotice(result.message);
      setPlans((current) => current.map((plan) => plan.id === planId ? { ...plan, status: "schema_prepared" } : plan));
      const nextTables = await loadPlanTables(projectId, planId);
      setTables(nextTables);
    });
  }

  const sourceConnections = connections.filter((item) => item.role === "source");
  const destinationConnections = connections.filter((item) => item.role === "destination");
  const selectedCount = tables.filter((table) => table.selected).length;

  if (!projects.length) {
    return <section className="rounded-xl border bg-white p-6 text-sm text-slate-600">Create a project and register source and destination database connections before planning a migration.</section>;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">1. Migration configuration</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="text-sm font-medium text-slate-700">
            Project
            <select value={projectId} onChange={(event) => { const nextId = event.target.value; setProjectId(nextId); setBusy(true); setError(""); refreshPlansAndConnections(nextId).catch((cause) => setError(cause instanceof Error ? cause.message : "Unable to load project data.")).finally(() => setBusy(false)); }} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2.5">
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700">
            Existing migration plan
            <select value={planId} onChange={(event) => { const nextId = event.target.value; if (nextId) openPlan(nextId); else { setPlanId(""); setTables([]); setActiveTableId(""); setValidation(null); setDdl(null); } }} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2.5">
              <option value="">Create a new plan…</option>
              {plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name} · {plan.status}</option>)}
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700">
            Plan name
            <input value={planName} onChange={(event) => setPlanName(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 p-2.5" maxLength={160} />
          </label>
          <label className="text-sm font-medium text-slate-700">
            Source connection
            <select value={sourceId} onChange={(event) => setSourceId(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2.5">
              <option value="">Select source…</option>
              {sourceConnections.map((connection) => <option key={connection.id} value={connection.id}>{connection.name} · {connection.database}</option>)}
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700">
            Destination connection
            <select value={destinationId} onChange={(event) => setDestinationId(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2.5">
              <option value="">Select destination…</option>
              {destinationConnections.map((connection) => <option key={connection.id} value={connection.id}>{connection.name} · {connection.database}</option>)}
            </select>
          </label>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button disabled={busy || !projectId || !sourceId || !destinationId || sourceId === destinationId} onClick={createPlan} className="rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">Create migration plan</button>
          <span className="text-xs text-slate-500">Both connections must have completed Phase 3 discovery.</span>
        </div>
        {connections.length === 0 && <p className="mt-3 text-sm text-amber-700">No database connections found for this project.</p>}
      </section>

      {planId && (
        <>
          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">2. Select source tables</h2>
                <p className="mt-1 text-sm text-slate-500">{selectedCount} selected · {tables.length} discovered candidates</p>
              </div>
              <button disabled={busy || !tables.length} onClick={saveSelection} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold hover:bg-slate-50 disabled:opacity-50">Save selection</button>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="border-b bg-slate-50 text-xs uppercase text-slate-500">
                  <tr><th className="p-3">Include</th><th className="p-3">Source table</th><th className="p-3">Rows (estimate)</th><th className="p-3">Destination schema</th><th className="p-3">Destination table</th><th className="p-3">Target</th></tr>
                </thead>
                <tbody className="divide-y">
                  {tables.map((table) => (
                    <tr key={table.id} className={activeTableId === table.id ? "bg-blue-50/50" : ""}>
                      <td className="p-3"><input type="checkbox" checked={table.selected} disabled={table.source_table_type !== "table"} onChange={(event) => updateTableLocal(table.id, { selected: event.target.checked })} aria-label={`Select ${table.source_schema}.${table.source_table}`} /></td>
                      <td className="p-3">
                        <button onClick={() => setActiveTableId(table.id)} className="text-left font-medium text-blue-700 hover:underline">{table.source_schema}.{table.source_table}</button>
                        <div className="text-xs text-slate-500">{table.source_table_type} · {table.column_count} columns</div>
                      </td>
                      <td className="p-3 text-slate-600">{table.estimated_rows?.toLocaleString() ?? "—"}</td>
                      <td className="p-3"><input value={table.destination_schema} onChange={(event) => updateTableLocal(table.id, { destination_schema: event.target.value })} className="w-36 rounded border p-2" /></td>
                      <td className="p-3"><input value={table.destination_table} onChange={(event) => updateTableLocal(table.id, { destination_table: event.target.value })} className="w-40 rounded border p-2" /></td>
                      <td className="p-3">{table.destination_exists ? <span className="text-emerald-700">Existing</span> : <span className="text-slate-500">Create</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-slate-500">Views and materialized views are displayed for reference but are not selectable for destination table creation.</p>
          </section>

          {activeTable && (
            <section className="rounded-xl border bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">3. Column mappings</h2>
                  <p className="mt-1 text-sm text-slate-500">{activeTable.source_schema}.{activeTable.source_table} → {activeTable.destination_schema}.{activeTable.destination_table}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button disabled={busy} onClick={suggestMappings} className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50">Regenerate suggestions</button>
                  <button disabled={busy} onClick={saveMappings} className="rounded-lg bg-blue-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Save mappings</button>
                </div>
              </div>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[680px] text-left text-sm">
                  <thead className="border-b bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="p-3">Use</th><th className="p-3">Source column</th><th className="p-3">Source type</th><th className="p-3">Destination column</th><th className="p-3">Destination type</th><th className="p-3">Match</th></tr></thead>
                  <tbody className="divide-y">
                    {activeTable.mappings.map((mapping) => (
                      <tr key={mapping.source_column}>
                        <td className="p-3"><input type="checkbox" checked={mapping.included} onChange={(event) => updateMappingLocal(mapping.source_column, { included: event.target.checked })} /></td>
                        <td className="p-3 font-medium">{mapping.source_column}</td>
                        <td className="p-3 text-slate-600">{mapping.source_type}</td>
                        <td className="p-3"><input value={mapping.destination_column ?? ""} onChange={(event) => updateMappingLocal(mapping.source_column, { destination_column: event.target.value || null })} className="w-40 rounded border p-2" disabled={!mapping.included} /></td>
                        <td className="p-3"><input value={mapping.destination_type ?? ""} onChange={(event) => updateMappingLocal(mapping.source_column, { destination_type: event.target.value || null })} className="w-40 rounded border p-2" disabled={!mapping.included || activeTable.destination_exists} /></td>
                        <td className="p-3 text-xs"><span className={mapping.compatible ? "text-emerald-700" : "text-amber-700"}>{mapping.match_strategy.replaceAll("_", " ")}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {activeTable.destination_exists && <p className="mt-3 text-xs text-slate-500">The destination table already exists. Column types are read from destination discovery and cannot be changed in this plan.</p>}
            </section>
          )}

          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold">4. Validate and prepare destination schema</h2>
            <div className="mt-4 flex flex-wrap gap-3">
              <button disabled={busy} onClick={validate} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold hover:bg-slate-50">Validate plan</button>
              <button disabled={busy} onClick={preview} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold hover:bg-slate-50">Preview destination DDL</button>
              <button disabled={busy || !ddl?.statements?.length} onClick={applyDDL} className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">Apply DDL to destination</button>
            </div>
            {validation && (
              <div className="mt-4 rounded-lg border p-4">
                <p className={validation.valid ? "font-semibold text-emerald-700" : "font-semibold text-red-700"}>{validation.valid ? "Plan is valid" : "Plan needs changes"}</p>
                {validation.errors?.map((item: string) => <p key={item} className="mt-2 text-sm text-red-700">• {item}</p>)}
                {validation.warnings?.map((item: string) => <p key={item} className="mt-2 text-sm text-amber-700">• {item}</p>)}
              </div>
            )}
            {ddl && (
              <div className="mt-4 space-y-3">
                <div className="flex flex-wrap gap-4 text-sm text-slate-600"><span>{ddl.tables_to_create} tables to create</span><span>{ddl.schemas_to_create.length} schemas to create</span></div>
                {ddl.warnings?.map((item: string) => <p key={item} className="text-sm text-amber-700">• {item}</p>)}
                <pre className="max-h-96 overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-6 text-slate-100">{ddl.statements.join("\n\n") || "-- No destination DDL is required."}</pre>
              </div>
            )}
            <p className="mt-4 text-xs text-slate-500">Applying DDL creates missing schemas and tables only. It does not drop, truncate, or alter existing tables and does not transfer data.</p>
          </section>
        </>
      )}

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {notice && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</div>}
      {busy && <p className="text-sm text-slate-500">Working…</p>}
    </div>
  );
}
