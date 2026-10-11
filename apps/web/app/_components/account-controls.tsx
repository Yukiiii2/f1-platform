"use client";
import Link from "next/link";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { signOut } from "../auth/actions";
import { authHref, authError, type AccountState } from "../_lib/auth";
export function AccountControls({ user, error }: AccountState) {
  const path = usePathname();
  const query = useSearchParams();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [failure, setFailure] = useState<string | null>(null);
  return (
    <div className="account-controls" aria-label="Account">
      {user ? (
        <>
          <Link
            href={`/workspace${/^\d{4}$/.test(query.get("season") ?? "") ? `?season=${query.get("season")}` : ""}`}
            prefetch={false}
          >
            Workspace
          </Link>
          <Link
            href={`/account${/^\d{4}$/.test(query.get("season") ?? "") ? `?season=${query.get("season")}` : ""}`}
            prefetch={false}
          >
            Account · {user.username}
          </Link>
          <button
            type="button"
            disabled={pending}
            onClick={() =>
              startTransition(async () => {
                try {
                  const result = await signOut();
                  if (result.success) {
                    setFailure(null);
                    router.refresh();
                  } else setFailure(result.error ?? authError(503));
                } catch {
                  setFailure(authError(503));
                }
              })
            }
          >
            {pending ? "Signing out…" : "Sign out"}
          </button>
        </>
      ) : error ? (
        <span>{error}</span>
      ) : (
        <Link
          href={authHref("sign-in", `${path}${query.size ? `?${query}` : ""}`)}
          prefetch={false}
        >
          Sign in
        </Link>
      )}
      {failure && <p role="status">{failure}</p>}
    </div>
  );
}
