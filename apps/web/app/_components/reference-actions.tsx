import Link from "next/link";
import { accountState, sessionHeaders } from "../_lib/auth-api";
import { authHref } from "../_lib/auth";
import { ApiError, workspaceRequest } from "../_lib/api";
import type { ReferenceInput, WorkspaceReference } from "../_lib/workspace";
import { ReferenceControls } from "./reference-controls";

export async function ReferenceActions({
  reference,
  returnTo,
}: {
  reference: ReferenceInput;
  returnTo: string;
}) {
  const account = await accountState();
  if (account.error)
    return (
      <p className="section-note">
        Private saving is temporarily unavailable. Public race data remains
        available.
      </p>
    );
  if (!account.user)
    return (
      <p className="section-note">
        <Link href={authHref("sign-in", returnTo)} prefetch={false}>
          Sign in to save this{" "}
          {reference.reference_type === "event"
            ? "weekend"
            : reference.reference_type}{" "}
          to your workspace
        </Link>
      </p>
    );
  let favorite: WorkspaceReference | undefined;
  let unavailable = false;
  if (
    reference.reference_type === "driver" ||
    reference.reference_type === "event"
  ) {
    try {
      favorite = (
        await workspaceRequest<WorkspaceReference[]>(
          "favorites",
          "GET",
          undefined,
          {
            reference_type: reference.reference_type,
            reference_id: reference.reference_id,
            limit: 1,
          },
          await sessionHeaders(),
        )
      )[0];
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      if (error.status === 401)
        return (
          <p className="section-note">
            <Link href={authHref("sign-in", returnTo)} prefetch={false}>
              Sign in again to save this reference
            </Link>
          </p>
        );
      unavailable = true;
    }
  }
  return (
    <ReferenceControls
      key={`${reference.reference_id}:${favorite?.id ?? "none"}`}
      reference={reference}
      returnTo={returnTo}
      initialFavorite={favorite}
      favoriteUnavailable={unavailable}
    />
  );
}
