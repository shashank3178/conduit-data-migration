import { redirect } from "next/navigation";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import MigrationPlanningClient from "./planning-client";

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
    <main className="run-artwash min-h-screen bg-[#10100e] text-[#f2eadb]">
      <header className="border-b border-[#d9bd8a]/20 bg-[#15130f]/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <a href="/dashboard" className="flex items-center gap-3 text-xl font-bold"><img src="/conduit-logo.png" alt="" className="h-8 w-8 object-contain" />CONDUIT</a>
          <nav className="flex items-center gap-5 text-sm text-[#d8c9ad]"><a href="/dashboard/runs" className="hover:text-slate-900">Live runs</a><a href="/dashboard" className="hover:text-slate-900">Dashboard</a></nav>
        </div>
      </header>
      <div className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-8">
          <p className="eyebrow">Migration workflow / Configure the transfer</p>
          <h1 className="display-title mt-2 font-serif text-5xl font-bold md:text-6xl">Migration planning</h1>
          <p className="mt-2 max-w-3xl text-slate-600">
            Configure a migration, select source tables, map columns, and prepare the destination schema.
            No application rows are transferred in this phase.
          </p>
        </div>
        {loadError && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{loadError}</div>
        )}
        <MigrationPlanningClient
          projects={projects}
          initialConnections={initialConnections}
          initialPlans={initialPlans}
        />
      </div>
    </main>
  );
}
