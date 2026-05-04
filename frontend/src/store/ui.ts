/**
 * Zustand store — client-only UI state.
 *
 * Server-derived data (conversations, traces, eval runs) lives in React Query
 * (see src/api/queries.ts). This store holds *only* ephemeral UI choices that
 * do not belong on the backend: which Customer Experience modality is active,
 * which trace the Operator Console has selected, and which event cards are
 * expanded inside the Trace Drill-Down.
 *
 * Persistence rule (CLAUDE.md §5): no localStorage / sessionStorage. State
 * lives in memory; the backend is the source of truth for anything durable.
 */
import { create } from "zustand";
import type { ChannelFilter, CxModality } from "@/api/types";

interface UiState {
  // Customer Experience
  modality: CxModality;
  selectedCustomerId: string | null; // null = anonymous
  setModality: (m: CxModality) => void;
  setSelectedCustomer: (id: string | null) => void;

  // Operator Console — page-level voice/chat/all filter.
  // Defaults to "voice" — the role this demo is targeted at owns voice agents.
  ocChannelFilter: ChannelFilter;
  setOcChannelFilter: (f: ChannelFilter) => void;

  // Operator Console — Trace Drill-Down
  selectedTraceId: string | null;
  expandedEventKeys: Set<string>;
  selectTrace: (traceId: string | null) => void;
  toggleEventExpanded: (key: string) => void;
  expandAllEvents: (keys: string[]) => void;
  collapseAllEvents: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  // Voice is the default for the Customer Experience surface. "Voice" is
  // realtime Gemini Live (WebSocket); push-to-talk has been removed.
  // Chat remains for fallback, debugging, and eval parity.
  modality: "voice",
  selectedCustomerId: null,
  setModality: (modality) => set({ modality }),
  setSelectedCustomer: (selectedCustomerId) => set({ selectedCustomerId }),

  ocChannelFilter: "voice",
  setOcChannelFilter: (ocChannelFilter) => set({ ocChannelFilter }),

  selectedTraceId: null,
  expandedEventKeys: new Set<string>(),
  selectTrace: (selectedTraceId) =>
    set({ selectedTraceId, expandedEventKeys: new Set<string>() }),
  toggleEventExpanded: (key) =>
    set((state) => {
      const next = new Set(state.expandedEventKeys);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return { expandedEventKeys: next };
    }),
  expandAllEvents: (keys) => set({ expandedEventKeys: new Set(keys) }),
  collapseAllEvents: () => set({ expandedEventKeys: new Set() }),
}));
