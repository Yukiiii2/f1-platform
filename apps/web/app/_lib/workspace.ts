export type ReferenceType = "comparison" | "event" | "driver" | "session";
export type ReferenceInput = {
  reference_type: ReferenceType;
  reference_id: string;
  season: number;
};
export type WorkspaceReference = ReferenceInput & {
  id: string;
  created_at: string;
  updated_at: string;
  label: string;
  availability: "available" | "partial" | "unavailable";
  notices: string[];
  open_url: string | null;
};
export type Collection = {
  id: string;
  title: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  item_count: number;
};
export type CollectionDetail = Collection & { items: WorkspaceReference[] };
export type WorkspaceResult = {
  success?: true;
  response?: Collection | WorkspaceReference;
  error?: string;
  signInRequired?: true;
};
export const referenceLabels: Record<ReferenceType, string> = {
  comparison: "Saved comparison",
  event: "Race weekend",
  driver: "Driver",
  session: "Session",
};
export function workspaceError(status = 503) {
  if (status === 401)
    return "Your session has expired. Sign in again to save or organize material.";
  if (status === 404)
    return "This private record is no longer available. Reload your workspace.";
  if (status === 422 || status === 413)
    return "Check the title, description and recorded reference. Reload if the source data has changed.";
  if (status === 429)
    return "Too many requests. Wait a moment, then try again.";
  return "Your workspace is temporarily unavailable. Reload to check whether your change was saved before trying again.";
}
export function workspaceDate(value: string) {
  return `${new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value))} UTC`;
}
export function workspaceRoute(path: string, context: string) {
  const year = new URL(context, "http://localhost").searchParams.get("season");
  return `${path}${year && /^\d{4}$/.test(year) ? `?season=${year}` : ""}`;
}
