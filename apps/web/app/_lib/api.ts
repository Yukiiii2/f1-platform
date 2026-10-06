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
      ...(body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }),
    });
    if (!response.ok) throw new ApiError(response.status);
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError();
  }
}
export function postEntity<T>(
  path: string,
  body: unknown,
  timeout?: number,
): Promise<T> {
  return request<T>(path, {}, body, timeout);
}
export function getSessionStrategy<T>(sessionId: string): Promise<T> {
  return request<T>(`sessions/${sessionId}/strategy`);
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
