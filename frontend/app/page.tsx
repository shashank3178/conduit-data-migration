"use client";

import { useEffect, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
type Endpoint = { engine: string; host: string; port: number; database: string; username: string; password: string; tls: boolean };
type Table = { schema_name: string; table_name: string; estimated_rows: number | null; estimated_bytes: number | null; columns: { name: string; native_type: string; nullable: boolean }[]; keys: { name: string; columns: string[]; primary: boolean }[] };
type Inventory = { tables: Table[]; capabilities: { name: string; status: string; reason: string }[]; warnings: string[]; estimate: { estimated_rows: number; estimated_bytes: number; confidence: string; column_count: number; estimated_duration_seconds: number | null }; table_count: number };
type Job = { id: string; status: string; stage: string; completed_tables: number; total_tables: number; rows: number; bytes: number; results: { table: string; rows: number; bytes: number; status: string }[]; error?: string; note?: string };

const blank = (): Endpoint => ({ engine: "postgresql", host: "localhost", port: 5432, database: "", username: "", password: "", tls: false });
const fmt = (n: number | null | undefined) => n == null ? "—" : n.toLocaleString();
const bytes = (n: number | null | undefined) => {
  if (n == null) return "—";
  if (n < 1024) return n + " B";
  const units = ["KB", "MB", "GB", "TB"]; let v = n / 1024; let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return v.toFixed(1) + " " + units[i];
};

function EndpointForm({ title, value, onChange }: { title: string; value: Endpoint; onChange: (v: Endpoint) => void }) {
  const set = (key: keyof Endpoint, v: string | number | boolean) => onChange({ ...value, [key]: v });
  return <section className="panel endpoint">
    <div className="panel-heading"><div><span className="eyebrow">DATABASE CONNECTION</span><h3>{title}</h3></div><span className="db-mark">PG</span></div>
    <label>Database engine<select value={value.engine} onChange={e => set("engine", e.target.value)}><option value="postgresql">PostgreSQL</option><option value="mysql">MySQL</option><option value="oracle">Oracle</option></select></label>
    <div className="field-grid">
      <label>Host<input value={value.host} onChange={e => set("host", e.target.value)} placeholder="localhost" /></label>
      <label>Port<input type="number" value={value.port} onChange={e => set("port", Number(e.target.value))} /></label>
      <label>Database / service<input value={value.database} onChange={e => set("database", e.target.value)} placeholder="database_name" /></label>
      <label>Username<input value={value.username} onChange={e => set("username", e.target.value)} placeholder="db_user" /></label>
      <label className="wide">Password<input type="password" autoComplete="new-password" value={value.password} onChange={e => set("password", e.target.value)} placeholder="Password is sent only to the local API" /></label>
    </div>
    <label className="toggle"><input type="checkbox" checked={value.tls} onChange={e => set("tls", e.target.checked)} /> Require TLS</label>
  </section>;
}

export default function Home() {
  const [source, setSource] = useState<Endpoint>(blank());
  const [target, setTarget] = useState<Endpoint>({ ...blank(), host: "localhost", port: 5433 });
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [schemas, setSchemas] = useState("");

  const schemaList = useMemo(() => schemas.split(",").map(s => s.trim()).filter(Boolean), [schemas]);

  async function call(path: string, body?: unknown) {
    const response = await fetch(API + path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Request failed");
    return payload;
  }
  function connection(endpoint: Endpoint) {
    return { ...endpoint };
  }
  async function testSource() {
    setBusy(true); setMessage("");
    try {
      const result = await call("/api/connections/test", { connection: connection(source), schemas: schemaList.length ? schemaList : null });
      setMessage("Source connected · " + result.database + " · " + result.server_version);
    } catch (e) { setMessage((e as Error).message); }
    finally { setBusy(false); }
  }
  async function discover() {
    setBusy(true); setMessage("");
    try {
      const result = await call("/api/discovery", { connection: connection(source), schemas: schemaList.length ? schemaList : null });
      setInventory(result); setMessage("Discovery completed successfully.");
    } catch (e) { setMessage((e as Error).message); }
    finally { setBusy(false); }
  }
  async function start() {
    setBusy(true); setMessage(""); setJob(null);
    try {
      const result = await call("/api/migrations", { source, target, schemas: schemaList.length ? schemaList : null, block_bytes: 1048576 });
      setJob({ id: result.id, status: result.status, stage: "Queued", completed_tables: 0, total_tables: 0, rows: 0, bytes: 0, results: [] });
    } catch (e) { setMessage((e as Error).message); setBusy(false); }
  }
  useEffect(() => {
    if (!job || ["completed", "failed"].includes(job.status)) { if (job) setBusy(false); return; }
    const timer = setInterval(async () => {
      try { const next = await call("/api/migrations/" + job.id); setJob(next); }
      catch (e) { setMessage((e as Error).message); }
    }, 1200);
    return () => clearInterval(timer);
  }, [job]);

  const canRun = source.engine === "postgresql" && target.engine === "postgresql" && source.database && target.database && source.username && target.username && source.password && target.password;

  return <main className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-icon">S</div><div><strong>snowbridge</strong><span>DATA MIGRATION</span></div></div>
      <div className="nav-label">WORKSPACE</div>
      <a className="nav-item active"><span>◫</span> Overview</a>
      <a className="nav-item"><span>⌘</span> Connections</a>
      <a className="nav-item"><span>▤</span> Schema discovery</a>
      <a className="nav-item"><span>⇄</span> Migration runs</a>
      <a className="nav-item"><span>◷</span> Reconciliation</a>
      <div className="sidebar-bottom"><div className="status-dot" /> Local development environment<br /><small>API · {API}</small></div>
    </aside>
    <section className="main">
      <header className="topbar"><div><span className="crumb">Workspace /</span> Overview</div><div className="top-right"><span className="live-dot" /> SYSTEM ONLINE <span className="avatar">SB</span></div></header>
      <div className="content">
        <div className="hero"><div><div className="eyebrow">MIGRATION CONTROL PLANE</div><h1>Move data with <em>confidence.</em></h1><p>Discover database structure, understand migration scope, and run a consistent PostgreSQL snapshot transfer.</p></div><div className="hero-chip"><span className="live-dot" /> ENGINE STATUS <b>READY</b></div></div>
        <div className="metrics">
          <div className="metric"><span>DISCOVERED TABLES</span><strong>{inventory ? fmt(inventory.table_count) : "—"}</strong><small>Source catalog inventory</small></div>
          <div className="metric"><span>ESTIMATED ROWS</span><strong>{inventory ? fmt(inventory.estimate.estimated_rows) : "—"}</strong><small>Catalog estimate</small></div>
          <div className="metric"><span>ESTIMATED DATA</span><strong>{inventory ? bytes(inventory.estimate.estimated_bytes) : "—"}</strong><small>Before target overhead</small></div>
          <div className="metric"><span>MIGRATION STATUS</span><strong className="status-text">{job?.status?.toUpperCase() || "IDLE"}</strong><small>{job?.stage || "No active migration"}</small></div>
        </div>
        <div className="section-title"><div><span className="eyebrow">01 / CONFIGURE</span><h2>Connect your databases</h2></div><span className="muted">Credentials are not saved by this demo UI</span></div>
        <div className="connection-grid">
          <EndpointForm title="Source database" value={source} onChange={setSource} />
          <EndpointForm title="Target database" value={target} onChange={setTarget} />
        </div>
        <div className="schema-filter panel"><div><strong>Schema scope</strong><p>Optional comma-separated schemas. Leave empty to discover all accessible schemas.</p></div><input value={schemas} onChange={e => setSchemas(e.target.value)} placeholder="public, sales, analytics" /></div>
        <div className="actions">
          <button className="button secondary" disabled={busy} onClick={testSource}>Test source</button>
          <button className="button secondary" disabled={busy} onClick={discover}>Discover schema</button>
          <button className="button primary" disabled={busy || !canRun} onClick={start}>⇄ &nbsp; Run snapshot migration</button>
        </div>
        {message && <div className="notice">{message}</div>}
        {inventory && <>
          <div className="section-title"><div><span className="eyebrow">02 / DISCOVERY</span><h2>Schema inventory</h2></div><span className={"confidence " + inventory.estimate.confidence}>{inventory.estimate.confidence} confidence</span></div>
          <div className="panel table-panel"><div className="table-head"><div><strong>Discovered objects</strong><p>{inventory.table_count} base tables · {inventory.estimate.column_count} columns</p></div><span className="tag">POSTGRESQL</span></div>
            <div className="table-scroll"><table><thead><tr><th>TABLE</th><th>COLUMNS</th><th>EST. ROWS</th><th>EST. SIZE</th><th>KEYS</th></tr></thead><tbody>
              {inventory.tables.map(t => <tr key={t.schema_name + "." + t.table_name}><td><b>{t.schema_name}.{t.table_name}</b><small>{t.columns.slice(0, 4).map(c => c.name + " · " + c.native_type).join("  /  ")}</small></td><td>{t.columns.length}</td><td>{fmt(t.estimated_rows)}</td><td>{bytes(t.estimated_bytes)}</td><td>{t.keys.map(k => k.primary ? "PK" : "UK").join(", ") || "—"}</td></tr>)}
            </tbody></table></div>
          </div>
          <div className="capabilities">{inventory.capabilities.map(c => <div className="capability" key={c.name}><span className={c.status === "available" ? "check" : "warn"}>{c.status === "available" ? "✓" : "!"}</span><div><b>{c.name.replaceAll("_", " ")}</b><small>{c.reason}</small></div><span className="cap-status">{c.status.replaceAll("_", " ")}</span></div>)}</div>
          {inventory.warnings.length > 0 && <div className="notice warning"><b>Discovery notes</b>{inventory.warnings.map((w, i) => <p key={i}>{w}</p>)}</div>}
        </>}
        {job && <><div className="section-title"><div><span className="eyebrow">03 / EXECUTION</span><h2>Migration activity</h2></div><span className={"confidence " + (job.status === "completed" ? "high" : job.status === "failed" ? "low" : "medium")}>{job.status}</span></div>
          <div className="panel progress-panel"><div className="progress-title"><div><b>{job.stage}</b><p>{job.completed_tables} of {job.total_tables} tables committed</p></div><strong>{job.total_tables ? Math.round(job.completed_tables / job.total_tables * 100) : 0}%</strong></div><div className="progress"><span style={{ width: (job.total_tables ? job.completed_tables / job.total_tables * 100 : 0) + "%" }} /></div><div className="progress-stats"><span>{fmt(job.rows)} rows committed</span><span>{bytes(job.bytes)} transferred</span></div>
            {job.error && <div className="notice error">{job.error}</div>}
            {job.results.length > 0 && <div className="table-scroll"><table><thead><tr><th>TABLE</th><th>ROWS</th><th>TRANSFERRED</th><th>STATUS</th></tr></thead><tbody>{job.results.map(r => <tr key={r.table}><td>{r.table}</td><td>{fmt(r.rows)}</td><td>{bytes(r.bytes)}</td><td><span className="success-text">{r.status}</span></td></tr>)}</tbody></table></div>}
            {job.note && <p className="footnote">{job.note}</p>}
          </div>
        </>}
        <footer>SNOWBRIDGE V0.3 · SNAPSHOT PIPELINE · LOCAL DEMONSTRATION BUILD</footer>
      </div>
    </section>
  </main>;
}
