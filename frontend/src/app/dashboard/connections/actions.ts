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
  let test: { success: boolean; message: string; server_version?: string | null };
  try {
    test = await apiRequest<{ success: boolean; message: string; server_version?: string | null }>(
      `/projects/${projectId}/connections/${connection.id}/test`, token,
      { method: "POST" },
    );
  } catch (error) {
    test = { success: false, message: error instanceof Error ? error.message : "Connection was saved, but the connectivity test failed." };
  }
  return { connection, test };
}


export async function updateConnection(projectId: string, connectionId: string, payload: Record<string, unknown>) {
  return apiRequest<any>(`/projects/${projectId}/connections/${connectionId}`, await getToken(), {
    method: "PATCH", body: JSON.stringify(payload),
  });
}

export async function deleteConnection(projectId: string, connectionId: string) {
  return apiRequest<void>(`/projects/${projectId}/connections/${connectionId}`, await getToken(), {
    method: "DELETE",
  });
}

export async function discoverConnection(projectId: string, connectionId: string) {
  return apiRequest<any>(`/projects/${projectId}/connections/${connectionId}/discover`, await getToken(), {
    method: "POST",
  });
}
