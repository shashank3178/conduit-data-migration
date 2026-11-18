import { redirect } from "next/navigation";
import Link from "next/link";
import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";

interface BackendUser {
  id: string;
  auth0_sub: string;
  email: string | null;
  created_at: string;
}

interface Project {
  id: string;
  name: string;
  status: string;
}

export default async function DashboardPage() {
  const session = await auth0.getSession();

  if (!session) {
    redirect("/auth/login?returnTo=/dashboard");
  }

  let backendStatus = "Not connected";
  let backendUser: BackendUser | null = null;
  let projectCount = 0;
  let apiError: string | null = null;

  try {
    const { token } = await auth0.getAccessToken();

    if (!token) {
      throw new Error("Auth0 did not return an API access token.");
    }

    const [me, projects] = await Promise.all([
      apiRequest<BackendUser>("/users/me", token, { cache: "no-store" }),
      apiRequest<Project[]>("/projects", token, { cache: "no-store" }),
    ]);

    backendUser = me;
    projectCount = projects.length;
    backendStatus = "Connected";
  } catch (error) {
    backendStatus = "Connection failed";
    apiError =
      error instanceof Error ? error.message : "Unknown API error";
  }

  const user = session.user;

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-3 text-xl font-bold text-slate-900"><img src="/conduit-logo.png" alt="" className="h-8 w-8 object-contain" /> CONDUIT</Link>

          <div className="flex items-center gap-4">
            <span className="text-sm text-slate-600">
              {user.name ?? user.email}
            </span>
            <Link href="/dashboard/runs" className="text-sm font-semibold text-amber-800">Live runs</Link>
            <a
              href="/auth/logout"
              className="rounded-lg border px-4 py-2 text-sm hover:bg-slate-100"
            >
              Logout
            </a>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-10">
        <h1 className="text-3xl font-bold text-slate-900">Dashboard</h1>
        <p className="mt-2 text-slate-600">
          Welcome back, {user.name ?? user.email}.
        </p>

        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            href="/dashboard/migration-planning"
            className="inline-flex items-center rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800"
          >
            Open migration planning
          </Link>
          <Link href="/dashboard/runs" className="inline-flex items-center rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-800 hover:bg-slate-100">Monitor live runs</Link>
        </div>

        <div className="mt-8 grid gap-6 md:grid-cols-3">
          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <h2 className="font-semibold text-slate-900">Authentication</h2>
            <p className="mt-3 text-green-600">Authenticated</p>
            <p className="mt-2 text-sm text-slate-500">
              Auth0 session established.
            </p>
          </section>

          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <h2 className="font-semibold text-slate-900">Backend API</h2>
            <p
              className={`mt-3 ${
                backendStatus === "Connected" ? "text-green-600" : "text-red-600"
              }`}
            >
              {backendStatus}
            </p>
            <p className="mt-2 text-sm text-slate-500">
              Authenticated FastAPI requests to the current-user and projects
              endpoints.
            </p>
            {apiError && (
              <p className="mt-3 break-words text-xs text-red-600">{apiError}</p>
            )}
          </section>

          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <h2 className="font-semibold text-slate-900">Migration Projects</h2>
            <p className="mt-3 text-3xl font-bold text-slate-900">
              {projectCount}
            </p>
            <p className="mt-2 text-sm text-slate-500">
              Projects owned by your authenticated account.
            </p>
          </section>
        </div>

        <section className="mt-8 rounded-xl border bg-white p-6 shadow-sm">
          <h2 className="font-semibold text-slate-900">Backend User Profile</h2>
          {backendUser ? (
            <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-slate-500">User ID</dt>
                <dd className="mt-1 break-all font-medium text-slate-900">
                  {backendUser.id}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Email</dt>
                <dd className="mt-1 font-medium text-slate-900">
                  {backendUser.email ?? "Not provided by Auth0"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Auth0 subject</dt>
                <dd className="mt-1 break-all font-medium text-slate-900">
                  {backendUser.auth0_sub}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Account created</dt>
                <dd className="mt-1 font-medium text-slate-900">
                  {new Date(backendUser.created_at).toLocaleString()}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="mt-3 text-sm text-slate-500">
              The backend profile is unavailable until the API connection
              succeeds.
            </p>
          )}
        </section>
      </div>
    </main>
  );
}
