import Link from "next/link";
import { auth0 } from "@/lib/auth0";

export default async function HomePage() {
  const session = await auth0.getSession();

  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center">
      <div className="max-w-2xl w-full text-center px-6">
        <h1 className="text-5xl font-bold text-slate-900">
          Conduit
        </h1>

        <p className="mt-4 text-lg text-slate-600">
          Enterprise Data Migration Platform
        </p>

        <p className="mt-3 text-slate-500">
          Securely migrate data between databases.
        </p>

        <div className="mt-8 flex justify-center gap-4">
          {session ? (
            <>
              <Link
                href="/dashboard"
                className="rounded-lg bg-blue-600 px-6 py-3 text-white hover:bg-blue-700"
              >
                Open Dashboard
              </Link>

              <a
                href="/auth/logout"
                className="rounded-lg border border-slate-300 px-6 py-3 text-slate-700 hover:bg-slate-100"
              >
                Logout
              </a>
            </>
          ) : (
            <a
              href="/auth/login?returnTo=/dashboard"
              className="rounded-lg bg-blue-600 px-6 py-3 text-white hover:bg-blue-700"
            >
              Login with Auth0
            </a>
          )}
        </div>
      </div>
    </main>
  );
}