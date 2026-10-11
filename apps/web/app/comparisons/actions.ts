"use server";

import { ApiError, changeSavedComparison, postEntity } from "../_lib/api";
import { comparisonError } from "../_lib/saved-comparisons";
import { sessionHeaders } from "../_lib/auth-api";
import type {
  Preset,
  SavedComparison,
  SaveResult,
} from "../_lib/saved-comparison-contracts";

export async function saveComparison(
  request: Preset & { title: string },
): Promise<SaveResult> {
  try {
    const response = await postEntity<SavedComparison>(
      "comparisons",
      request,
      undefined,
      await sessionHeaders(),
    );
    return { response };
  } catch (error) {
    return {
      error: comparisonError(error instanceof ApiError ? error.status : 503),
      ...(error instanceof ApiError && error.status === 401
        ? { signInRequired: true as const }
        : {}),
    };
  }
}
export async function renameComparison(
  id: string,
  title: string,
): Promise<SaveResult> {
  try {
    const response = await changeSavedComparison<SavedComparison>(
      id,
      "PATCH",
      {
        title,
      },
      await sessionHeaders(),
    );
    return { response };
  } catch (error) {
    return {
      error: comparisonError(error instanceof ApiError ? error.status : 503),
    };
  }
}
export async function deleteComparison(
  id: string,
): Promise<{ success?: true; error?: string }> {
  try {
    await changeSavedComparison(
      id,
      "DELETE",
      undefined,
      await sessionHeaders(),
    );
    return { success: true };
  } catch (error) {
    return {
      error: comparisonError(error instanceof ApiError ? error.status : 503),
    };
  }
}
