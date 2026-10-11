"use server";
import { ApiError, workspaceRequest } from "../_lib/api";
import { sessionHeaders } from "../_lib/auth-api";
import {
  workspaceError,
  type Collection,
  type ReferenceInput,
  type WorkspaceResult,
} from "../_lib/workspace";

type Action =
  "create" | "update" | "delete" | "add" | "remove" | "favorite" | "unfavorite";
export async function mutateWorkspace(
  action: Action,
  values: {
    id?: string;
    item_id?: string;
    title?: string;
    description?: string;
    reference?: ReferenceInput;
  },
): Promise<WorkspaceResult> {
  try {
    let path: string, method: "POST" | "PATCH" | "DELETE", body: unknown;
    if (action === "create" || action === "update") {
      path = action === "create" ? "collections" : `collections/${values.id}`;
      method = action === "create" ? "POST" : "PATCH";
      body = { title: values.title, description: values.description };
    } else if (action === "add") {
      path = `collections/${values.id}/items`;
      method = "POST";
      body = values.reference;
    } else if (action === "remove") {
      path = `collections/${values.id}/items/${values.item_id}`;
      method = "DELETE";
    } else if (action === "delete") {
      path = `collections/${values.id}`;
      method = "DELETE";
    } else if (action === "favorite") {
      path = "favorites";
      method = "POST";
      body = values.reference;
    } else if (action === "unfavorite") {
      path = `favorites/${values.id}`;
      method = "DELETE";
    } else return { error: workspaceError(422) };
    const response = await workspaceRequest<WorkspaceResult["response"]>(
      path,
      method,
      body,
      {},
      await sessionHeaders(),
    );
    return { success: true, ...(response ? { response } : {}) };
  } catch (error) {
    return {
      error: workspaceError(error instanceof ApiError ? error.status : 503),
      ...(error instanceof ApiError && error.status === 401
        ? { signInRequired: true as const }
        : {}),
    };
  }
}

export async function collectionOptions(
  offset = 0,
): Promise<{ rows?: Collection[]; error?: string; signInRequired?: true }> {
  try {
    if (!Number.isInteger(offset) || offset < 0 || offset > 1000000)
      return { error: workspaceError(422) };
    return {
      rows: await workspaceRequest<Collection[]>(
        "collections",
        "GET",
        undefined,
        { limit: 50, offset },
        await sessionHeaders(),
      ),
    };
  } catch (error) {
    return {
      error: workspaceError(error instanceof ApiError ? error.status : 503),
      ...(error instanceof ApiError && error.status === 401
        ? { signInRequired: true as const }
        : {}),
    };
  }
}
