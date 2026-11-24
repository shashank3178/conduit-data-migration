import { redirect } from "next/navigation";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import AppShell from "@/components/layout/app-shell";
import DiscoveryClient from "./discovery-client";

type Project = { id: string; name: string };
type Connection = {
  id: string; name: string; role: "source" | "destination";
  database: string; host: string; port: number;
};

export default async function DiscoveryPage({ searchParams }: { searchParams: Promise<{ projectId?: string }> }) {
  const query = await searchParams;
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/dashboard/discovery");

  let projects: Project[] = [];
  let connectionsByProject: Record<string, Connection[]> = {};
  let loadError = "";
  try {
    const { token } = await auth0.getAccessToken();
    if (!token) throw new Error("Auth0 did not return an API access token.");
    projects = await apiRequest<Project[]>("/projects", token, { cache: "no-store" });
    const rows = await Promise.all(projects.map(async (project) => ({
      projectId: project.id,
      connections: await apiRequest<Connection[]>(
        `/projects/${project.id}/connections`, token, { cache: "no-store" },
      ),
    })));
    connectionsByProject = Object.fromEntries(rows.map((row) => [row.projectId, row.connections]));
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Unable to load database connections.";
  }

  return (
    <AppShell userLabel={session.user.name ?? session.user.email}>
      <div className="conduit-enter space-y-7">
        <header>
          <p className="conduit-eyebrow">Database intelligence</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">Discovery</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
            Build a metadata snapshot of your PostgreSQL database before planning a migration. Discovery inspects accessible schemas,
            tables, views, columns, keys, constraints, indexes, and database capabilities so Conduit can assess compatibility,
            dependencies, and migration scope.
          </p>
          <div className="mt-4 max-w-3xl rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm font-semibold text-slate-800">What a discovery snapshot contains</p>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              A point-in-time record of database structure and metadata used by the migration planner. Re-run discovery after
              schema changes to refresh the snapshot and keep the plan aligned with the source database.
            </p>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              Discovery is not a database backup and does not copy application table data. Data consistency is established
              separately during migration and validation.
            </p>
          </div>
        </header>
        {loadError && <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{loadError}</div>}
        <DiscoveryClient projects={projects} connectionsByProject={connectionsByProject} initialProjectId={query.projectId} />
      </div>
    </AppShell>
  );
}
