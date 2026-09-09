<script setup lang="ts">
import { computed } from "vue";

import PixelIcon from "../components/PixelIcon.vue";
import type { NetworkSnapshot } from "../composables/useNetwork";

const props = defineProps<{
  busy: boolean;
  connecting: boolean;
  error: string;
  snapshot: NetworkSnapshot;
}>();

const emit = defineEmits<{
  cancelConnection: [];
  setConnection: [connected: boolean];
}>();

const statusTitle = computed(function resolveStatusTitle(): string {
  if (props.connecting || props.snapshot.status === "reconnecting") {
    return "正在连接校园网";
  }
  return props.snapshot.connected ? "校园网已登录" : "校园网未连接";
});

function handleConnectClick(): void {
  if (props.connecting) {
    emit("cancelConnection");
    return;
  }
  emit("setConnection", true);
}
</script>

<template>
  <section class="page status-page">
    <article class="pixel-panel status-console">
      <div class="status-overview">
        <div class="status-heading">
          <p>网络状态</p>
          <h2>{{ statusTitle }}</h2>
        </div>

        <div class="status-orb" :class="{ 'status-orb--offline': !snapshot.connected }">
          <PixelIcon v-if="snapshot.connected" name="check" />
          <PixelIcon v-else name="close" />
        </div>
      </div>

      <dl class="network-details">
        <div><PixelIcon name="account" /><dt>当前账号</dt><dd>{{ snapshot.account || "—" }}</dd></div>
        <div><PixelIcon name="chart" /><dt>接入运营商</dt><dd>{{ snapshot.operator || "—" }}</dd></div>
        <div><PixelIcon name="computer" /><dt>IPv4 地址</dt><dd>{{ snapshot.ipv4 || "—" }}</dd></div>
        <div><PixelIcon name="clock" /><dt>上次检测</dt><dd>{{ snapshot.checkedAt }}</dd></div>
      </dl>
      <p v-if="error" class="inline-error">{{ error }}</p>

      <div class="actions-row">
        <button
          class="pixel-button pixel-button--primary"
          :disabled="snapshot.connected || (busy && !connecting)"
          @click="handleConnectClick"
        >
          <PixelIcon v-if="connecting" class="spin" name="reload" />
          <PixelIcon v-else name="link" />
          {{ connecting ? "取消连接" : "连接" }}
        </button>
        <button
          class="pixel-button"
          :class="{ 'pixel-button--primary': snapshot.connected }"
          :disabled="busy || !snapshot.connected"
          @click="emit('setConnection', false)"
        >
          <PixelIcon v-if="busy && snapshot.connected" class="spin" name="reload" />
          <PixelIcon v-else name="power" />
          断开
        </button>
      </div>
    </article>
  </section>
</template>
