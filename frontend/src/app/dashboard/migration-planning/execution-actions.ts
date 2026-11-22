"use server";

import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";

async function token() {
  const session = await auth0.getSession();
  if (!session) throw new Error("Your session has expired. Sign in again.");
  const result = await auth0.getAccessToken();
  if (!result.token) throw new Error("Auth0 did not return an API access token.");
  return result.token;
}

export async function startMigrationRun(projectId: string, planId: string, batchSize: number, writeStrategy: "INSERT_ONLY" | "UPSERT", writeEngine: "VALUES" | "COPY") {
  return apiRequest<any>(`/projects/${projectId}/migration-plans/${planId}/runs`, await token(), {
    method: "POST", body: JSON.stringify({ batch_size: batchSize, write_strategy: writeStrategy, write_engine: writeEngine }),
  });
}
export async function listMigrationRuns(projectId: string, planId: string) {
  return apiRequest<any[]>(`/projects/${projectId}/migration-plans/${planId}/runs`, await token(), { cache: "no-store" });
}
export async function getMigrationRun(projectId: string, planId: string, runId: string) {
  return apiRequest<any>(`/projects/${projectId}/migration-plans/${planId}/runs/${runId}`, await token(), { cache: "no-store" });
}
export async function getMigrationRunTables(projectId: string, planId: string, runId: string) {
  return apiRequest<any[]>(`/projects/${projectId}/migration-plans/${planId}/runs/${runId}/tables`, await token(), { cache: "no-store" });
}
export async function getMigrationRunErrors(projectId: string, planId: string, runId: string) {
  return apiRequest<any[]>(`/projects/${projectId}/migration-plans/${planId}/runs/${runId}/errors`, await token(), { cache: "no-store" });
}
export async function resumeMigrationRun(projectId: string, planId: string, runId: string) {
  return apiRequest<any>(`/projects/${projectId}/migration-plans/${planId}/runs/${runId}/resume`, await token(), { method: "POST" });
}
export async function cancelMigrationRun(projectId: string, planId: string, runId: string) {
  return apiRequest<any>(`/projects/${projectId}/migration-plans/${planId}/runs/${runId}/cancel`, await token(), { method: "POST" });
}

export async function getMigrationRunEvents(projectId: string, planId: string, runId: string) {
  return apiRequest<any[]>(`/projects/${projectId}/migration-plans/${planId}/runs/${runId}/events`, await token(), { cache: "no-store" });
}
export async function getMigrationRunReport(projectId: string, planId: string, runId: string) {
  return apiRequest<any>(`/projects/${projectId}/migration-plans/${planId}/runs/${runId}/report`, await token(), { cache: "no-store" });
}
export async function downloadMigrationRunCsv(projectId: string, planId: string, runId: string) {
  const accessToken = await token();
    const base = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");
  const response = await fetch(`${base}/projects/${projectId}/migration-plans/${planId}/runs/${runId}/report.csv`, {
    headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store",
  });
  if (!response.ok) throw new Error(`Could not download migration report (HTTP ${response.status}).`);
  return response.text();
}

export async function retryMigrationRunErrors(projectId: string, planId: string, runId: string) {
  const endpoint = "/projects/" + projectId + "/migration-plans/" + planId + "/runs/" + runId + "/retry-errors";
  return apiRequest<any>(endpoint, await token(), { method: "POST" });
}

export async function getMigrationPlanMetrics(projectId: string, planId: string) {
  return apiRequest<any>(
    `/projects/${projectId}/migration-plans/${planId}/metrics`,
    await token(),
    { cache: "no-store" },
  );
}


export async function getMigrationRunMetrics(projectId: string, planId: string, runId: string) {
  return apiRequest<any>(
    `/projects/${projectId}/migration-plans/${planId}/runs/${runId}/metrics`,
    await token(),
    { cache: "no-store" },
  );
}
