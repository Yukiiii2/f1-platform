import { redirect } from "next/navigation";
import { PageHeading } from "../_components/ui";
import { accountState } from "../_lib/auth-api";
import { safeReturnTo } from "../_lib/auth";
import { single } from "../_lib/format";
import type { SearchPageProps } from "../_lib/contracts";
import { AuthForm } from "../auth/auth-form";
import "../auth/auth.css";
export const metadata = { title: "Sign in" };
export default async function SignInPage({ searchParams }: SearchPageProps) {
  const next = safeReturnTo(single((await searchParams).next));
  if ((await accountState()).user) redirect(next);
  return (
    <>
      <PageHeading title="Sign in." intro="Return to your saved comparisons." />
      <AuthForm mode="login" next={next} />
    </>
  );
}
