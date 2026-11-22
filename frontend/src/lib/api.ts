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
    let message = response.status === 401 ? "Your session has expired. Sign in again."
      : response.status === 403 ? "You do not have permission to perform this action."
      : response.status === 404 ? "The requested resource could not be found."
      : response.status === 409 ? "The operation conflicts with the current resource state."
      : response.status === 422 ? "Some submitted values are invalid. Review the form and try again."
      : response.status >= 500 ? "The service encountered an error. Please retry; if it continues, inspect the backend logs."
      : `The request failed (HTTP ${response.status}).`;

    if (responseBody) {
      try {
        const payload = JSON.parse(responseBody) as {
          detail?: string | { message?: string };
          message?: string;
        };
        const detail = (payload as { detail?: unknown }).detail;
        const candidate = typeof detail === "string" ? detail
          : detail && typeof detail === "object" && "message" in detail ? String((detail as { message?: unknown }).message ?? "")
          : Array.isArray(detail) ? detail.map((item) => (item as { msg?: string }).msg ?? "Invalid request.").join(" · ")
          : typeof payload.message === "string" ? payload.message : "";
        if (candidate && candidate.length <= 300 && !/traceback|stack trace|file \"|internal server error|exception:/i.test(candidate)) {
          message = candidate;
        }
      } catch {
        // Never surface raw proxy, framework, HTML, or JSON error bodies in the UI.
      }
    }

    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
