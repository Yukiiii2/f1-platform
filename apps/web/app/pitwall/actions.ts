"use server";

import { ApiError, postEntity } from "../_lib/api";
import type {
  QueryRequest,
  QueryResponse,
  QueryResult,
} from "../_lib/pitwall-contracts";
import { pitwallError, queryRequest } from "../_lib/pitwall";

export async function askPitwall(request: QueryRequest): Promise<QueryResult> {
  let payload: QueryRequest;
  try {
    payload = queryRequest(request.question, request.context);
  } catch {
    return { error: pitwallError(422) };
  }
  try {
    // Keep browser traffic same-origin and allow the backend's bounded retrieval/retry budget.
    const response = await postEntity<QueryResponse>(
      "ai/query",
      payload,
      90000,
    );
    return { response };
  } catch (error) {
    return {
      error: pitwallError(error instanceof ApiError ? error.status : 503),
    };
  }
}
