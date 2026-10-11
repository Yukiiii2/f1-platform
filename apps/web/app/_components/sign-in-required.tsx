import Link from "next/link";
import { authHref } from "../_lib/auth";
import { EmptyState } from "./ui";
export function SignInRequired({ next }: { next: string }) {
  return (
    <EmptyState title="Sign in to use Saved Comparisons">
      <p>
        Race data and analysis remain public. Your selections will be restored
        after sign-in.
      </p>
      <div className="saved-comparison-actions">
        <Link
          className="button"
          href={authHref("sign-in", next)}
          prefetch={false}
        >
          Sign in
        </Link>
        <Link
          className="button button-quiet"
          href={authHref("create-account", next)}
          prefetch={false}
        >
          Create account
        </Link>
      </div>
    </EmptyState>
  );
}
