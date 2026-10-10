import type { ComparisonRequest } from "./telemetry-contracts";

// Mirrors the existing Phase 8 application contract, not a model-provider API.
export interface PageContext {
  route?: string;
  event_id?: string;
  session_id?: string;
  driver_id?: string;
  lap_id?: string;
  stint_id?: string;
  season?: number;
  comparison?: ComparisonRequest;
  allow_approximate?: boolean;
}
export interface QueryRequest {
  question: string;
  context: PageContext;
}
export type Json =
  null | string | number | boolean | Json[] | { [key: string]: Json };
export interface Evidence {
  id: string;
  tool: string;
  arguments: Record<string, Json>;
  status: "available" | "unavailable";
  data: Record<string, Json>;
  data_status?: "not_tracked" | "provisional" | "finalized";
  truncated: boolean;
  next_offset: number | null;
  error: string | null;
}
export interface GroundedValue {
  evidence_id: string;
  pointer: string;
  value: Json;
  classification: "source" | "derived" | "estimate";
}
export interface Interpretation {
  kind: "observed_pace" | "pit_timing" | "tyre_context" | "lap_comparison";
  evidence_ids: string[];
  text: string;
  classification: "interpretation";
  uncertainty: "not_confirmed_team_intent";
}
export interface QueryResponse {
  status: "answered" | "unavailable";
  facts: GroundedValue[];
  calculations: GroundedValue[];
  estimates: GroundedValue[];
  interpretations: Interpretation[];
  unavailable: string[];
  evidence: Evidence[];
  policy_version: "pitwall-tool-first-v1";
}
export type QueryResult =
  | { response: QueryResponse; error?: never }
  | { error: string; response?: never };
