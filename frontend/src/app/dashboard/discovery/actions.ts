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

export type DiscoverySnapshot = {
  snapshot_id: string;
  connection_id: string;
  status: "pending" | "running" | "completed" | "failed";
  database_name: string;
  server_version: string | null;
  schema_count: number;
  table_count: number;
  discovered_at: string | null;
  message: string;
  error_message?: string | null;
};
export type DiscoveredSchema = { id: string; name: string; is_system: boolean; table_count: number };
export type DiscoveredTable = {
  id: string; schema_name: string; name: string; table_type: string; estimated_rows: number | null;
};
export type DiscoveredTableDetail = DiscoveredTable & {
  columns: { name: string; type?: string; nullable?: boolean; default?: string | null; [key: string]: unknown }[];
  primary_key: { constrained_columns?: string[]; name?: string | null };
  foreign_keys: unknown[];
  unique_constraints: unknown[];
  check_constraints: unknown[];
  indexes: unknown[];
  comment: string | null;
};

function base(projectId: string, connectionId: string) {
  return `/projects/${projectId}/connections/${connectionId}`;
}

export async function verifyConnectionAction(projectId: string, connectionId: string) {
  const token = await getToken();
  return apiRequest<{ success: boolean; message: string; server_version?: string | null }>(
    `/projects/${projectId}/connections/${connectionId}/test`, token, { method: "POST" },
  );
}

export async function runDiscoveryAction(projectId: string, connectionId: string) {
  const token = await getToken();
  const root = base(projectId, connectionId);
  const snapshot = await apiRequest<DiscoverySnapshot>(`${root}/discover`, token, { method: "POST" });
  const [schemas, tables] = await Promise.all([
    apiRequest<DiscoveredSchema[]>(`${root}/schemas`, token, { cache: "no-store" }),
    apiRequest<DiscoveredTable[]>(`${root}/tables`, token, { cache: "no-store" }),
  ]);
  return { snapshot, schemas, tables };
}

export async function loadDiscoveryAction(projectId: string, connectionId: string) {
  const token = await getToken();
  const root = base(projectId, connectionId);
  const [snapshot, schemas, tables] = await Promise.all([
    apiRequest<DiscoverySnapshot>(`${root}/discovery`, token, { cache: "no-store" }),
    apiRequest<DiscoveredSchema[]>(`${root}/schemas`, token, { cache: "no-store" }),
    apiRequest<DiscoveredTable[]>(`${root}/tables`, token, { cache: "no-store" }),
  ]);
  return { snapshot, schemas, tables };
}

export async function loadDiscoveredTableDetailAction(projectId: string, connectionId: string, tableId: string) {
  const token = await getToken();
  return apiRequest<DiscoveredTableDetail>(
    `${base(projectId, connectionId)}/tables/${tableId}`, token, { cache: "no-store" },
  );
}
