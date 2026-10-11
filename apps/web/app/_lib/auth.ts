export type AccountUser = { id: string; username: string };
export type AccountState = { user: AccountUser | null; error?: string };
export type AuthResult = { success?: true; error?: string };

export function safeReturnTo(value?: string): string {
  if (!value || value.length > 4096 || /[\\\u0000-\u001f\u007f]/.test(value))
    return "/comparisons";
  if (
    !/^\/(?:[?#]|$|(?:telemetry|strategy|pitwall|comparisons|races|drivers|standings)(?:\/[a-zA-Z0-9-]+)*(?:[?#]|$))/.test(
      value,
    )
  )
    return "/comparisons";
  return value;
}
export function authHref(
  page: "sign-in" | "create-account",
  next: string,
): string {
  return `/${page}?${new URLSearchParams({ next: safeReturnTo(next) })}`;
}
export function authError(status: number): string {
  if (status === 401) return "The sign-in name or password is incorrect.";
  if (status === 409)
    return "An account could not be created with those details. Choose another sign-in name or sign in.";
  if (status === 429)
    return "Too many account requests. Wait a moment, then try again.";
  if (status === 422 || status === 413)
    return "Check your sign-in name and password requirements.";
  return "Account access is temporarily unavailable. Please try again.";
}
