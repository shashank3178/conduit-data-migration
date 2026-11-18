import { redirect } from "next/navigation";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";
import MigrationPlanningClient from "./planning-client";

interface Project { id: string; name: string; }

export default async function MigrationPlanningPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/dashboard/migration-planning");
  let projects: Project[] = [], initialConnections: any[] = [], initialPlans: any[] = [], loadError: string | null = null;
  try {
    const { token } = await auth0.getAccessToken();
    if (!token) throw new Error("Auth0 did not return an API access token.");
    projects = await apiRequest<Project[]>("/projects", token, { cache: "no-store" });
    if (projects.length > 0) {
      const [connections, plans] = await Promise.all([
        apiRequest<any[]>(`/projects/${projects[0].id}/connections`, token, { cache: "no-store" }),
        apiRequest<any[]>(`/projects/${projects[0].id}/migration-plans`, token, { cache: "no-store" }),
      ]);
      initialConnections = connections; initialPlans = plans;
    }
  } catch (error) { loadError = error instanceof Error ? error.message : "Unable to load migration planning data."; }
  return (
    <main className="run-artwash min-h-screen bg-[#10100e] text-[#f2eadb]">
      <header className="border-b border-[#d9bd8a]/20 bg-[#15130f]/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <a href="/dashboard" className="flex items-center gap-3 font-serif text-xl tracking-[.16em]"><img src="/conduit-logo.png" alt="" className="h-8 w-8 object-contain" />CONDUIT</a>
          <nav className="flex items-center gap-5 text-sm text-[#d8c9ad]"><a href="/dashboard/runs" className="hover:text-[#e7c68d]">Live runs ↗</a><a href="/dashboard" className="hover:text-[#e7c68d]">Workspace</a></nav>
        </div>
      </header>
      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 border-b border-[#c8a66f]/20 pb-7">
          <p className="eyebrow">Migration workflow / Configure the transfer</p>
          <h1 className="display-title mt-3 font-serif text-6xl md:text-7xl">Plan with <em>intention.</em></h1>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-[#c7b99f]">Configure a migration, select source tables, map columns, and prepare the destination schema. Row transfer begins only when you explicitly queue execution.</p>
        </div>
        {loadError && <div className="mb-6 rounded border border-red-400/30 bg-red-950/50 p-4 text-sm text-red-200">{loadError}</div>}
        <div className="planning-workspace"><MigrationPlanningClient projects={projects} initialConnections={initialConnections} initialPlans={initialPlans}/></div>
      </div>
    </main>
  );
}
