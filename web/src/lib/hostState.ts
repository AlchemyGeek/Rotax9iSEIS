// Shared by the browser client and the app's gate (Spec 04 v0.7 §9.4).

// A flag outside OPFS, set when a registry is first created on this device:
// "the data is gone" vs "a first run".
export const EVICTION_MARKER = "slingology-eis-registry-created";
// The outcome of the one durable-storage request (Spec 02 §9).
export const PERSIST_OUTCOME = "slingology-eis-persist";

export type EngineStatus =
  | { phase: "loading"; step: string; done: number; total: number }
  | { phase: "ready"; engineVersion: string; pyodideVersion: string; registryPresent: boolean }
  | { phase: "failed"; message: string };

export interface StatusSource {
  onStatus(fn: (s: EngineStatus) => void): () => void;
}
