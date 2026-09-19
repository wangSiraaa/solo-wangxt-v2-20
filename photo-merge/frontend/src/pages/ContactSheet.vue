<template>
  <h1>接触印样</h1>
  <p class="sub">
    图库全部原始文件索引。可多选后人工归并；紫色角标表示该文件已归并到主图，
    绿色星标为主图。<b>归并不删除原文件</b>，摄影师署名与引用项目始终可追踪。
  </p>

  <div v-if="error" class="alert error">{{ error }}</div>

  <div class="panel">
    <div class="row">
      <div class="tabs">
        <a :class="{ active: filter === 'all' }" @click="setFilter('all')">全部 ({{ counts.all }})</a>
        <a :class="{ active: filter === 'active' }" @click="setFilter('active')">独立主图 ({{ counts.active }})</a>
        <a :class="{ active: filter === 'merged' }" @click="setFilter('merged')">已归并副本 ({{ counts.merged }})</a>
      </div>
      <div class="spacer" />
      <button @click="load">刷新</button>
    </div>
  </div>

  <div v-if="selected.length" class="panel">
    <div class="row">
      <b>已选 {{ selected.length }} 张</b>
      <span v-if="selectionScopes.length > 1" class="badge danger">
        授权范围不一致（{{ selectionScopes.join(' / ') }}）：后端将拒绝归并
      </span>
      <span v-else-if="selected.length" class="badge" :class="selectionScopes[0]">
        授权一致：{{ selectionScopes[0] }}
      </span>
      <div class="spacer" />
      <label class="field" style="flex-direction:row;align-items:center;gap:8px">
        主图
        <select v-model="primaryId">
          <option v-for="p in selectedPhotos" :key="p.id" :value="p.id">
            #{{ p.id }} {{ p.filename }}
          </option>
        </select>
      </label>
      <input v-model="mergeNote" placeholder="归并备注（可选）" style="width:200px" />
      <button class="primary" :disabled="selected.length < 2" @click="doMerge">
        归并所选
      </button>
      <button @click="clearSel">取消选择</button>
    </div>
  </div>

  <div class="sheet-grid">
    <div
      v-for="p in photos"
      :key="p.id"
      class="photo-card"
      :class="{ selected: selected.includes(p.id) }"
    >
      <div class="check" @click.stop="toggle(p.id)">
        {{ selected.includes(p.id) ? '✓' : '' }}
      </div>
      <div v-if="p.primary_id" class="badge merged" style="position:absolute;top:8px;right:8px">
        副本→#{{ p.primary_id }}
      </div>
      <div v-else class="star">主图</div>
      <RouterLink :to="`/photos/${p.id}`">
        <img class="thumb" :src="p.thumb_url" :alt="p.filename" loading="lazy" />
      </RouterLink>
      <div class="meta">
        <div class="fname" :title="p.filename">#{{ p.id }} {{ p.filename }}</div>
        <div class="who">
          <span>📷 {{ p.photographer }}</span>
          <span class="badge" :class="p.license_scope">{{ p.license_scope }}</span>
        </div>
        <div class="who"><span>{{ p.width }}×{{ p.height }}</span>
          <span class="mono">d{{ p.phash.slice(0, 6) }}</span>
        </div>
      </div>
    </div>
  </div>

  <div v-if="!photos.length" class="panel muted">暂无照片，先去「上传」或运行 seed_demo.py。</div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'

const router = useRouter()
const photos = ref([])
const filter = ref('all')
const selected = ref([])
const primaryId = ref(null)
const mergeNote = ref('')
const error = ref('')

const counts = ref({ all: 0, active: 0, merged: 0 })
const selectedPhotos = computed(() =>
  photos.value.filter((p) => selected.value.includes(p.id)),
)
const selectionScopes = computed(() =>
  [...new Set(selectedPhotos.value.map((p) => p.license_scope))],
)

async function load() {
  const [all, active, merged, cur] = await Promise.all([
    api.photos('all'), api.photos('active'), api.photos('merged'),
    api.photos(filter.value),
  ])
  counts.value = { all: all.length, active: active.length, merged: merged.length }
  photos.value = cur
  selected.value = selected.value.filter((id) => cur.some((p) => p.id === id))
}
function setFilter(f) { filter.value = f; load() }
function toggle(id) {
  const i = selected.value.indexOf(id)
  if (i >= 0) selected.value.splice(i, 1)
  else { selected.value.push(id); if (!primaryId.value) primaryId.value = id }
  if (selected.value.length && !selected.value.includes(primaryId.value)) {
    primaryId.value = selected.value[0]
  }
}
function clearSel() { selected.value = []; primaryId.value = null }

async function doMerge() {
  error.value = ''
  try {
    const rec = await api.merge({
      photo_ids: selected.value,
      primary_photo_id: primaryId.value,
      note: mergeNote.value,
    })
    clearSel(); mergeNote.value = ''
    await load()
    router.push({ path: '/merges', query: { highlight: rec.id } })
  } catch (e) {
    error.value = '归并被拒绝：' + e.message
  }
}

onMounted(load)
</script>
