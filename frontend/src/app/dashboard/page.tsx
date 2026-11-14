import { redirect } from "next/navigation";
import Link from "next/link";
import { auth0 } from "@/lib/auth0";

interface BackendUser {
  sub?: string;
  email?: string;
  name?: string;
}

export default async function DashboardPage() {
  const session = await auth0.getSession();

  if (!session) {
    redirect("/auth/login?returnTo=/dashboard");
  }

  const { token } = await auth0.getAccessToken();

  let backendStatus = "Not connected";
  let backendUser: BackendUser | null = null;

  try {
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/users/me`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
        },
        cache: "no-store",
      }
    );

    if (response.ok) {
      backendUser = await response.json();
      backendStatus = "Connected";
    } else {
      backendStatus = `API returned ${response.status}`;
    }
  } catch {
    backendStatus = "Backend unavailable";
  }

  const user = session.user;

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <Link href="/" className="text-xl font-bold text-slate-900">
            Conduit
          </Link>

          <div className="flex items-center gap-4">
            <span className="text-sm text-slate-600">
              {user.name ?? user.email}
            </span>

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
        <h1 className="text-3xl font-bold text-slate-900">
          Dashboard
        </h1>

        <p className="mt-2 text-slate-600">
          Welcome back, {user.name ?? user.email}.
        </p>

        <div className="mt-8 grid gap-6 md:grid-cols-3">
          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <h2 className="font-semibold text-slate-900">
              Authentication
            </h2>
            <p className="mt-3 text-green-600">Authenticated</p>
            <p className="mt-2 text-sm text-slate-500">
              Login handled by Auth0.
            </p>
          </section>

          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <h2 className="font-semibold text-slate-900">
              Backend API
            </h2>
            <p
              className={`mt-3 ${
                backendStatus === "Connected"
                  ? "text-green-600"
                  : "text-red-600"
              }`}
            >
              {backendStatus}
            </p>
            <p className="mt-2 text-sm text-slate-500">
              FastAPI connectivity and authentication.
            </p>
          </section>

          <section className="rounded-xl border bg-white p-6 shadow-sm">
            <h2 className="font-semibold text-slate-900">
              Migration Projects
            </h2>
            <p className="mt-3 text-3xl font-bold text-slate-900">
              0
            </p>
            <p className="mt-2 text-sm text-slate-500">
              Migration projects will appear here.
            </p>
          </section>
        </div>

        <section className="mt-8 rounded-xl border bg-white p-6 shadow-sm">
          <h2 className="font-semibold text-slate-900">
            Authenticated User
          </h2>

          <pre className="mt-4 overflow-x-auto rounded-lg bg-slate-100 p-4 text-sm">
            {JSON.stringify(
              {
                auth0User: user,
                backendUser,
              },
              null,
              2
            )}
          </pre>
        </section>
      </div>
    </main>
  );
}