<script setup lang="ts">
import { computed, onActivated, reactive, ref } from "vue";
import { invoke } from "@tauri-apps/api/core";

import PixelIcon from "../components/PixelIcon.vue";

interface Settings {
  studentId: string;
}

interface SelfServiceSession {
  account: string;
  displayName: string;
  landingUrl: string;
}

interface LoginResult {
  success: boolean;
  message: string;
  captchaRequired: boolean;
  captchaImage: string;
  session: SelfServiceSession | null;
}

interface AccountOverview {
  status: string;
  anomalyInfo: string;
}

interface TrafficSummary {
  startDate: string;
  endDate: string;
  internationalUpMb: number;
  internationalDownMb: number;
  domesticUpMb: number;
  domesticDownMb: number;
}

const loginForm = reactive({ account: "", password: "", captcha: "" });
const dateRange = reactive(defaultDateRange());
const session = ref<SelfServiceSession | null>(null);
const overview = ref<AccountOverview | null>(null);
const traffic = ref<TrafficSummary | null>(null);
const passwordVisible = ref(false);
const captchaRequired = ref(false);
const captchaImage = ref("");
const preparedAccount = ref<string | null>(null);
const busy = ref(false);
const notice = ref("");

const metrics = computed(function buildMetrics(): Array<{ label: string; value: string }> {
  const value = traffic.value;
  if (!value) {
    return [
      { label: "总流量", value: "—" },
      { label: "国内流量", value: "—" },
      { label: "国际流量", value: "—" },
    ];
  }
  const domestic = value.domesticUpMb + value.domesticDownMb;
  const international = value.internationalUpMb + value.internationalDownMb;
  return [
    { label: "总流量", value: formatTraffic(domestic + international) },
    { label: "国内流量", value: formatTraffic(domestic) },
    { label: "国际流量", value: formatTraffic(international) },
  ];
});

function defaultDateRange(): { startDate: string; endDate: string } {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return { startDate: `${year}-${month}-01`, endDate: `${year}-${month}-${day}` };
}

function formatTraffic(megabytes: number): string {
  if (megabytes >= 1_024) {
    return `${(megabytes / 1_024).toFixed(2)} GB`;
  }
  return `${megabytes.toFixed(1)} MB`;
}

function describeError(error: unknown): string {
  return typeof error === "string" ? error : "请求失败，请稍后重试";
}

function challengeMatchesAccount(account: string): boolean {
  return preparedAccount.value === "" || preparedAccount.value === account;
}

async function submitLogin(): Promise<void> {
  if (busy.value) {
    return;
  }
  busy.value = true;
  notice.value = "正在登录自助服务…";
  try {
    const account = loginForm.account.trim();
    if (!challengeMatchesAccount(account) || !captchaImage.value) {
      await prepareLogin();
      if (captchaImage.value) {
        notice.value = "验证码已更新，请输入验证码";
      }
      return;
    }
    if (!loginForm.captcha.trim()) {
      notice.value = "请输入验证码";
      return;
    }
    const result = await invoke<LoginResult>("self_service_login", {
      account: loginForm.account,
      password: loginForm.password,
      captcha: loginForm.captcha,
    });
    notice.value = result.message;
    captchaRequired.value = result.captchaRequired;
    captchaImage.value = result.captchaImage;
    if (result.success && result.session) {
      session.value = result.session;
      captchaRequired.value = false;
      captchaImage.value = "";
      loginForm.password = "";
      loginForm.captcha = "";
      await refreshAccount();
    }
  } catch (error) {
    notice.value = describeError(error);
  } finally {
    busy.value = false;
  }
}

async function prepareLogin(): Promise<void> {
  captchaRequired.value = true;
  captchaImage.value = "";
  loginForm.captcha = "";
  const account = loginForm.account.trim();
  try {
    captchaImage.value = await invoke<string>("self_service_prepare_login", { account });
    preparedAccount.value = account;
  } catch (error) {
    notice.value = describeError(error);
  }
}

async function refreshCaptcha(): Promise<void> {
  const account = loginForm.account.trim();
  if (!challengeMatchesAccount(account)) {
    await prepareLogin();
    return;
  }
  captchaRequired.value = true;
  try {
    captchaImage.value = await invoke<string>("self_service_captcha");
  } catch (error) {
    notice.value = describeError(error);
  }
}

async function refreshAccount(): Promise<void> {
  if (!session.value) {
    return;
  }
  notice.value = "正在读取账户数据…";
  try {
    overview.value = await invoke<AccountOverview>("self_service_account_overview");
    await refreshTraffic();
    notice.value = "数据已更新";
  } catch (error) {
    notice.value = describeError(error);
  }
}

async function refreshTraffic(): Promise<void> {
  traffic.value = await invoke<TrafficSummary>("self_service_traffic", {
    startDate: dateRange.startDate,
    endDate: dateRange.endDate,
  });
}

async function queryTraffic(): Promise<void> {
  if (busy.value || !session.value) {
    return;
  }
  busy.value = true;
  notice.value = "正在查询流量…";
  try {
    await refreshTraffic();
    notice.value = "流量数据已更新";
  } catch (error) {
    notice.value = describeError(error);
  } finally {
    busy.value = false;
  }
}

async function switchAccount(): Promise<void> {
  await invoke("reset_self_service");
  session.value = null;
  overview.value = null;
  traffic.value = null;
  captchaRequired.value = false;
  captchaImage.value = "";
  preparedAccount.value = null;
  loginForm.password = "";
  loginForm.captcha = "";
  notice.value = "";
  await syncCampusCredentials();
}

async function syncCampusCredentials(): Promise<void> {
  if (session.value || busy.value) {
    return;
  }
  try {
    const [settings, password] = await Promise.all([
      invoke<Settings>("get_settings"),
      invoke<string>("reveal_saved_password"),
    ]);
    loginForm.account = settings.studentId;
    loginForm.password = password;
  } catch (error) {
    notice.value = describeError(error);
    return;
  }
  if (!challengeMatchesAccount(loginForm.account.trim()) || !captchaImage.value) {
    await prepareLogin();
  }
}

onActivated(async function refreshSavedCredentials(): Promise<void> {
  await syncCampusCredentials();
});
</script>

<template>
  <section class="page scroll-page">
    <div class="page-heading">
      <h2>自助服务账户</h2>
      <p>登录校园网自助服务，查看账户状态与流量</p>
    </div>

    <form v-if="!session" class="pixel-panel pixel-card account-login" @submit.prevent="submitLogin">
      <div class="card-title">
        <div><span class="eyebrow">独立安全会话</span><h3>登录自助服务</h3></div>
        <PixelIcon name="login" />
      </div>
      <label><span>学号</span><input v-model="loginForm.account" autocomplete="username" /></label>
      <label class="password-field">
        <span>密码</span>
        <input v-model="loginForm.password" :type="passwordVisible ? 'text' : 'password'" autocomplete="current-password" />
        <button type="button" aria-label="显示或隐藏密码" @click="passwordVisible = !passwordVisible">
          <PixelIcon v-if="passwordVisible" name="eye-off" />
          <PixelIcon v-else name="eye" />
        </button>
      </label>
      <p class="field-note">自动使用“连接与设置”中保存的校园网账号和密码。</p>
      <label v-if="captchaRequired" class="captcha-field">
        <span>验证码</span>
        <input v-model="loginForm.captcha" autocomplete="off" />
        <button type="button" title="刷新验证码" @click="refreshCaptcha">
          <img v-if="captchaImage" :src="`data:image/png;base64,${captchaImage}`" alt="验证码" />
          <span v-else class="captcha-placeholder">刷新</span>
          <PixelIcon name="reload" />
        </button>
      </label>
      <button class="pixel-button pixel-button--primary save-button" type="submit" :disabled="busy">
        <PixelIcon v-if="busy" class="spin" name="reload" />
        <PixelIcon v-else name="login" />
        登录
      </button>
      <p v-if="notice" class="account-notice">{{ notice }}</p>
    </form>

    <template v-else>
      <article class="pixel-panel pixel-card account-card">
        <div class="account-avatar"><PixelIcon name="account" /></div>
        <div>
          <span class="eyebrow">当前账户</span>
          <h3>{{ session.displayName || session.account }}</h3>
          <p>{{ session.account }} · {{ overview?.status || "已登录" }}</p>
        </div>
        <button class="pixel-button pixel-button--small" @click="switchAccount">切换账户</button>
      </article>

      <article class="pixel-panel pixel-card traffic-card">
        <div class="card-title">
          <div><span class="eyebrow">用量概览</span><h3>网络流量</h3></div>
          <PixelIcon name="chart" />
        </div>
        <div class="date-query">
          <input v-model="dateRange.startDate" type="date" />
          <span>至</span>
          <input v-model="dateRange.endDate" type="date" />
          <button class="pixel-button pixel-button--small" :disabled="busy" @click="queryTraffic">查询</button>
        </div>
        <div class="metrics">
          <div v-for="metric in metrics" :key="metric.label">
            <span>{{ metric.label }}</span><strong>{{ metric.value }}</strong>
          </div>
        </div>
        <p class="field-note account-summary">{{ overview?.anomalyInfo || "暂无异常信息" }}</p>
        <p v-if="notice" class="account-notice">{{ notice }}</p>
      </article>
    </template>
  </section>
</template>
