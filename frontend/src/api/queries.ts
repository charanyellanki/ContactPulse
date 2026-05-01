import { useQuery } from "@tanstack/react-query";
import {
  listCustomers,
  listConversations,
  listErrorClusters,
  listEvalRuns,
  getTrace,
} from "./client";

export const queryKeys = {
  customers: ["customers"] as const,
  conversations: ["conversations"] as const,
  trace: (traceId: string) => ["trace", traceId] as const,
  evalRuns: ["eval-runs"] as const,
  errorClusters: ["error-clusters"] as const,
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
