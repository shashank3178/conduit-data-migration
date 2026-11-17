"use server";

import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";

async function getToken() {
  const session = await auth0.getSession();
  if (!session) throw new Error("Your session has expired. Sign in again.");
  const { token } = await auth0.getAccessToken();
  if (!token) throw new Error("Auth0 did not return an API access token.");
  return token;
}

export async function createAndTestConnection(projectId: string, payload: {
  name: string; role: "source" | "destination"; host: string; port: number;
  database: string; username: string; password: string;
  sslmode: "disable" | "allow" | "prefer" | "require" | "verify-ca" | "verify-full";
}) {
  const token = await getToken();
  const connection = await apiRequest<{ id: string; name: string }>(
    `/projects/${projectId}/connections`, token,
    { method: "POST", body: JSON.stringify(payload) },
  );
  const test = await apiRequest<{ success: boolean; message: string; server_version?: string | null }>(
    `/projects/${projectId}/connections/${connection.id}/test`, token,
    { method: "POST" },
  );
  return { connection, test };
}
