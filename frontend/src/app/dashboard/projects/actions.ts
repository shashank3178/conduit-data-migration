"use server";

import { auth0 } from "@/lib/auth0";
import { apiRequest } from "@/lib/api";

export async function createProjectAction(payload: { name: string; description: string }) {
  const session = await auth0.getSession();
  if (!session) throw new Error("Your session has expired. Sign in again.");
  const { token } = await auth0.getAccessToken();
  if (!token) throw new Error("Auth0 did not return an API access token.");
  return apiRequest<{ id: string; name: string }>("/projects", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
