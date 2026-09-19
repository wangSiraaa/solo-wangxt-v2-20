<template>
  <header class="topbar">
    <div class="brand">🖼️ 图库归并台</div>
    <nav>
      <RouterLink to="/upload">上传</RouterLink>
      <RouterLink to="/sheet">接触印样</RouterLink>
      <RouterLink to="/candidates">候选审查</RouterLink>
      <RouterLink to="/merges">归并 / 撤销</RouterLink>
    </nav>
    <div class="spacer" />
    <div class="muted" style="color:#8fa0bb;font-size:12px">
      阈值 {{ meta.phash_threshold }} · {{ meta.database }}
    </div>
  </header>
  <main class="page">
    <RouterView />
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from './api.js'

const meta = ref({ phash_threshold: '…', database: '…' })
onMounted(async () => {
  try { meta.value = await api.meta() } catch { /* 未连接后端时静默 */ }
})
</script>
