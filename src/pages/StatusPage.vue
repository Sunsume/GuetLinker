<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { invoke } from "@tauri-apps/api/core";

import PixelIcon from "../components/PixelIcon.vue";
import type { NetworkSnapshot } from "../composables/useNetwork";

export interface NodePingResult {
  id: string;
  name: string;
  target: string;
  latencyMs: number | null;
  isOnline: boolean;
}

export interface DiagnosticStep {
  id: string;
  name: string;
  status: "pass" | "warning" | "fail";
  title: string;
  details: string;
  suggestion: string | null;
}

export interface DiagnosticReport {
  timestamp: string;
  overallStatus: "healthy" | "warning" | "error";
  summary: string;
  steps: DiagnosticStep[];
  exportText: string;
}

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

// ---------------- Realtime Quality & Waveform ----------------
const nodes = ref<NodePingResult[]>([]);
const latencyHistory = ref<number[]>([]);
const probing = ref(false);
let probeIntervalId: number | null = null;

async function probeQuality(): Promise<void> {
  if (probing.value) return;
  probing.value = true;
  try {
    const results = await invoke<NodePingResult[]>("get_network_quality");
    nodes.value = results;
    const targetNode = results.find((n) => n.id === "gateway") || results[0];
    const ms = targetNode?.latencyMs ?? 0;
    latencyHistory.value.push(ms);
    if (latencyHistory.value.length > 16) {
      latencyHistory.value.shift();
    }
  } catch {
    // Ignore probe errors
  } finally {
    probing.value = false;
  }
}

const averageLatency = computed(() => {
  const valid = latencyHistory.value.filter((v) => v > 0);
  if (valid.length === 0) return 0;
  return Math.round(valid.reduce((a, b) => a + b, 0) / valid.length);
});

// ---------------- Diagnostics ----------------
const diagnosing = ref(false);
const diagnosticReport = ref<DiagnosticReport | null>(null);
const showDiagnostic = ref(false);
const copySuccess = ref(false);

async function runDiagnostic(): Promise<void> {
  diagnosing.value = true;
  showDiagnostic.value = true;
  try {
    const report = await invoke<DiagnosticReport>("run_network_diagnostics");
    diagnosticReport.value = report;
  } catch {
    // Ignore
  } finally {
    diagnosing.value = false;
  }
}

async function copyReport(): Promise<void> {
  if (!diagnosticReport.value) return;
  try {
    await navigator.clipboard.writeText(diagnosticReport.value.exportText);
    copySuccess.value = true;
    setTimeout(() => {
      copySuccess.value = false;
    }, 2500);
  } catch {
    // Clipboard fallback
  }
}

onMounted(() => {
  probeQuality();
  probeIntervalId = window.setInterval(probeQuality, 3000);
});

onUnmounted(() => {
  if (probeIntervalId) {
    clearInterval(probeIntervalId);
  }
});
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

      <div class="status-tools-row">
        <button
          class="pixel-button pixel-button--small"
          type="button"
          :disabled="diagnosing"
          @click="runDiagnostic"
        >
          <PixelIcon v-if="diagnosing" class="spin" name="reload" />
          <PixelIcon v-else name="computer" />
          {{ diagnosing ? "正在体检…" : "一键网络体检" }}
        </button>
        <button
          class="pixel-button pixel-button--small"
          type="button"
          :disabled="probing"
          @click="probeQuality"
        >
          <PixelIcon v-if="probing" class="spin" name="reload" />
          <PixelIcon v-else name="reload" />
          刷新测速
        </button>
      </div>
    </article>

    <!-- Diagnostics Panel (Collapsible) -->
    <article v-if="showDiagnostic && diagnosticReport" class="diagnostic-panel">
      <div class="diagnostic-header">
        <h3>网络体检报告</h3>
        <span
          class="diagnostic-badge"
          :class="'diagnostic-badge--' + diagnosticReport.overallStatus"
        >
          {{ diagnosticReport.overallStatus === "healthy" ? "链路良好" : (diagnosticReport.overallStatus === "warning" ? "存在警告" : "检测异常") }}
        </span>
      </div>
      <p class="diagnostic-summary">{{ diagnosticReport.summary }}</p>

      <div class="diagnostic-steps">
        <div v-for="step in diagnosticReport.steps" :key="step.id" class="diagnostic-step">
          <div class="step-top">
            <span>{{ step.name }}</span>
            <span :class="'node-latency--' + (step.status === 'pass' ? 'fast' : (step.status === 'warning' ? 'medium' : 'timeout'))">
              {{ step.status === 'pass' ? '✓ ' + step.title : '! ' + step.title }}
            </span>
          </div>
          <p class="step-details">{{ step.details }}</p>
          <p v-if="step.suggestion" class="step-suggestion">> 建议: {{ step.suggestion }}</p>
        </div>
      </div>

      <div class="diagnostic-actions">
        <button class="pixel-button pixel-button--small pixel-button--primary" type="button" @click="copyReport">
          <PixelIcon name="save" />{{ copySuccess ? "✓ 报障单已复制到剪贴板！" : "复制报障诊断单" }}
        </button>
        <button class="pixel-button pixel-button--small" type="button" @click="showDiagnostic = false">
          <PixelIcon name="close" />收起
        </button>
      </div>
    </article>

    <!-- Realtime Network Quality & Waveform Panel -->
    <article class="pixel-panel quality-panel">
      <div class="quality-header">
        <h3>实时网络质量波形</h3>
        <span class="waveform-meta">网关均值: {{ averageLatency > 0 ? averageLatency + 'ms' : '—' }}</span>
      </div>

      <div class="node-grid">
        <div v-for="n in nodes" :key="n.id" class="node-card">
          <div>
            <span class="node-name">{{ n.name }}</span>
            <span class="node-target">{{ n.target }}</span>
          </div>
          <span
            class="node-latency"
            :class="n.latencyMs === null ? 'node-latency--timeout' : (n.latencyMs < 30 ? 'node-latency--fast' : (n.latencyMs < 100 ? 'node-latency--medium' : 'node-latency--slow'))"
          >
            {{ n.latencyMs !== null ? n.latencyMs + 'ms' : '超时' }}
          </span>
        </div>
      </div>

      <div class="waveform-box">
        <div class="waveform-meta">
          <span>网关延迟实时采样 (最近 16 次)</span>
          <span>采样率: 3s</span>
        </div>
        <div class="waveform-canvas">
          <div
            v-for="(val, idx) in latencyHistory"
            :key="idx"
            class="wave-bar-col"
          >
            <div
              class="wave-bar"
              :class="val === 0 ? 'wave-bar--timeout' : (val < 30 ? 'wave-bar--fast' : (val < 100 ? 'wave-bar--medium' : 'wave-bar--slow'))"
              :style="{ height: Math.max(4, Math.min(68, val > 0 ? val * 1.5 : 68)) + 'px' }"
              :title="val > 0 ? val + 'ms' : '超时/丢包'"
            ></div>
          </div>
        </div>
      </div>
    </article>
  </section>
</template>
