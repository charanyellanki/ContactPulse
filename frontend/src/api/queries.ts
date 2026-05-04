import { useQuery } from "@tanstack/react-query";
import {
  getBatchEvalPreview,
  listCustomers,
  listConversations,
  listErrorClusters,
  listEvalRuns,
  getTrace,
} from "./client";
import type { SampleModality } from "./types";

export const queryKeys = {
  customers: ["customers"] as const,
  conversations: ["conversations"] as const,
  trace: (traceId: string) => ["trace", traceId] as const,
  evalRuns: ["eval-runs"] as const,
  errorClusters: ["error-clusters"] as const,
  batchPreview: (modality: SampleModality) => ["batch-preview", modality] as const,
};

export function useCustomers() {
  return useQuery({ queryKey: queryKeys.customers, queryFn: listCustomers });
}

export function useConversations() {
  return useQuery({ queryKey: queryKeys.conversations, queryFn: listConversations });
}

export function useTrace(traceId: string | null) {
  return useQuery({
    queryKey: traceId ? queryKeys.trace(traceId) : ["trace", "none"],
    queryFn: () => getTrace(traceId as string),
    enabled: !!traceId,
  });
}

export function useEvalRuns() {
  return useQuery({ queryKey: queryKeys.evalRuns, queryFn: listEvalRuns });
}

export function useErrorClusters() {
  return useQuery({ queryKey: queryKeys.errorClusters, queryFn: listErrorClusters });
}

export function useBatchEvalPreview(modality: SampleModality) {
  return useQuery({
    queryKey: queryKeys.batchPreview(modality),
    queryFn: () => getBatchEvalPreview(modality),
    refetchInterval: 10_000, // refresh the "N new" hint every 10s
  });
}
