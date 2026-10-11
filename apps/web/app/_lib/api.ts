export class ApiError extends Error {
  status: number;
  constructor(status = 503) {
    super("Race data is temporarily unreachable");
    this.status = status;
  }
}
async function request<T>(
  path: string,
  query: Record<string, string | number> = {},
  body?: unknown,
  timeout = 8000,
  method: "GET" | "POST" | "PATCH" | "DELETE" = body === undefined
    ? "GET"
    : "POST",
  requestHeaders: Record<string, string> = {},
): Promise<T> {
  try {
    const base = (
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    ).replace(/\/$/, "");
    const url = new URL(`${base}/v1/${path}`);
    Object.entries(query).forEach(([key, value]) =>
      url.searchParams.set(key, String(value)),
    );
    const response = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeout),
      method,
      headers: {
        ...requestHeaders,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined
        ? {}
        : {
            body: JSON.stringify(body),
          }),
    });
    if (!response.ok) throw new ApiError(response.status);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError();
  }
}
export function getComparisonPage<T>(
  query: Record<string, string | number> = {},
  headers: Record<string, string> = {},
): Promise<T[]> {
  return request<T[]>(
    "comparisons",
    { ...query, limit: 50 },
    undefined,
    8000,
    "GET",
    headers,
  );
}
export function getSavedComparison<T>(
  id: string,
  headers: Record<string, string> = {},
): Promise<T> {
  comparisonId(id);
  return request<T>(`comparisons/${id}`, {}, undefined, 8000, "GET", headers);
}
function comparisonId(id: string) {
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
  )
    throw new ApiError(404);
}
export function changeSavedComparison<T>(
  id: string,
  method: "PATCH" | "DELETE",
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<T> {
  comparisonId(id);
  return request<T>(`comparisons/${id}`, {}, body, 8000, method, headers);
}
export function postEntity<T>(
  path: string,
  body: unknown,
  timeout?: number,
  headers: Record<string, string> = {},
): Promise<T> {
  return request<T>(path, {}, body, timeout, "POST", headers);
}
export function workspaceRequest<T>(
  path: string,
  method: "GET" | "POST" | "PATCH" | "DELETE" = "GET",
  body?: unknown,
  query: Record<string, string | number> = {},
  headers: Record<string, string> = {},
): Promise<T> {
  const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  if (
    !new RegExp(
      `^(?:collections(?:/${uuid}(?:/items(?:/${uuid})?)?)?|favorites(?:/${uuid})?)$`,
      "i",
    ).test(path)
  )
    throw new ApiError(404);
  return request<T>(path, query, body, 8000, method, headers);
}
export function getSessionStrategy<T>(sessionId: string): Promise<T> {
  return request<T>(`sessions/${sessionId}/strategy`);
}
export function getSessionReplay<T>(sessionId: string): Promise<T> {
  return request<T>(`sessions/${sessionId}/replay`);
}
export async function getList<T extends { id: string }>(
  path: string,
  query: Record<string, string | number> = {},
): Promise<T[]> {
  const rows: T[] = [];
  const seen = new Set<string>();
  while (true) {
    const page = await request<T[]>(path, {
      ...query,
      limit: 200,
      offset: rows.length,
    });
    if (!Array.isArray(page) || page.length > 200) throw new ApiError();
    for (const row of page) {
      if (!row || typeof row.id !== "string" || seen.has(row.id))
        throw new ApiError();
      seen.add(row.id);
      rows.push(row);
    }
    if (page.length < 200) return rows;
  }
}
export async function getEntity<T>(
  resource: "events" | "circuits" | "drivers" | "teams" | "sessions",
  id: string,
): Promise<T> {
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
  )
    throw new ApiError(404);
  return request<T>(`${resource}/${id}`);
}
