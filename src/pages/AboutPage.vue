<script setup lang="ts">
import { getVersion } from "@tauri-apps/api/app";
import { openUrl } from "@tauri-apps/plugin-opener";
import { onMounted, ref } from "vue";

import brandMark from "../assets/guetlinker-mark-v2.png";
import PixelIcon from "../components/PixelIcon.vue";

const repositoryUrl = "https://github.com/Sunsume/GuetLinker";
const appVersion = ref("v2.0.1");

onMounted(async () => {
  try {
    const version = await getVersion();
    if (version) {
      appVersion.value = `v${version}`;
    }
  } catch {
    // Keep default fallback
  }
});

async function openRepository(): Promise<void> {
  try {
    await openUrl(repositoryUrl);
  } catch {
    window.open(repositoryUrl, "_blank", "noopener,noreferrer");
  }
}
</script>

<template>
  <section class="page about-page">
    <article class="pixel-panel about-panel">
      <img :src="brandMark" alt="" />
      <h2>GuetLinker</h2>
      <span class="version-badge">{{ appVersion }}</span>
      <p>桂电校园网连接与自助服务客户端</p>
      <small>实时状态检测 · 可靠自动重连 · 隐私优先</small>
      <button class="pixel-button pixel-button--small" type="button" @click="openRepository">
        <PixelIcon name="github" />访问项目仓库
      </button>
      <footer>MIT License · 为桂电子弟而造</footer>
    </article>
  </section>
</template>
