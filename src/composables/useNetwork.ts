import { computed, onMounted, onUnmounted, ref, type ComputedRef, type Ref } from "vue";
import { invoke } from "@tauri-apps/api/core";

export type NetworkStatus = "connected" | "disconnected" | "reconnecting" | "unknown";

export interface NetworkSnapshot {
  connected: boolean;
  status: NetworkStatus;
  account: string;
  operator: string;
  ipv4: string;
  ipv6: string;
  checkedAt: string;
}

interface NetworkState {
  busy: ComputedRef<boolean>;
  connecting: ComputedRef<boolean>;
  error: Ref<string>;
  snapshot: Ref<NetworkSnapshot>;
  cancelConnection: () => Promise<void>;
  setConnection: (connected: boolean) => Promise<void>;
}

const SNAPSHOT_REFRESH_INTERVAL = 2_000;

function initialSnapshot(): NetworkSnapshot {
  return {
    connected: false,
    status: "unknown",
    account: "—",
    operator: "—",
    ipv4: "—",
    ipv6: "—",
    checkedAt: "检测中…",
  };
}

function errorMessage(error: unknown): string {
  return typeof error === "string" ? error : "操作失败，请稍后重试";
}

export function useNetwork(): NetworkState {
  const connectionTarget = ref<boolean | null>(null);
  const cancellationRequested = ref(false);
  const busy = computed(function isConnectionBusy(): boolean {
    return connectionTarget.value !== null;
  });
  const connecting = computed(function isConnecting(): boolean {
    return connectionTarget.value === true;
  });
  const error = ref("");
  const snapshot = ref(initialSnapshot());
  let refreshTimer: number | undefined;

  function scheduleSnapshotRefresh(): void {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(refreshSnapshot, SNAPSHOT_REFRESH_INTERVAL);
  }

  async function refreshSnapshot(): Promise<void> {
    if (busy.value) {
      scheduleSnapshotRefresh();
      return;
    }
    try {
      snapshot.value = await invoke<NetworkSnapshot>("get_network_snapshot");
      error.value = "";
    } catch (caught) {
      error.value = errorMessage(caught);
      snapshot.value.checkedAt = new Date().toLocaleTimeString("zh-CN", {
        hour12: false,
      });
    } finally {
      scheduleSnapshotRefresh();
    }
  }

  async function setConnection(connected: boolean): Promise<void> {
    if (busy.value || snapshot.value.connected === connected) {
      return;
    }
    connectionTarget.value = connected;
    cancellationRequested.value = false;
    error.value = "";
    try {
      snapshot.value = await invoke<NetworkSnapshot>("set_connection", { connected });
    } catch (caught) {
      if (!cancellationRequested.value) {
        error.value = errorMessage(caught);
      }
    } finally {
      connectionTarget.value = null;
      cancellationRequested.value = false;
      scheduleSnapshotRefresh();
    }
  }

  async function cancelConnection(): Promise<void> {
    if (!connecting.value || cancellationRequested.value) {
      return;
    }
    cancellationRequested.value = true;
    try {
      await invoke("cancel_connection");
    } catch (caught) {
      cancellationRequested.value = false;
      error.value = errorMessage(caught);
    }
  }

  onMounted(async function initializeNetwork(): Promise<void> {
    await refreshSnapshot();
  });

  onUnmounted(function stopSnapshotRefresh(): void {
    window.clearTimeout(refreshTimer);
  });

  return { busy, connecting, error, snapshot, cancelConnection, setConnection };
}
