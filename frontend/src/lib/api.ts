const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"
).replace(/\/+$/, "");

export async function apiRequest<T>(
  endpoint: string,
  token: string,
  options: RequestInit = {}
): Promise<T> {
  const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  const headers = new Headers(options.headers);

  headers.set("Authorization", `Bearer ${token}`);

  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const responseBody = await response.text();
    let message = `Request failed (${response.status}).`;

    if (responseBody) {
      try {
        const payload = JSON.parse(responseBody) as {
          detail?: string | { message?: string };
          message?: string;
        };
        if (typeof payload.detail === "string") {
          message = payload.detail;
        } else if (payload.detail && typeof payload.detail.message === "string") {
          message = payload.detail.message;
        } else if (typeof payload.message === "string") {
          message = payload.message;
        } else {
          message = responseBody;
        }
      } catch {
        message = responseBody;
      }
    }

    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
