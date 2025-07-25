<script lang="ts" setup>
import { ref } from "vue";

const props = defineProps<{ onOpenTitle: str, onCloseTitle: str, textContent: string }>();
const isOpen = ref(true);

</script>

<template>
  <div class="border rounded shadow-md mt-0 mb-4">
    <button
      @click="isOpen = !isOpen"
      class="w-full text-left px-3 py-2 bg-blue-200 text-black font-semibold rounded-top border"
    >
      {{ isOpen ? onOpenTitle : onCloseTitle }}
    </button>

    <div v-show="isOpen" class="p-3 bg-white border-t" v-html="textContent"></div>
  </div>
</template>


