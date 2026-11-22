import { redirect } from "next/navigation";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import MigrationPlanningClient from "./planning-client";
import AppShell from "@/components/layout/app-shell";

interface Project {
  id: string;
  name: string;
}

export default async function MigrationPlanningPage() {
  const session = await auth0.getSession();
  if (!session) {
    redirect("/auth/login?returnTo=/dashboard/migration-planning");
  }

  let projects: Project[] = [];
  let initialConnections: any[] = [];
  let initialPlans: any[] = [];
  let loadError: string | null = null;

  try {
    const { token } = await auth0.getAccessToken();
    if (!token) {
      throw new Error("Auth0 did not return an API access token.");
    }
    projects = await apiRequest<Project[]>("/projects", token, { cache: "no-store" });
    if (projects.length > 0) {
      const [connections, plans] = await Promise.all([
        apiRequest<any[]>(`/projects/${projects[0].id}/connections`, token, { cache: "no-store" }),
        apiRequest<any[]>(`/projects/${projects[0].id}/migration-plans`, token, { cache: "no-store" }),
      ]);
      initialConnections = connections;
      initialPlans = plans;
    }
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Unable to load migration planning data.";
  }

  return (
    <AppShell userLabel={session.user.name ?? session.user.email}>
      <div className="conduit-enter space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="conduit-eyebrow">Migration workspace</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">Migration planning</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Select source and destination connections; plan creation automatically discovers both databases and measures table sizes.</p>
          </div>
          <div className="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-xs text-indigo-800"><span className="font-semibold">Workflow</span><span className="ml-2 text-indigo-600">Discover → Select by size → Map → Prepare → COPY</span></div>
        </div>
        {loadError && <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{loadError}</div>}
        <MigrationPlanningClient projects={projects} initialConnections={initialConnections} initialPlans={initialPlans} />
      </div>
    </AppShell>
  );
}
