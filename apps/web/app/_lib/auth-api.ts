import { cookies, headers } from "next/headers";
import { cache } from "react";
import { ApiError } from "./api";
import type { AccountState, AccountUser } from "./auth";

const cookieName = "f1_session";
const validToken = /^[A-Za-z0-9_-]{43}$/;
export async function sessionHeaders(): Promise<Record<string, string>> {
  const token = (await cookies()).get(cookieName)?.value;
  const origin = (await headers()).get("origin");
  return {
    "X-F1-Auth": "1",
    ...(token && validToken.test(token)
      ? { Cookie: `${cookieName}=${token}` }
      : {}),
    ...(origin ? { Origin: origin } : {}),
  };
}
export async function authFetch(
  path: "auth/login" | "auth/register" | "auth/logout" | "auth/me",
  body?: { username: string; password: string },
): Promise<Response> {
  try {
    const base = (
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    ).replace(/\/$/, "");
    const response = await fetch(`${base}/v1/${path}`, {
      method: path === "auth/me" ? "GET" : "POST",
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
      headers: {
        ...(await sessionHeaders()),
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) throw new ApiError(response.status);
    return response;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError();
  }
}
export async function applySessionCookie(
  responseHeaders: Headers,
): Promise<void> {
  const raw = responseHeaders.get("set-cookie") ?? "";
  const match = raw.match(/^f1_session=([A-Za-z0-9_-]{43});/);
  const age = raw.match(/(?:^|;)\s*Max-Age=(\d+)/i);
  if (
    !match ||
    !age ||
    !/(?:^|;)\s*HttpOnly(?:;|$)/i.test(raw) ||
    !/(?:^|;)\s*SameSite=lax(?:;|$)/i.test(raw) ||
    !/(?:^|;)\s*Path=\/(?:;|$)/i.test(raw) ||
    Number(age[1]) < 3600 ||
    Number(age[1]) > 604800
  )
    throw new ApiError();
  (await cookies()).set(cookieName, match[1], {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure: /(?:^|;)\s*Secure(?:;|$)/i.test(raw),
    maxAge: Number(age[1]),
  });
}
export async function clearSessionCookie(): Promise<void> {
  (await cookies()).delete(cookieName);
}
export const accountState = cache(async (): Promise<AccountState> => {
  const token = (await cookies()).get(cookieName)?.value;
  if (!token || !validToken.test(token)) return { user: null };
  try {
    const body = (await (await authFetch("auth/me")).json()) as AccountUser;
    return { user: { id: body.id, username: body.username } };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401)
      return { user: null };
    return { user: null, error: "Account access is temporarily unavailable." };
  }
});
