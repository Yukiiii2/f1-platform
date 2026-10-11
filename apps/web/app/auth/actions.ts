"use server";
import { ApiError } from "../_lib/api";
import { authError, type AuthResult } from "../_lib/auth";
import {
  authFetch,
  applySessionCookie,
  clearSessionCookie,
} from "../_lib/auth-api";

export async function authenticate(
  mode: "login" | "register",
  username: string,
  password: string,
): Promise<AuthResult> {
  try {
    if (mode !== "login" && mode !== "register")
      return { error: authError(422) };
    const response = await authFetch(
      mode === "login" ? "auth/login" : "auth/register",
      { username, password },
    );
    await applySessionCookie(response.headers);
    return { success: true };
  } catch (error) {
    return { error: authError(error instanceof ApiError ? error.status : 503) };
  }
}
export async function signOut(): Promise<AuthResult> {
  try {
    await authFetch("auth/logout");
    await clearSessionCookie();
    return { success: true };
  } catch (error) {
    return { error: authError(error instanceof ApiError ? error.status : 503) };
  }
}
