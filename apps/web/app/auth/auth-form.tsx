"use client";
import { useId, useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authenticate } from "./actions";
import { authHref, authError } from "../_lib/auth";

export function AuthForm({
  mode,
  next,
}: {
  mode: "login" | "register";
  next: string;
}) {
  const id = useId();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const register = mode === "register";
  return (
    <div className="account-form-wrap">
      <form
        className="account-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (pending) return;
          const form = event.currentTarget;
          const values = new FormData(form);
          const password = String(values.get("password") ?? "");
          if (register && password !== values.get("confirm")) {
            setError("Passwords must match.");
            return;
          }
          setError(null);
          startTransition(async () => {
            try {
              const result = await authenticate(
                mode,
                String(values.get("username") ?? ""),
                password,
              );
              if (result.success) {
                form.reset();
                router.replace(next);
                router.refresh();
              } else setError(result.error ?? authError(503));
            } catch {
              setError(authError(503));
            }
          });
        }}
      >
        <div className="field">
          <label htmlFor={`${id}-name`}>Sign-in name</label>
          <input
            id={`${id}-name`}
            name="username"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            pattern="[a-zA-Z0-9][a-zA-Z0-9_.-]{2,31}"
            minLength={3}
            maxLength={32}
            required
            disabled={pending}
            aria-describedby={`${id}-name-help`}
          />
          <p id={`${id}-name-help`} className="section-note">
            3–32 letters, numbers, dots, underscores or hyphens.
          </p>
        </div>
        <div className="field">
          <label htmlFor={`${id}-password`}>Password</label>
          <input
            id={`${id}-password`}
            type="password"
            name="password"
            autoComplete={register ? "new-password" : "current-password"}
            minLength={register ? 12 : undefined}
            maxLength={128}
            required
            disabled={pending}
            aria-describedby={register ? `${id}-password-help` : undefined}
          />
          {register && (
            <p id={`${id}-password-help`} className="section-note">
              Use a unique password with at least 12 characters.
            </p>
          )}
        </div>
        {register && (
          <div className="field">
            <label htmlFor={`${id}-confirm`}>Confirm password</label>
            <input
              id={`${id}-confirm`}
              type="password"
              name="confirm"
              autoComplete="new-password"
              required
              disabled={pending}
            />
          </div>
        )}
        <p role="status" aria-live="polite">
          {error}
        </p>
        <button className="button" type="submit" disabled={pending}>
          {pending ? "Please wait…" : register ? "Create account" : "Sign in"}
        </button>
      </form>
      <p className="section-note">
        {register ? "Already have an account?" : "New here?"}{" "}
        <Link
          href={authHref(register ? "sign-in" : "create-account", next)}
          prefetch={false}
        >
          {register ? "Sign in" : "Create account"}
        </Link>
      </p>
      <p className="section-note">
        Race data remains public. An account keeps your saved comparisons
        private.
      </p>
    </div>
  );
}
