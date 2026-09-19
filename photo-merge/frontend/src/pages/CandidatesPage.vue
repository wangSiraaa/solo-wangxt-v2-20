<template>
  <h1>相似候选审查</h1>
  <p class="sub">
    pHash 汉明距离 ≤ 阈值（或 sha256 完全一致）只产生候选，<b>必须人工逐对确认</b>。
    「同场景不同照片」是最常见的误判：可在此记录误判原因并驳回，系统会保留完整处理过程。
  </p>

  <div v-if="error" class="alert error">{{ error }}</div>
  <div v-if="notice" class="alert ok">{{ notice }}</div>

  <div class="panel">
    <div class="row">
      <div class="tabs">
        <a :class="{ active: tab === 'pending' }" @click="setTab('pending')">
          待审查 ({{ pendingCount }})
        </a>
        <a :class="{ active: tab === 'rejected' }" @click="setTab('rejected')">
          已判误判 ({{ rejected.length }})
        </a>
        <a :class="{ active: tab === 'confirmed' }" @click="setTab('confirmed')">
          已据以归并 ({{ confirmed.length }})
        </a>
      </div>
      <div class="spacer" />
      <button @click="rescan">全量重扫候选</button>
    </div>
  </div>

  <template v-if="tab === 'pending'">
    <div v-if="!list.length" class="panel muted">没有待审查候选 🎉</div>

    <div v-for="c in list" :key="c.id" class="candidate">
      <div class="twocol" style="grid-column:1 / -1; margin-bottom:4px">
        <div class="row" style="gap:6px">
          <span v-if="c.exact_duplicate" class="badge exact">sha256 精确重复</span>
          <span v-else-if="c.distance >= nearLimit" class="badge danger">距离边缘（重点看是否误判）</span>
          <span v-else class="badge muted">近重复</span>
        </div>
      </div>

      <RouterLink :to="`/photos/${c.photo_a.id}`" style="color:inherit">
        <img :src="c.photo_a.thumb_url" />
        <div class="fname">#{{ c.photo_a.id }} {{ c.photo_a.filename }}</div>
        <div class="muted" style="font-size:12px;margin-top:4px">
          📷{{ c.photo_a.photographer }}
          <span class="badge" :class="c.photo_a.license_scope">{{ c.photo_a.license_scope }}</span>
        </div>
      </RouterLink>

      <div class="mid">
        <div class="dist" :style="{ color: c.distance >= nearLimit ? 'var(--danger)' : 'var(--ink)' }">
          {{ c.distance }}
        </div>
        <div class="muted" style="font-size:11.5px">汉明距离 / 64</div>
      </div>

      <RouterLink :to="`/photos/${c.photo_b.id}`" style="color:inherit">
        <img :src="c.photo_b.thumb_url" />
        <div class="fname">#{{ c.photo_b.id }} {{ c.photo_b.filename }}</div>
        <div class="muted" style="font-size:12px;margin-top:4px">
          📷{{ c.photo_b.photographer }}
          <span class="badge" :class="c.photo_b.license_scope">{{ c.photo_b.license_scope }}</span>
        </div>
      </RouterLink>

      <div class="actions">
        <label class="field" style="flex:1;min-width:260px">
          若两张只是同场景不同照片，请写明误判理由（将留档）：
          <input v-model="reasons[c.id]" placeholder="如：前景主体不同 / 不同机位成片，不能归并" />
        </label>
        <button class="ghost" style="border-color:var(--danger);color:var(--danger)"
                @click="reject(c)">
          判为误判并驳回
        </button>
        <button class="primary" @click="openMerge(c)">归并这两张…</button>
        <span v-if="c.photo_a.license_scope !== c.photo_b.license_scope" class="badge danger">
          授权范围不同，归并会被后端拒绝
        </span>
      </div>
    </div>
  </template>

  <template v-else>
    <div v-if="!list.length" class="panel muted">暂无记录。</div>
    <div v-for="c in list" :key="c.id" class="candidate rejected">
      <div>
        <img :src="c.photo_a.thumb_url" />
        <div class="fname">#{{ c.photo_a.id }} {{ c.photo_a.filename }}</div>
      </div>
      <div class="mid">
        <div class="dist">{{ c.distance }}</div>
        <span class="badge" :class="c.status === 'rejected' ? 'danger' : 'primary'">
          {{ c.status === 'rejected' ? '误判驳回' : '已归并' }}
        </span>
      </div>
      <div>
        <img :src="c.photo_b.thumb_url" />
        <div class="fname">#{{ c.photo_b.id }} {{ c.photo_b.filename }}</div>
      </div>
      <div v-if="c.status === 'rejected'" class="actions">
        <div class="alert warn" style="margin:0;flex:1">
          <b>误判处理记录</b>（{{ fmt(c.decided_at) }}）：{{ c.reject_reason }}
        </div>
      </div>
    </div>
  </template>

  <!-- 单对归并弹层 -->
  <div v-if="merging" class="panel" style="border:2px solid var(--brand)">
    <h2>归并确认</h2>
    <div class="row">
      <span>主图：</span>
      <label class="field">
        <select v-model="mergePrimary">
          <option :value="merging.photo_a.id">#{{ merging.photo_a.id }} {{ merging.photo_a.filename }}</option>
          <option :value="merging.photo_b.id">#{{ merging.photo_b.id }} {{ merging.photo_b.filename }}</option>
        </select>
      </label>
      <span v-if="merging.photo_a.license_scope !== merging.photo_b.license_scope" class="badge danger">
        授权范围不一致，无法归并
      </span>
    </div>
    <div class="row" style="margin-top:12px">
      <button class="primary"
              :disabled="merging.photo_a.license_scope !== merging.photo_b.license_scope"
              @click="confirmMerge">确认归并</button>
      <button @click="merging = null">取消</button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api.js'

const router = useRouter()
const tab = ref('pending')
const pending = ref([])
const rejected = ref([])
const confirmed = ref([])
const reasons = ref({})
const error = ref('')
const notice = ref('')
const nearLimit = 10
const merging = ref(null)
const mergePrimary = ref(null)

const list = ref([])
const pendingCount = ref(0)

async function load() {
  const [p, rj, cf] = await Promise.all([
    api.candidates('pending'), api.candidates('rejected'), api.candidates('confirmed'),
  ])
  pending.value = p; rejected.value = rj; confirmed.value = cf
  pendingCount.value = p.length
  list.value = tab.value === 'pending' ? p : tab.value === 'rejected' ? rj : cf
}
function setTab(t) { tab.value = t; list.value = t === 'pending' ? pending.value : t === 'rejected' ? rejected.value : confirmed.value }

async function reject(c) {
  error.value = ''; notice.value = ''
  const reason = (reasons.value[c.id] || '').trim()
  if (reason.length < 2) {
    error.value = '驳回必须填写误判理由（例如：前景主体不同，是另一张照片）'
    return
  }
  try {
    await api.reject(c.id, reason)
    notice.value = `候选 #${c.id} 已作为误判驳回并留档。`
    await load()
  } catch (e) { error.value = e.message }
}

function openMerge(c) { merging.value = c; mergePrimary.value = c.photo_a.id }
async function confirmMerge() {
  error.value = ''
  try {
    const rec = await api.merge({
      candidate_id: merging.value.id,
      photo_ids: [merging.value.photo_a.id, merging.value.photo_b.id],
      primary_photo_id: mergePrimary.value,
      note: '从候选审查页归并',
    })
    merging.value = null
    router.push({ path: '/merges', query: { highlight: rec.id } })
  } catch (e) { error.value = '归并被拒绝：' + e.message }
}

async function rescan() {
  error.value = ''
  try {
    const r = await api.rescan()
    notice.value = `重扫完成，新增候选 ${r.created} 条。`
    await load()
  } catch (e) { error.value = e.message }
}

function fmt(t) { return t ? new Date(t).toLocaleString('zh-CN') : '' }
onMounted(load)
</script>

<style scoped>
.fname { font-size: 12.5px; font-weight: 600; margin-top: 6px; word-break: break-all; }
</style>
