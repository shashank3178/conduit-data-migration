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
            Verify database connectivity, inspect schemas and tables, and review column metadata before building a migration plan.
          </p>
        </header>
        {loadError && <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{loadError}</div>}
        <DiscoveryClient projects={projects} connectionsByProject={connectionsByProject} initialProjectId={query.projectId} />
      </div>
    </AppShell>
  );
}
