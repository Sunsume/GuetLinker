<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { invoke } from "@tauri-apps/api/core";

import PixelIcon from "../components/PixelIcon.vue";

interface Settings {
  studentId: string;
  password: string;
  operator: string;
  quiet: boolean;
  notification: boolean;
  autoReconnect: boolean;
  autoStart: boolean;
  startMinimized: boolean;
}

interface IspOption {
  value: string;
  label: string;
  suffix: string;
}

interface SaveSettingsResult {
  notificationTested: boolean;
  notificationError: string;
}

const defaultOperators = ["校园网", "中国移动", "中国联通", "中国电信", "中国广电"];
const operators = ref<string[]>([...defaultOperators]);
const passwordVisible = ref(false);
const passwordLoading = ref(false);
const saveNotice = ref("");
const notificationWarning = ref("");
const loading = ref(true);
const settings = reactive<Settings>({
  studentId: "",
  password: "",
  operator: "校园网",
  quiet: false,
  notification: true,
  autoReconnect: false,
  autoStart: false,
  startMinimized: false,
});

function showNotice(message: string): void {
  saveNotice.value = message;
  window.setTimeout(function clearNotice(): void {
    saveNotice.value = "";
  }, 2_200);
}

function isPasswordPlaceholder(password: string): boolean {
  return password.length > 0 && Array.from(password).every(function isBullet(character): boolean {
    return character === "•";
  });
}

async function togglePasswordVisibility(): Promise<void> {
  if (passwordVisible.value) {
    passwordVisible.value = false;
    return;
  }
  if (isPasswordPlaceholder(settings.password)) {
    passwordLoading.value = true;
    try {
      settings.password = await invoke<string>("reveal_saved_password");
    } catch (error) {
      showNotice(typeof error === "string" ? error : "密码读取失败");
      return;
    } finally {
      passwordLoading.value = false;
    }
  }
  passwordVisible.value = true;
}

async function loadSettings(): Promise<void> {
  try {
    Object.assign(settings, await invoke<Settings>("get_settings"));
  } catch (error) {
    showNotice(typeof error === "string" ? error : "设置读取失败");
  } finally {
    loading.value = false;
  }
}

async function loadOperators(): Promise<void> {
  try {
    const options = await invoke<IspOption[]>("get_isp_options");
    const labels = options.map(function selectLabel(option): string {
      return option.label;
    });
    operators.value = Array.from(new Set([...labels, ...defaultOperators]));
  } catch {
    operators.value = [...defaultOperators];
  }
}

async function saveSettings(): Promise<void> {
  saveNotice.value = "正在保存…";
  try {
    const result = await invoke<SaveSettingsResult>("save_settings", {
      settings: { ...settings },
    });
    notificationWarning.value = result.notificationError;
    if (result.notificationError) {
      showNotice(`设置已保存；${result.notificationError}`);
    } else if (result.notificationTested) {
      showNotice("设置已保存，测试通知已发送");
    } else {
      showNotice("设置已安全保存到本机");
    }
  } catch (error) {
    showNotice(typeof error === "string" ? error : "设置保存失败");
  }
}

onMounted(function initializeSettings(): void {
  void Promise.all([loadSettings(), loadOperators()]);
});
</script>

<template>
  <section class="page scroll-page">
    <div class="page-heading">
      <h2>连接与设置</h2>
      <p>管理校园网凭据、通知与启动偏好</p>
    </div>

    <form class="settings-form" @submit.prevent="saveSettings">
      <section class="pixel-panel pixel-card">
        <h3 class="pixel-card__title">校园网连接</h3>
        <fieldset class="settings-fields" :disabled="loading">
          <label><span>学号</span><input v-model="settings.studentId" autocomplete="username" /></label>
          <label class="password-field">
            <span>密码</span>
            <input v-model="settings.password" :type="passwordVisible ? 'text' : 'password'" autocomplete="current-password" />
            <button type="button" :aria-label="passwordVisible ? '隐藏密码' : '显示密码'" :disabled="passwordLoading" @click="togglePasswordVisibility">
              <PixelIcon v-if="passwordLoading" class="spin" name="reload" />
              <PixelIcon v-else-if="passwordVisible" name="eye-off" />
              <PixelIcon v-else name="eye" />
            </button>
          </label>
          <label>
            <span>运营商</span>
            <select v-model="settings.operator">
              <option v-for="operator in operators" :key="operator">{{ operator }}</option>
            </select>
          </label>
          <p class="field-note">密码经本机设备密钥加密保存，仅在你点击眼睛时临时解密显示。</p>
        </fieldset>
      </section>

        <section class="pixel-panel pixel-card compact-card">
          <h3 class="pixel-card__title">通知设置</h3>
          <fieldset class="settings-fields" :disabled="loading">
            <label class="toggle-row"><PixelIcon name="bell" /><span>静默（不通知）</span><input v-model="settings.quiet" type="checkbox" /></label>
            <label class="toggle-row"><PixelIcon name="status" /><span>通知栏气泡</span><input v-model="settings.notification" type="checkbox" /></label>
          </fieldset>
          <p v-if="notificationWarning" class="field-note notification-warning">{{ notificationWarning }}</p>
        </section>

      <section class="pixel-panel pixel-card compact-card">
        <h3 class="pixel-card__title">系统设置</h3>
        <fieldset class="settings-fields" :disabled="loading">
          <label class="toggle-row"><PixelIcon name="reload" /><span>断网后自动重连</span><input v-model="settings.autoReconnect" type="checkbox" /></label>
          <label class="toggle-row"><PixelIcon name="power" /><span>开机自动启动</span><input v-model="settings.autoStart" type="checkbox" /></label>
          <label class="toggle-row"><PixelIcon name="power" /><span>启动时最小化到托盘</span><input v-model="settings.startMinimized" type="checkbox" /></label>
        </fieldset>
      </section>

      <button class="pixel-button pixel-button--primary save-button" type="submit" :disabled="loading">
        <PixelIcon name="save" />保存设置
      </button>
      <Transition name="activity"><p v-if="saveNotice" class="save-notice">{{ saveNotice }}</p></Transition>
    </form>
  </section>
</template>
