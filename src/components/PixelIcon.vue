<script setup lang="ts">
import { computed } from "vue";

import accountUrl from "pixelarticons/svg/user.svg";
import bellUrl from "pixelarticons/svg/bell.svg";
import chartUrl from "pixelarticons/svg/chart-bar-big.svg";
import checkUrl from "pixelarticons/svg/check.svg";
import clockUrl from "pixelarticons/svg/clock.svg";
import closeUrl from "pixelarticons/svg/close.svg";
import computerUrl from "pixelarticons/svg/computer.svg";
import eyeOffUrl from "pixelarticons/svg/eye-off.svg";
import eyeUrl from "pixelarticons/svg/eye.svg";
import githubUrl from "pixelarticons/svg/git-branch.svg";
import infoUrl from "pixelarticons/svg/info-box.svg";
import linkUrl from "pixelarticons/svg/link.svg";
import loginUrl from "pixelarticons/svg/login.svg";
import minusUrl from "pixelarticons/svg/minus.svg";
import powerUrl from "pixelarticons/svg/power.svg";
import reloadUrl from "pixelarticons/svg/reload.svg";
import saveUrl from "pixelarticons/svg/save.svg";
import settingsUrl from "pixelarticons/svg/wifi.svg";
import statusUrl from "pixelarticons/svg/audio-waveform.svg";

const icons = {
  account: accountUrl,
  bell: bellUrl,
  chart: chartUrl,
  check: checkUrl,
  clock: clockUrl,
  close: closeUrl,
  computer: computerUrl,
  eye: eyeUrl,
  "eye-off": eyeOffUrl,
  github: githubUrl,
  info: infoUrl,
  link: linkUrl,
  login: loginUrl,
  minus: minusUrl,
  power: powerUrl,
  reload: reloadUrl,
  save: saveUrl,
  settings: settingsUrl,
  status: statusUrl,
} as const;

export type PixelIconName = keyof typeof icons;

const props = defineProps<{ name: PixelIconName }>();

const iconStyle = computed(function resolveIcon(): Record<string, string> {
  return { "--pixel-icon": `url("${icons[props.name]}")` };
});
</script>

<template>
  <span class="pixel-icon" :style="iconStyle" aria-hidden="true"></span>
</template>
