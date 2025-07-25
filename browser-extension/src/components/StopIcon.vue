<script setup lang="ts">
import { PlayerStopFilledIcon } from "vue-tabler-icons";

const props = defineProps<{ isDisabled: boolean }>();
</script>

<template>

  <button class="p-0" title="Detener análisis" aria-label="Detener" :disabled="isDisabled">
    <!--  TODO: eliminar hover classes cuando disabled=true -->
    <player-stop-filled-icon class="w-6 h-6 text-gray-500 hover:text-red-500" />
  </button>
</template>
