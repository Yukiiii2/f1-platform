"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <div className="error-state" role="alert">
      <h1>Race data could not be loaded.</h1>
      <p>
        The data service may be temporarily unreachable. Try again in a moment.
      </p>
      <div className="actions">
        <button
          className="button"
          disabled={pending}
          onClick={() =>
            startTransition(() => {
              router.refresh();
              reset();
            })
          }
        >
          {pending ? "Retrying…" : "Try again"}
        </button>
        <Link href="/" prefetch={false}>
          Return home
        </Link>
      </div>
    </div>
  );
}
