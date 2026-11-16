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

export async function startMigrationRun(projectId: string, planId: string, batchSize: number) {
  return apiRequest<any>(`/projects/${projectId}/migration-plans/${planId}/runs`, await token(), {
    method: "POST", body: JSON.stringify({ batch_size: batchSize }),
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
export async function cancelMigrationRun(projectId: string, planId: string, runId: string) {
  return apiRequest<any>(`/projects/${projectId}/migration-plans/${planId}/runs/${runId}/cancel`, await token(), { method: "POST" });
}
