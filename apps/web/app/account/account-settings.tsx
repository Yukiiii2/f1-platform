"use client";
import { useId, useState, useTransition, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authHref, accountError, type AccountProfile } from "../_lib/auth";
import { updateAccount } from "./actions";

function timestamp(value: string) {
  return `${new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value))} UTC`;
}
type Setting = "username" | "password" | "sessions" | "delete";
const successMessages: Record<Setting, string> = {
  username: "Sign-in name updated.",
  password: "Password changed. Other sessions have been signed out.",
  sessions: "Other sessions have been signed out.",
  delete: "Account deleted.",
};

export function AccountSettings({
  profile,
  returnTo = "/account",
}: {
  profile: AccountProfile;
  returnTo?: string;
}) {
  const id = useId();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{
    kind: Setting;
    message: string;
    error?: boolean;
    signInRequired?: boolean;
  } | null>(null);
  function submit(kind: Setting, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    if (
      kind === "password" &&
      data.get("new_password") !== data.get("confirm_password")
    ) {
      setResult({ kind, message: "New passwords must match.", error: true });
      return;
    }
    if (kind === "delete" && data.get("confirmation") !== "DELETE") {
      setResult({
        kind,
        message: "Type DELETE to confirm permanent account deletion.",
        error: true,
      });
      return;
    }
    const values: Record<string, string> = {};
    for (const name of [
      "username",
      "current_password",
      "new_password",
      "confirmation",
    ]) {
      const value = data.get(name);
      if (typeof value === "string") values[name] = value;
    }
    setResult(null);
    startTransition(async () => {
      try {
        const response = await updateAccount(kind, values);
        if (response.success) {
          form.reset();
          setResult({ kind, message: successMessages[kind] });
          if (kind === "delete")
            router.replace(returnTo.replace(/^\/account/, "/"));
          router.refresh();
        } else
          setResult({
            kind,
            message: response.error ?? accountError(503),
            error: true,
            signInRequired: response.signInRequired,
          });
      } catch {
        setResult({ kind, message: accountError(503), error: true });
      }
    });
  }
  const status = (kind: Setting) => (
    <div role="status" aria-live="polite">
      {result?.kind === kind && (
        <p>
          {result.message}
          {result.signInRequired && (
            <>
              {" "}
              <Link href={authHref("sign-in", returnTo)} prefetch={false}>
                Sign in again
              </Link>
            </>
          )}
        </p>
      )}
    </div>
  );
  return (
    <div className="account-settings">
      <dl className="account-summary">
        <div>
          <dt>Sign-in name</dt>
          <dd>{profile.username}</dd>
        </div>
        <div>
          <dt>Account created</dt>
          <dd>
            <time dateTime={profile.created_at}>
              {timestamp(profile.created_at)}
            </time>
          </dd>
        </div>
        <div>
          <dt>Saved comparisons</dt>
          <dd>
            {profile.saved_comparison_count} ·{" "}
            <Link href="/comparisons" prefetch={false}>
              Open Saved Comparisons
            </Link>
          </dd>
        </div>
      </dl>
      <section
        className="account-section"
        aria-labelledby={`${id}-name-heading`}
      >
        <h2 id={`${id}-name-heading`}>Change sign-in name</h2>
        <p className="section-note">
          3–32 letters, numbers, dots, underscores or hyphens. Your current
          session stays signed in.
        </p>
        <form
          className="account-form"
          data-setting="username"
          onSubmit={(event) => submit("username", event)}
        >
          <div className="field">
            <label htmlFor={`${id}-name`}>Sign-in name</label>
            <input
              id={`${id}-name`}
              name="username"
              defaultValue={profile.username}
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              pattern="[a-zA-Z0-9][a-zA-Z0-9_.-]{2,31}"
              minLength={3}
              maxLength={32}
              required
              disabled={pending}
            />
          </div>
          <button
            className="button button-quiet"
            type="submit"
            disabled={pending}
          >
            {pending ? "Saving…" : "Save sign-in name"}
          </button>
          {status("username")}
        </form>
      </section>
      <section
        className="account-section"
        aria-labelledby={`${id}-password-heading`}
      >
        <h2 id={`${id}-password-heading`}>Change password</h2>
        <p className="section-note">
          Choose a unique password with at least 12 characters. All other
          sessions will be signed out.
        </p>
        <form
          className="account-form"
          data-setting="password"
          onSubmit={(event) => submit("password", event)}
        >
          <div className="field">
            <label htmlFor={`${id}-current`}>Current password</label>
            <input
              id={`${id}-current`}
              name="current_password"
              type="password"
              autoComplete="current-password"
              maxLength={128}
              required
              disabled={pending}
            />
          </div>
          <div className="field">
            <label htmlFor={`${id}-new`}>New password</label>
            <input
              id={`${id}-new`}
              name="new_password"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              required
              disabled={pending}
            />
          </div>
          <div className="field">
            <label htmlFor={`${id}-confirm`}>Confirm new password</label>
            <input
              id={`${id}-confirm`}
              name="confirm_password"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              required
              disabled={pending}
            />
          </div>
          <button
            className="button button-quiet"
            type="submit"
            disabled={pending}
          >
            {pending ? "Saving…" : "Change password"}
          </button>
          {status("password")}
        </form>
      </section>
      <section
        className="account-section"
        aria-labelledby={`${id}-sessions-heading`}
      >
        <h2 id={`${id}-sessions-heading`}>Active sessions</h2>
        <p className="section-note">
          Times are shown in UTC. Expired sessions are excluded.
        </p>
        <ul className="account-session-list">
          {profile.sessions.map((session, index) => (
            <li key={`${session.created_at}-${index}`}>
              <strong>
                {session.is_current ? "Current session" : "Other session"}
              </strong>
              <span>
                Created{" "}
                <time dateTime={session.created_at}>
                  {timestamp(session.created_at)}
                </time>
                <br />
                Expires{" "}
                <time dateTime={session.expires_at}>
                  {timestamp(session.expires_at)}
                </time>
              </span>
            </li>
          ))}
        </ul>
        <form
          className="account-form"
          data-setting="sessions"
          onSubmit={(event) => submit("sessions", event)}
        >
          <button
            className="button button-quiet"
            type="submit"
            disabled={
              pending ||
              !profile.sessions.some((session) => !session.is_current)
            }
          >
            {pending ? "Signing out…" : "Sign out other sessions"}
          </button>
          {status("sessions")}
        </form>
      </section>
      <section
        className="account-section"
        aria-labelledby={`${id}-delete-heading`}
      >
        <h2 id={`${id}-delete-heading`}>Delete account</h2>
        <p>
          This permanently removes your account, its sessions and{" "}
          {profile.saved_comparison_count} saved comparisons. Public race and
          telemetry data is preserved.
        </p>
        <details>
          <summary>Review permanent account deletion</summary>
          <form
            className="account-form"
            data-setting="delete"
            onSubmit={(event) => submit("delete", event)}
          >
            <div className="field">
              <label htmlFor={`${id}-delete-password`}>Current password</label>
              <input
                id={`${id}-delete-password`}
                name="current_password"
                type="password"
                autoComplete="current-password"
                maxLength={128}
                required
                disabled={pending}
              />
            </div>
            <div className="field">
              <label htmlFor={`${id}-delete-confirm`}>
                Type DELETE to confirm
              </label>
              <input
                id={`${id}-delete-confirm`}
                name="confirmation"
                autoComplete="off"
                spellCheck={false}
                pattern="DELETE"
                maxLength={6}
                required
                disabled={pending}
              />
            </div>
            <button
              className="button button-quiet"
              type="submit"
              disabled={pending}
            >
              {pending ? "Deleting…" : "Permanently delete account"}
            </button>
            {status("delete")}
          </form>
        </details>
      </section>
    </div>
  );
}
