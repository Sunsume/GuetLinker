<script setup lang="ts">
import { computed, ref, type Component } from "vue";
import { getCurrentWindow } from "@tauri-apps/api/window";

import brandMark from "./assets/guetlinker-mark-v2.png";
import PixelIcon from "./components/PixelIcon.vue";
import { useNetwork } from "./composables/useNetwork";
import AboutPage from "./pages/AboutPage.vue";
import AccountPage from "./pages/AccountPage.vue";
import SettingsPage from "./pages/SettingsPage.vue";
import StatusPage from "./pages/StatusPage.vue";

type TabId = "status" | "settings" | "account" | "about";

const tabs = [
  { id: "status" as const, label: "状态", icon: "status" as const },
  { id: "settings" as const, label: "连接与设置", icon: "settings" as const },
  { id: "account" as const, label: "账户", icon: "account" as const },
  { id: "about" as const, label: "关于", icon: "info" as const },
];

const pageComponents: Record<TabId, Component> = {
  status: StatusPage,
  settings: SettingsPage,
  account: AccountPage,
  about: AboutPage,
};

const activeTab = ref<TabId>("status");
const { busy, connecting, error, cancelConnection, setConnection, snapshot } = useNetwork();
const activePage = computed(function resolveActivePage(): Component {
  return pageComponents[activeTab.value];
});
const activePageBindings = computed(function resolveActivePageBindings(): Record<string, unknown> {
  if (activeTab.value !== "status") {
    return {};
  }
  return {
    busy: busy.value,
    connecting: connecting.value,
    error: error.value,
    snapshot: snapshot.value,
    onCancelConnection: cancelConnection,
    onSetConnection: setConnection,
  };
});

async function minimizeWindow(): Promise<void> {
  try {
    await getCurrentWindow().minimize();
  } catch {
    // Native window APIs are unavailable in a browser preview.
  }
}

async function hideWindow(): Promise<void> {
  try {
    await getCurrentWindow().hide();
  } catch {
    // Native window APIs are unavailable in a browser preview.
  }
}

async function startWindowDrag(): Promise<void> {
  try {
    await getCurrentWindow().startDragging();
  } catch {
    // Native window APIs are unavailable in a browser preview.
  }
}
</script>

<template>
  <main class="app-shell">
    <div class="window-drag-region" aria-hidden="true" @mousedown.left="startWindowDrag"></div>

    <div class="window-actions">
      <button aria-label="最小化" @click="minimizeWindow"><PixelIcon name="minus" /></button>
      <button aria-label="最小化到托盘" @click="hideWindow"><PixelIcon name="close" /></button>
    </div>

    <header class="brand">
      <img :src="brandMark" alt="GuetLinker" />
      <div>
        <h1>GuetLinker</h1>
        <p>校园网连接与自助服务</p>
      </div>
    </header>

    <nav class="pixel-panel nav-bar" aria-label="主导航">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="nav-item"
        :class="{ 'nav-item--active': activeTab === tab.id }"
        :aria-current="activeTab === tab.id ? 'page' : undefined"
        @click="activeTab = tab.id"
      >
        <PixelIcon :name="tab.icon" />
        <span>{{ tab.label }}</span>
      </button>
    </nav>

    <Transition name="page" mode="out-in">
      <KeepAlive>
        <component :is="activePage" :key="activeTab" v-bind="activePageBindings" />
      </KeepAlive>
    </Transition>

    <div class="status-strip" :class="{ 'status-strip--error': error }">
      <span></span>{{ error || (busy ? "正在处理…" : "就绪") }}
    </div>
  </main>
</template>

<style src="./styles.css"></style>
