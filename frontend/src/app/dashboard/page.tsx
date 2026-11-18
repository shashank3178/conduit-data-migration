import { redirect } from "next/navigation";
import Link from "next/link";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";

interface BackendUser { id: string; auth0_sub: string; email: string | null; created_at: string; }
interface Project { id: string; name: string; status: string; }

export default async function DashboardPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login?returnTo=/dashboard");
  let backendStatus = "Not connected", backendUser: BackendUser | null = null, projectCount = 0, apiError: string | null = null;
  try {
    const { token } = await auth0.getAccessToken();
    if (!token) throw new Error("Auth0 did not return an API access token.");
    const [me, projects] = await Promise.all([
      apiRequest<BackendUser>("/users/me", token, { cache: "no-store" }),
      apiRequest<Project[]>("/projects", token, { cache: "no-store" }),
    ]);
    backendUser = me; projectCount = projects.length; backendStatus = "Connected";
  } catch (error) { backendStatus = "Connection failed"; apiError = error instanceof Error ? error.message : "Unknown API error"; }
  const user = session.user;
  return (
    <main className="run-artwash min-h-screen text-[#f2eadb]">
      <header className="border-b border-[#d9bd8a]/20 bg-[#15130f]/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-3 font-serif text-2xl tracking-[.16em]"><img src="/conduit-logo.png" alt="" className="h-9 w-9 object-contain"/>CONDUIT</Link>
          <div className="flex items-center gap-5"><span className="hidden text-sm text-[#d8c9ad] sm:inline">{user.name ?? user.email}</span><Link href="/dashboard/runs" className="text-sm text-[#d7b77f]">Live runs ↗</Link><a href="/auth/logout" className="rounded-full border border-[#c8a66f]/35 px-4 py-2 text-sm text-[#d8c9ad] hover:bg-[#c8a66f]/10">Logout</a></div>
        </div>
      </header>
      <div className="mx-auto max-w-7xl px-6 py-12">
        <p className="eyebrow">Your migration atelier / Workspace</p>
        <h1 className="display-title mt-4 font-serif text-6xl leading-none md:text-8xl">Make data <em>move.</em></h1>
        <p className="mt-5 max-w-2xl text-[#c7b99f]">Welcome back, {user.name ?? user.email}. Your migration workspace is ready.</p>
        <div className="mt-8 flex flex-wrap gap-3"><Link href="/dashboard/migration-planning" className="bg-[#c8a66f] px-6 py-3 text-sm font-bold uppercase tracking-wider text-[#211b13] hover:bg-[#dec18f]">Open migration planning ↗</Link><Link href="/dashboard/runs" className="border border-[#c8a66f]/45 px-6 py-3 text-sm font-semibold text-[#ead8b9] hover:bg-[#c8a66f]/10">Monitor all runs</Link></div>
        <div className="mt-12 grid gap-4 md:grid-cols-3">
          <section className="metric-tile"><span>Authentication</span><strong className="!text-3xl">Verified</strong><p className="text-sm text-[#b9aa90]">Auth0 session established</p></section>
          <section className="metric-tile"><span>Backend API</span><strong className="!text-3xl">{backendStatus}</strong><p className="text-sm text-[#b9aa90]">Authenticated FastAPI connection</p>{apiError && <p className="break-words text-xs text-red-300">{apiError}</p>}</section>
          <section className="metric-tile"><span>Migration projects</span><strong>{projectCount.toLocaleString()}</strong><p className="text-sm text-[#b9aa90]">Projects in your account</p></section>
        </div>
        <section className="panel-dark mt-6 p-7"><p className="eyebrow">Account / Identity</p><h2 className="mt-2 font-serif text-3xl">Workspace profile</h2>{backendUser ? <dl className="mt-6 grid gap-5 text-sm sm:grid-cols-2"><div><dt className="text-[#aa9b81]">User ID</dt><dd className="mt-1 break-all">{backendUser.id}</dd></div><div><dt className="text-[#aa9b81]">Email</dt><dd className="mt-1">{backendUser.email ?? "Not provided by Auth0"}</dd></div><div><dt className="text-[#aa9b81]">Auth0 subject</dt><dd className="mt-1 break-all">{backendUser.auth0_sub}</dd></div><div><dt className="text-[#aa9b81]">Account created</dt><dd className="mt-1">{new Date(backendUser.created_at).toLocaleString()}</dd></div></dl> : <p className="mt-4 text-sm text-[#b9aa90]">Backend profile unavailable until the API connection succeeds.</p>}</section>
      </div>
    </main>
  );
}
