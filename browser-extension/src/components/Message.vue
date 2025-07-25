<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
import "highlight.js/styles/base16/gigavolt.min.css";
import MarkdownItPlantuml from "markdown-it-plantuml";
import { CircleFilledIcon, ExclamationCircleIcon } from "vue-tabler-icons";
import NewPromptButton from "./NewPromptButton.vue";
import CopyButton from "./CopyButton.vue";
import CollapsiblePanel from "./CollapsiblePanel.vue";
import * as echarts from "echarts";
import moment from "moment";
import StopIcon from "./StopIcon.vue";
import browser from "webextension-polyfill";
import { findAgentSession } from "../scripts/agent-session-repository";

const props = defineProps<{
  text: string,
  file: Record<string, string>,
  isUser: boolean,
  isComplete: boolean,
  isSuccess: boolean,
  agentLogo: string,
  agentName: string,
  agentId: string,
  reasoning?: string
}>();
const { t } = useI18n();

const isCancelling = ref(false);

const renderedReasoning = computed(() => props.isUser ? null : renderMarkDown(props.reasoning ?? ""));
const renderedMsg = computed(() => props.isUser ? props.text.replaceAll("\n", "<br/>") : renderMarkDown(props.text));
const messageElement = ref<HTMLElement | null>(null);
const resizeObserver: ResizeObserver = new ResizeObserver(onResize);
var chart: any;
var prevWidth: number = 0;

function renderMarkDown(text: string) {
  let md = new MarkdownIt({
    highlight: (code: string, lang: string) => {
      let ret = code;
      if (lang && hljs.getLanguage(lang)) {
        try {
          ret = hljs.highlight(code, { language: lang }).value;
        } catch (__) {
        }
      }
      return "<pre><code class=\"hljs\">" + ret + "</code></pre>";
    }
  });
  useTargetBlankLinks(md);
  useEcharts(md);
  md.use(MarkdownItPlantuml);
  return md.render(text);
}

function useTargetBlankLinks(md: MarkdownIt) {
  let defaultRender = md.renderer.rules.link_open || function(tokens, idx, options, env, self) {
    return self.renderToken(tokens, idx, options);
  };
  md.renderer.rules.link_open = function(tokens, idx, options, env, self) {
    tokens[idx].attrSet("target", "_blank");
    return defaultRender(tokens, idx, options, env, self);
  };
}

function useEcharts(md: MarkdownIt) {
  const defaultRender = md.renderer.rules.fence || function(tokens, idx, options, env, self) {
    return self.renderToken(tokens, idx, options);
  };
  md.renderer.rules.fence = function(tokens, idx, options, env, self) {
    const token = tokens[idx];
    const code = token.content.trim();
    if (token.info === "echarts") {
      nextTick().then(() => {
        const container = messageElement.value!;
        const chartDiv = container.querySelector(".echarts");
        const chartData = container.querySelector(".echarts-data");
        if (chartDiv && chartData) {
          chart = echarts.init(chartDiv as HTMLDivElement);
          const options = JSON.parse(chartData.textContent || "");
          solveEchartsFormatter(options.xAxis.axisLabel);
          solveEchartsFormatter(options.xAxis.axisPointer.label);
          chart.setOption(options);
        }
      });
      return `<div class="echarts" style="width: 100%; height: 200px;"></div><div class="echarts-data" style='display:none'>${code}</div>`;
    }
    return defaultRender(tokens, idx, options, env, self);
  };
}

function solveEchartsFormatter(obj: any) {
  if (obj && obj.formatter) {
    if (obj.formatter.name === "formatEpoch") {
      obj.formatter = formatEpoch(obj.formatter);
    }
  }
}

function formatEpoch(config: any): (value: any) => string {
  return (value: any) => {
    if (typeof value === "object") {
      value = value.value;
    }
    const time = moment(parseInt(value));
    return time.format(config.format);
  };
}

function onResize() {
  if (messageElement.value!.scrollWidth != prevWidth && chart) {
    prevWidth = messageElement.value!.scrollWidth;
    chart.resize();
  }
}

onMounted(() => {
  if (messageElement.value) {
    resizeObserver.observe(messageElement.value);
  }
});

onBeforeUnmount(() => {
  if (messageElement.value) {
    resizeObserver.unobserve(messageElement.value);
  }
});

const onCancel = async () => {
  isCancelling.value = true;

  const currentTab = await browser.tabs.getCurrent();
  const agentSession = await findAgentSession(currentTab.id!);

  console.log(`Canceling agent session '${agentSession?.id}'...`);

  agentSession?.cancelTask();
};
</script>

<template>
  <div class="flex flex-col mb-1 p-1 min-w-7" :class="!isSuccess ? ['border-red-500', 'border-b'] : []">
    <div class="flex items-center flex-row">
      <template v-if="isUser">
        <circle-filled-icon class="text-violet-600" />
      </template>
      <template v-else-if="!isUser && isSuccess">
        <img :src="agentLogo" class="w-5 mr-1 rounded-full" />
      </template>
      <template v-else>
        <exclamation-circle-icon class="text-red-600" />
      </template>

      <span class="text-base">{{ isUser ? t("you") : agentName }}</span>
      <div class="flex-auto flex justify-end">
        <CopyButton v-if="!isUser && text" :text="text" :html="renderedMsg" />
        <NewPromptButton v-if="isUser && text" :is-large-icon="false" :text="text" :agent-id="agentId" />
      </div>
    </div>
    <div class="mt-2 ml-8 mr-2">
      <div>
        <template v-if="file.data">
          <audio controls>
            <source :src="file.url" type="audio/webm">
          </audio>
        </template>

        <template v-if="renderedReasoning">
          <CollapsiblePanel on-open-title="Ocultar razonamiento" on-close-title="Mostrar razonamiento"
                            :text-content="renderedReasoning" />
        </template>

        <template v-if="text">
          <div v-html="renderedMsg" ref="messageElement"
               class="flex flex-col text-sm font-light leading-tight gap-2 rendered-msg" />
        </template>
      </div>

      <template v-if="!isComplete">
        <div class="flex flex-row justify-items-center py-4">
          <div class="grow flex items-center">
            <div class="ml-3 dot-pulse" />
          </div>

          <div class="grow flex flex-row-reverse">
            <StopIcon @click="onCancel" :is-disabled="isCancelling" />
          </div>
        </div>

      </template>
    </div>
  </div>
</template>
<style lang="scss">
@use 'three-dots' with ($dot-width: 5px,
  $dot-height: 5px,
  $dot-color: var(--accent-color));

.rendered-msg pre {
  padding: 15px;
  background: #202126;
  border-radius: 8px;
  text-wrap: wrap;
}

// Fix: Inadequate gap between code blocks within list items.
.rendered-msg li pre {
  margin-bottom: 10px;
}

.rendered-msg pre {
  box-shadow: var(--shadow);
}

.rendered-msg pre code.hljs {
  padding: 0px;
}

div a {
  color: var(--accent-color);
  text-decoration: none;
}

.rendered-msg table {
  width: 100%;
  box-shadow: var(--shadow);
}

.rendered-msg thead tr {
  background-color: #ece6f5;
}

.rendered-msg th,
.rendered-msg td {
  padding: var(--half-spacing);
  border: var(--border);
}

.rendered-msg tbody tr:hover {
  background-color: #f1f1f1;
}

.echarts {
  box-shadow: var(--shadow);
  border-radius: var(--spacing);
  width: 100%;
  padding: var(--half-spacing);
}

.rendered-msg > img {
  box-shadow: var(--shadow);
  border-radius: var(--spacing);
  width: fit-content;
}
</style>

<i18n>
{
  "en": {
    "you": "You"
  },
  "es": {
    "you": "Tú"
  }
}
</i18n>
