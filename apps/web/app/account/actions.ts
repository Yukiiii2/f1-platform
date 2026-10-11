"use server";
import { ApiError } from "../_lib/api";
import { accountError, type AuthResult } from "../_lib/auth";
import {
  authFetch,
  applySessionCookie,
  clearSessionCookie,
} from "../_lib/auth-api";

export async function updateAccount(
  kind: "username" | "password" | "sessions" | "delete",
  values: Record<string, string>,
): Promise<AuthResult> {
  try {
    if (kind === "username")
      await authFetch("auth/username", { username: values.username }, "PATCH");
    else if (kind === "password") {
      const response = await authFetch(
        "auth/password",
        {
          current_password: values.current_password,
          new_password: values.new_password,
        },
        "POST",
      );
      await applySessionCookie(response.headers);
    } else if (kind === "sessions")
      await authFetch("auth/sessions/revoke-others");
    else if (kind === "delete") {
      await authFetch(
        "auth/account",
        {
          current_password: values.current_password,
          confirmation: values.confirmation,
        },
        "DELETE",
      );
      await clearSessionCookie();
    } else return { error: accountError(422) };
    return { success: true };
  } catch (error) {
    return {
      error: accountError(error instanceof ApiError ? error.status : 503),
      ...(error instanceof ApiError && error.status === 401
        ? { signInRequired: true as const }
        : {}),
    };
  }
}
