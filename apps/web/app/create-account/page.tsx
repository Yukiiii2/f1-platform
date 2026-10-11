import { redirect } from "next/navigation";
import { PageHeading } from "../_components/ui";
import { accountState } from "../_lib/auth-api";
import { safeReturnTo } from "../_lib/auth";
import { single } from "../_lib/format";
import type { SearchPageProps } from "../_lib/contracts";
import { AuthForm } from "../auth/auth-form";
import "../auth/auth.css";
export const metadata = { title: "Create account" };
export default async function CreateAccountPage({
  searchParams,
}: SearchPageProps) {
  const next = safeReturnTo(single((await searchParams).next));
  if ((await accountState()).user) redirect(next);
  return (
    <>
      <PageHeading
        title="Create account."
        intro="Keep useful lap and strategy selections together."
      />
      <AuthForm mode="register" next={next} />
    </>
  );
}
