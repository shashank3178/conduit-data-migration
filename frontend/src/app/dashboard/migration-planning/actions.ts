"use server";

import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";

async function accessToken() {
  const session = await auth0.getSession();
  if (!session) {
    throw new Error("Your session has expired. Sign in again.");
  }
  const { token } = await auth0.getAccessToken();
  if (!token) {
    throw new Error("Auth0 did not return an API access token.");
  }
  return token;
}

export async function loadProjectPlanningData(projectId: string) {
  const token = await accessToken();
  const [connections, plans] = await Promise.all([
    apiRequest<any[]>(`/projects/${projectId}/connections`, token, { cache: "no-store" }),
    apiRequest<any[]>(`/projects/${projectId}/migration-plans`, token, { cache: "no-store" }),
  ]);
  return { connections, plans };
}

export async function createMigrationPlan(projectId: string, payload: Record<string, unknown>) {
  const token = await accessToken();
  return apiRequest<any>(`/projects/${projectId}/migration-plans`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loadPlanTables(projectId: string, planId: string) {
  const token = await accessToken();
  return apiRequest<any[]>(
    `/projects/${projectId}/migration-plans/${planId}/tables`,
    token,
    { cache: "no-store" },
  );
}

export async function saveTableSelection(
  projectId: string,
  planId: string,
  tables: Array<Record<string, unknown>>,
) {
  const token = await accessToken();
  return apiRequest<any[]>(
    `/projects/${projectId}/migration-plans/${planId}/tables/selection`,
    token,
    { method: "PUT", body: JSON.stringify({ tables }) },
  );
}

export async function regenerateMappingSuggestions(projectId: string, planId: string) {
  const token = await accessToken();
  return apiRequest<any[]>(
    `/projects/${projectId}/migration-plans/${planId}/mappings/suggest`,
    token,
    { method: "POST" },
  );
}

export async function saveColumnMappings(
  projectId: string,
  planId: string,
  tableId: string,
  mappings: Array<Record<string, unknown>>,
) {
  const token = await accessToken();
  return apiRequest<any[]>(
    `/projects/${projectId}/migration-plans/${planId}/tables/${tableId}/mappings`,
    token,
    { method: "PUT", body: JSON.stringify({ mappings }) },
  );
}

export async function validateMigrationPlan(projectId: string, planId: string) {
  const token = await accessToken();
  return apiRequest<any>(
    `/projects/${projectId}/migration-plans/${planId}/validate`,
    token,
    { method: "POST" },
  );
}

export async function previewDestinationDDL(projectId: string, planId: string) {
  const token = await accessToken();
  return apiRequest<any>(
    `/projects/${projectId}/migration-plans/${planId}/ddl`,
    token,
    { cache: "no-store" },
  );
}

export async function applyDestinationDDL(projectId: string, planId: string) {
  const token = await accessToken();
  return apiRequest<any>(
    `/projects/${projectId}/migration-plans/${planId}/ddl/apply`,
    token,
    { method: "POST" },
  );
}
