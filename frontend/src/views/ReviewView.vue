<template>
  <div>
    <div v-if="error" class="banner error">{{ error }}</div>
    <div v-if="notice" class="banner success">{{ notice }}</div>

    <div class="card">
      <h2>待审查候选（{{ pending.length }}）</h2>
      <p class="hint">哈希接近只产生候选。请人工比对后「确认相似」或标记「误判」，系统不会自动删除任何图片。</p>
      <div v-if="!pending.length" class="hint">暂无待审查候选</div>
      <div v-for="c in pending" :key="c.id" class="card" style="background:#fafbfd">
        <div class="row">
          <b>候选 #{{ c.id }}</b>
          <span class="tag">pHash 距离 {{ c.phash_distance }}</span>
          <span class="tag">dHash 距离 {{ c.dhash_distance }}</span>
          <div class="spacer"></div>
          <button class="ok" @click="confirm(c)">确认相似</button>
          <button class="ghost" @click="reject(c)">误判（不相似）</button>
        </div>
        <div class="compare" style="margin-top:10px">
          <div v-for="p in [c.photo_a, c.photo_b]" :key="p.id" class="photo-box">
            <img :src="`/api/photos/${p.id}/file`" />
            <div class="meta">
              <b>#{{ p.id }} {{ p.original_filename }}</b> · {{ p.photographer }}
              <span :class="`tag license-${p.license_scope}`">{{ p.license_scope }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>已确认相似 · 选择主图并归并</h2>
      <p class="hint">同一组内点击照片选为主图（保留项），其余成员进入归并。授权范围不一致的组无法合并。</p>
      <div v-if="!clusters.length" class="hint">暂无已确认的相似组</div>
      <div v-for="(cluster, i) in clusters" :key="i" class="card" style="background:#fafbfd">
        <div class="row">
          <b>相似组 {{ i + 1 }}</b>
          <span v-if="licenseConflict(cluster)" class="tag review">授权范围不一致，不可合并</span>
          <div class="spacer"></div>
          <button :disabled="!primaryOf[i] || licenseConflict(cluster)" @click="merge(cluster, i)">
            归并，保留主图
          </button>
        </div>
        <div class="contact-sheet" style="margin-top:10px">
          <div v-for="p in cluster" :key="p.id" class="thumb photo-box"
               :class="{ 'primary-pick': primaryOf[i] === p.id }" @click="primaryOf[i] = p.id">
            <img :src="`/api/photos/${p.id}/file`" />
            <div class="meta">
              <b>#{{ p.id }} {{ p.original_filename }}</b>
              {{ p.photographer }}
              <span :class="`tag license-${p.license_scope}`">{{ p.license_scope }}</span>
              <span v-if="primaryOf[i] === p.id" class="tag primary">主图</span>
              <div v-if="p.references.length">引用：{{ p.references.map(r => r.project_name).join('、') }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>误判记录（{{ rejected.length }}）</h2>
      <p class="hint">被人工判定为"不相似"的候选：两张照片都完整保留，候选关闭不再出现。</p>
      <table v-if="rejected.length">
        <thead><tr><th>候选</th><th>照片 A</th><th>照片 B</th><th>哈希距离</th><th>处理时间</th></tr></thead>
        <tbody>
          <tr v-for="c in rejected" :key="c.id">
            <td>#{{ c.id }}</td>
            <td>#{{ c.photo_a.id }} {{ c.photo_a.original_filename }}</td>
            <td>#{{ c.photo_b.id }} {{ c.photo_b.original_filename }}</td>
            <td>p{{ c.phash_distance }} / d{{ c.dhash_distance }}</td>
            <td>{{ new Date(c.reviewed_at).toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="hint">暂无误判记录</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

const candidates = ref([])
const error = ref('')
const notice = ref('')
const primaryOf = reactive({})

const pending = computed(() => candidates.value.filter(c => c.status === 'pending'))
const rejected = computed(() => candidates.value.filter(c => c.status === 'rejected'))
const confirmed = computed(() => candidates.value.filter(c => c.status === 'confirmed'))

// 把已确认的候选对按连通分量聚成相似组
const clusters = computed(() => {
  const parent = new Map()
  const find = (x) => { while (parent.get(x) !== x) { parent.set(x, parent.get(parent.get(x))); x = parent.get(x) } return x }
  const union = (a, b) => parent.set(find(a), find(b))
  const photos = new Map()
  for (const c of confirmed.value) {
    for (const p of [c.photo_a, c.photo_b]) {
      if (!parent.has(p.id)) { parent.set(p.id, p.id); photos.set(p.id, p) }
    }
    union(c.photo_a.id, c.photo_b.id)
  }
  const groups = new Map()
  for (const id of parent.keys()) {
    const root = find(id)
    if (!groups.has(root)) groups.set(root, [])
    groups.get(root).push(photos.get(id))
  }
  return [...groups.values()].filter(g => g.length > 1)
})

function licenseConflict(cluster) {
  return new Set(cluster.map(p => p.license_scope)).size > 1
}

async function load() {
  candidates.value = (await api.get('/candidates')).data
}

async function confirm(c) {
  error.value = ''
  await api.post(`/candidates/${c.id}/confirm`)
  notice.value = `候选 #${c.id} 已确认相似，可在下方选择主图归并`
  await load()
}

async function reject(c) {
  error.value = ''
  await api.post(`/candidates/${c.id}/reject`)
  notice.value = `候选 #${c.id} 已标记为误判：两张照片均保留，该候选不再出现`
  await load()
}

async function merge(cluster, i) {
  error.value = ''; notice.value = ''
  try {
    const { data } = await api.post('/merges', {
      photo_ids: cluster.map(p => p.id),
      primary_photo_id: primaryOf[i],
      note: '人工审查后归并',
    })
    notice.value = `归并完成：组 #${data.id}，主图 #${data.primary_photo_id}；原文件、署名与引用仍可追踪`
    delete primaryOf[i]
    await load()
  } catch (e) {
    error.value = e.friendlyMessage
  }
}

onMounted(load)
</script>
