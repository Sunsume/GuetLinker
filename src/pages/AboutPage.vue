<script setup lang="ts">
import { getVersion } from "@tauri-apps/api/app";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { openUrl } from "@tauri-apps/plugin-opener";
import { onMounted, onUnmounted, ref } from "vue";

import brandMark from "../assets/guetlinker-mark-v2.png";
import PixelIcon from "../components/PixelIcon.vue";

export interface AppUpdateInfo {
  hasUpdate: boolean;
  currentVersion: string;
  latestVersion: string;
  releaseName: string;
  releaseNotes: string;
  releaseUrl: string;
  portableDownloadUrl: string | null;
  setupDownloadUrl: string | null;
  publishedAt: string;
}

const repositoryUrl = "https://github.com/Sunsume/GuetLinker";
const appVersion = ref("v2.1.0");
const checking = ref(false);
const checkMessage = ref("");
const updateInfo = ref<AppUpdateInfo | null>(null);
let unlistenUpdate: (() => void) | null = null;

onMounted(async () => {
  try {
    const version = await getVersion();
    if (version) {
      appVersion.value = `v${version}`;
    }
  } catch {
    // Keep default fallback
  }

  try {
    unlistenUpdate = await listen("open-check-update", () => {
      checkForUpdates();
    });
  } catch {
    // Tauri events not available in browser preview
  }
});

onUnmounted(() => {
  if (unlistenUpdate) {
    unlistenUpdate();
  }
});

async function openLink(url: string): Promise<void> {
  try {
    await openUrl(url);
  } catch {
    window.open(url, "_blank", "noopener,noreferrer");
  }
}

async function checkForUpdates(): Promise<void> {
  checking.value = true;
  checkMessage.value = "";
  try {
    const info = await invoke<AppUpdateInfo>("check_app_update");
    updateInfo.value = info;
    if (!info.hasUpdate) {
      checkMessage.value = `当前已是最新版本 (${appVersion.value}) ✓`;
    }
  } catch (err) {
    checkMessage.value = typeof err === "string" ? err : "检查更新失败，请稍后重试";
  } finally {
    checking.value = false;
  }
}
</script>

<template>
  <section class="page about-page">
    <article class="pixel-panel about-panel">
      <img :src="brandMark" alt="" />
      <h2>GuetLinker</h2>
      <div class="version-row">
        <span class="version-badge">{{ appVersion }}</span>
        <span v-if="updateInfo?.hasUpdate" class="update-available-badge">
          可更新至 {{ updateInfo.latestVersion }}
        </span>
      </div>
      <p>桂电校园网连接与自助服务客户端</p>
      <small>实时状态检测 · 可靠自动重连 · 隐私优先</small>

      <div class="about-actions">
        <button
          class="pixel-button pixel-button--small"
          type="button"
          :disabled="checking"
          @click="checkForUpdates"
        >
          <PixelIcon name="reload" />{{ checking ? "正在检查…" : "检查更新" }}
        </button>
        <button class="pixel-button pixel-button--small" type="button" @click="openLink(repositoryUrl)">
          <PixelIcon name="github" />访问项目仓库
        </button>
      </div>

      <p v-if="checkMessage" class="check-feedback">{{ checkMessage }}</p>

      <!-- New version available details card -->
      <div v-if="updateInfo?.hasUpdate" class="update-card">
        <div class="update-header">
          <strong>🎉 发现新版本 {{ updateInfo.latestVersion }}</strong>
          <span v-if="updateInfo.publishedAt" class="update-date">{{ updateInfo.publishedAt.slice(0, 10) }}</span>
        </div>
        <p v-if="updateInfo.releaseName" class="update-title">{{ updateInfo.releaseName }}</p>
        <div v-if="updateInfo.releaseNotes" class="update-notes">
          <pre>{{ updateInfo.releaseNotes }}</pre>
        </div>
        <div class="update-download-actions">
          <button
            v-if="updateInfo.portableDownloadUrl"
            class="pixel-button pixel-button--small pixel-button--primary"
            type="button"
            @click="openLink(updateInfo.portableDownloadUrl)"
          >
            下载便携免安装版
          </button>
          <button
            v-if="updateInfo.setupDownloadUrl"
            class="pixel-button pixel-button--small"
            type="button"
            @click="openLink(updateInfo.setupDownloadUrl)"
          >
            下载安装包
          </button>
          <button
            class="pixel-button pixel-button--small"
            type="button"
            @click="openLink(updateInfo.releaseUrl)"
          >
            前往 Release 页面
          </button>
        </div>
      </div>

      <footer>MIT License · 为桂电子弟而造</footer>
    </article>
  </section>
</template>
