import Link from "next/link";
import { ApiError } from "../_lib/api";
import { authFetch } from "../_lib/auth-api";
import { authHref, type AccountProfile } from "../_lib/auth";
import { PageHeading, EmptyState } from "../_components/ui";
import { AccountSettings } from "./account-settings";
import type { SearchPageProps } from "../_lib/contracts";
import "./account.css";

export const metadata = { title: "Account" };
export default async function AccountPage({
  searchParams,
}: Partial<SearchPageProps> = {}) {
  const query = await searchParams;
  const year = Array.isArray(query?.season) ? query.season[0] : query?.season;
  const returnTo = `/account${year && /^\d{4}$/.test(year) ? `?season=${year}` : ""}`;
  let profile: AccountProfile;
  try {
    profile = (await (
      await authFetch("auth/account")
    ).json()) as AccountProfile;
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401)
      return (
        <EmptyState title="Sign in to manage your account">
          <p>Race data remains available without signing in.</p>
          <Link
            className="button"
            href={authHref("sign-in", returnTo)}
            prefetch={false}
          >
            Sign in
          </Link>
        </EmptyState>
      );
    return (
      <EmptyState title="Account settings temporarily unavailable">
        <p>Your account and saved comparisons have not been changed.</p>
        <a className="button button-quiet" href={returnTo}>
          Retry account settings
        </a>
      </EmptyState>
    );
  }
  return (
    <>
      <PageHeading
        title="Your account."
        intro="Manage your sign-in details and active sessions."
      />
      <AccountSettings profile={profile} returnTo={returnTo} key={profile.id} />
    </>
  );
}
