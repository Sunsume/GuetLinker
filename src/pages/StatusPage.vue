<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
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

export interface PublicEgressInfo {
  ip: string;
  country: string;
  countryCode: string;
  region: string;
  city: string;
  isp: string;
  org: string;
  isProxyNode: boolean;
  isCernet: boolean;
  latencyMs: number | null;
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

// ---------------- Public & Proxy Egress ----------------
const egressInfo = ref<PublicEgressInfo | null>(null);
const loadingEgress = ref(false);

async function refreshEgressInfo(): Promise<void> {
  if (loadingEgress.value) return;
  loadingEgress.value = true;
  try {
    const result = await invoke<PublicEgressInfo | null>("get_public_egress_info");
    egressInfo.value = result;
  } catch {
    // ignore error
  } finally {
    loadingEgress.value = false;
  }
}

// ---------------- Saved Credentials Fallback ----------------
const savedStudentId = ref("");
const savedOperator = ref("");

async function loadSavedCredentials(): Promise<void> {
  try {
    const settings = await invoke<{ studentId: string; operator: string }>("get_settings");
    if (settings) {
      savedStudentId.value = settings.studentId || "";
      savedOperator.value = settings.operator || "";
    }
  } catch {
    // Ignore error
  }
}

const displayAccount = computed(() => {
  if (props.snapshot.account && props.snapshot.account !== "—" && props.snapshot.account !== "") {
    return props.snapshot.account;
  }
  return savedStudentId.value || "—";
});

const displayOperator = computed(() => {
  if (
    props.snapshot.operator &&
    props.snapshot.operator !== "—" &&
    props.snapshot.operator !== "" &&
    props.snapshot.operator !== "未知运营商"
  ) {
    return props.snapshot.operator;
  }
  return savedOperator.value || "—";
});

watch(
  () => props.snapshot.connected,
  (connected) => {
    if (connected) {
      refreshEgressInfo();
    }
  }
);

onMounted(() => {
  probeQuality();
  probeIntervalId = window.setInterval(probeQuality, 3000);
  refreshEgressInfo();
  loadSavedCredentials();
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
      <!-- 1. Hero row: orb + texts on left, connect/disconnect button on right -->
      <div class="status-hero-row">
        <div class="status-orb-group">
          <div class="status-orb-mini" :class="{ 'status-orb-mini--offline': !snapshot.connected }">
            <PixelIcon v-if="snapshot.connected" name="check" />
            <PixelIcon v-else name="close" />
          </div>
          <div class="status-hero-texts">
            <span class="status-prefix">NET STATUS // 校园网状态</span>
            <h2 class="status-title">{{ statusTitle }}</h2>
          </div>
        </div>

        <div class="status-hero-actions">
          <button
            v-if="!snapshot.connected"
            class="pixel-button pixel-button--primary pixel-button--hero"
            :disabled="busy && !connecting"
            @click="handleConnectClick"
          >
            <PixelIcon v-if="connecting" class="spin" name="reload" />
            <PixelIcon v-else name="link" />
            {{ connecting ? "取消" : "连接" }}
          </button>
          <button
            v-else
            class="pixel-button pixel-button--danger pixel-button--hero"
            :disabled="busy"
            @click="emit('setConnection', false)"
          >
            <PixelIcon v-if="busy" class="spin" name="reload" />
            <PixelIcon v-else name="power" />
            断开
          </button>
        </div>
      </div>

      <!-- 2. Spacious 2x2 metadata grid -->
      <div class="status-meta-grid">
        <div class="meta-item">
          <div class="meta-lbl-row">
            <PixelIcon name="account" />
            <span class="meta-lbl">当前账号</span>
          </div>
          <span class="meta-val font-mono" :title="displayAccount">{{ displayAccount }}</span>
        </div>
        <div class="meta-item">
          <div class="meta-lbl-row">
            <PixelIcon name="chart" />
            <span class="meta-lbl">接入运营商</span>
          </div>
          <span class="meta-val" :title="displayOperator">{{ displayOperator }}</span>
        </div>
        <div class="meta-item">
          <div class="meta-lbl-row">
            <PixelIcon name="computer" />
            <span class="meta-lbl">IPv4 内网地址</span>
          </div>
          <span class="meta-val font-mono" :title="snapshot.ipv4 || '—'">{{ snapshot.ipv4 || "—" }}</span>
        </div>
        <div class="meta-item">
          <div class="meta-lbl-row">
            <PixelIcon name="clock" />
            <span class="meta-lbl">心跳检测</span>
          </div>
          <span class="meta-val font-mono">{{ snapshot.checkedAt || '—' }}</span>
        </div>
      </div>

      <div v-if="error" class="inline-error">
        <PixelIcon name="close" />
        <span>{{ error }}</span>
      </div>

      <!-- 3. Subtools: diagnostics & speed test -->
      <div class="status-subtools">
        <button
          class="pixel-subtool-btn"
          type="button"
          :disabled="diagnosing"
          @click="runDiagnostic"
        >
          <PixelIcon v-if="diagnosing" class="spin" name="reload" />
          <PixelIcon v-else name="computer" />
          {{ diagnosing ? "正在体检…" : "一键体检" }}
        </button>
        <button
          class="pixel-subtool-btn"
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

    <!-- Public & Proxy Egress Panel (Spacious) -->
    <article class="pixel-panel egress-panel">
      <div class="egress-header">
        <div class="egress-title-row">
          <PixelIcon name="globe" />
          <h3>公网 / 代理出口检测</h3>
        </div>
        <div class="egress-header-right">
          <span
            v-if="egressInfo"
            class="egress-tag"
            :class="egressInfo.isCernet ? 'egress-tag--danger' : (egressInfo.isProxyNode ? 'egress-tag--proxy' : 'egress-tag--direct')"
          >
            <span class="egress-dot"></span>
            {{ egressInfo.isCernet ? '校园网出口(严查代理)' : (egressInfo.isProxyNode ? '代理节点(已生效)' : '商业运营商出口') }}
          </span>
          <button
            class="pixel-button pixel-button--small egress-refresh-btn"
            type="button"
            :disabled="loadingEgress"
            @click="refreshEgressInfo"
            title="探测当前公网 IP 及翻墙节点"
          >
            <PixelIcon v-if="loadingEgress" class="spin" name="reload" />
            <PixelIcon v-else name="reload" />
            {{ loadingEgress ? "探测中…" : "刷新出口" }}
          </button>
        </div>
      </div>

      <div v-if="egressInfo" class="egress-compact-body">
        <div class="egress-info-row">
          <div class="egress-field">
            <span class="egress-lbl">对外公网 IP</span>
            <span class="egress-ip-highlight font-mono">{{ egressInfo.ip }}</span>
          </div>
          <div class="egress-field">
            <span class="egress-lbl">物理落地 / 节点机房</span>
            <span class="egress-txt" :title="`${egressInfo.country} ${egressInfo.city} · ${egressInfo.isp || egressInfo.org || ''}`">
              {{ egressInfo.country }} {{ egressInfo.city }} · {{ egressInfo.isp || egressInfo.org || '—' }}
            </span>
          </div>
        </div>

        <div
          class="egress-mini-tip"
          :class="egressInfo.isCernet ? 'egress-mini-tip--danger' : (egressInfo.isProxyNode ? 'egress-mini-tip--proxy' : 'egress-mini-tip--direct')"
        >
          <template v-if="egressInfo.isCernet">
            ⚠️ <strong>高危警示：</strong>当前为学校教育网出口(CERNET)，严禁在此开启代理翻墙工具，以防学号被查封！建议切为【中国移动】。
          </template>
          <template v-else-if="egressInfo.isProxyNode">
            🚀 <strong>翻墙代理已接管：</strong>出口已中转至海外/云节点（{{ egressInfo.country }} {{ egressInfo.city }}），外网流量未经过校内审计。
          </template>
          <template v-else>
            🟢 <strong>运营商专线：</strong>当前为国内运营商直连，未经过校内审计系统，可正常访问。
          </template>
        </div>
      </div>

      <div v-else-if="loadingEgress" class="egress-loading-compact">
        <PixelIcon class="spin" name="reload" />
        <span>正在精准探测当前对外公网 IP 及翻墙代理节点…</span>
      </div>

      <div v-else class="egress-loading-compact">
        <PixelIcon name="close" />
        <span>未获取出口数据（连接网络后点击“刷新出口”）</span>
      </div>
    </article>

    <!-- Diagnostics Panel (Collapsible) -->
    <article v-if="showDiagnostic && diagnosticReport" class="pixel-panel diagnostic-panel">
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

      <div class="diagnostic-steps-scroll">
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
          <PixelIcon name="save" />{{ copySuccess ? "✓ 已复制报障单！" : "复制报障诊断单" }}
        </button>
        <button class="pixel-button pixel-button--small" type="button" @click="showDiagnostic = false">
          <PixelIcon name="close" />收起
        </button>
      </div>
    </article>

    <!-- Realtime Network Quality & Waveform Panel (Compact) -->
    <article class="pixel-panel quality-panel">
      <div class="quality-header">
        <h3>实时网络质量</h3>
        <span class="waveform-meta-avg">
          网关均值: <strong :class="averageLatency > 0 && averageLatency < 50 ? 'color-lime' : 'color-warn'">{{ averageLatency > 0 ? averageLatency + 'ms' : '—' }}</strong>
        </span>
      </div>

      <div class="node-compact-row">
        <div v-for="n in nodes" :key="n.id" class="node-pill">
          <span class="node-pill-name">{{ n.name }}</span>
          <span
            class="node-pill-ms"
            :class="n.latencyMs === null ? 'node-latency--timeout' : (n.latencyMs < 30 ? 'node-latency--fast' : (n.latencyMs < 100 ? 'node-latency--medium' : 'node-latency--slow'))"
          >
            {{ n.latencyMs !== null ? n.latencyMs + 'ms' : '超时' }}
          </span>
        </div>
      </div>

      <div class="waveform-box-compact">
        <div class="waveform-canvas-compact">
          <div
            v-for="(val, idx) in latencyHistory"
            :key="idx"
            class="wave-bar-col"
          >
            <div
              class="wave-bar"
              :class="val === 0 ? 'wave-bar--timeout' : (val < 30 ? 'wave-bar--fast' : (val < 100 ? 'wave-bar--medium' : 'wave-bar--slow'))"
              :style="{ height: Math.max(4, Math.min(44, val > 0 ? Math.round(val * 1.0) : 44)) + 'px' }"
              :title="val > 0 ? val + 'ms' : '超时/丢包'"
            ></div>
          </div>
        </div>
        <div class="waveform-caption-compact">
          <span>网关延迟采样 (3s/次)</span>
          <span>最近 {{ latencyHistory.length }} 次</span>
        </div>
      </div>
    </article>
  </section>
</template>
