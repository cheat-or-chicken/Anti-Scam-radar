export const BACKEND_URL = "http://127.0.0.1:8765";
export async function backendRequest(path, body, token) {
  const response = await fetch(BACKEND_URL + path, {
    method: body ? "POST" : "GET",
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: "Bearer " + token } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    credentials: "omit",
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(140000),
  });
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? "PAIRING_REQUIRED"
        : response.status === 429
          ? "RATE_LIMITED"
          : response.status === 422 ? "BACKEND_INCOMPATIBLE" : "BACKEND_UNAVAILABLE",
    );
  return response.json();
}
