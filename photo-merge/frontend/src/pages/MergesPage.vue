<template>
  <h1>归并记录与撤销</h1>
  <p class="sub">
    每次归并都保留完整快照：主图、成员、原始引用指向。撤销时恢复原有集合；
    <b>归并之后才新增的引用无法自动判定该回到哪张原图</b>，会逐条列出由人工改指。
  </p>

  <div v-if="error" class="alert error">{{ error }}</div>

  <div v-if="undoResult" class="panel" style="border:2px solid var(--warn)">
    <h2>撤销结果 — 归并组 #{{ undoResult.merge_record_id }}</h2>
    <div class="alert ok">已恢复照片集合：{{ undoResult.restored_photo_ids.map((i) => '#' + i).join('、') }}</div>
    <div v-if="undoResult.post_merge_refs.length" class="alert warn">
      {{ undoResult.message }}
    </div>
    <table v-if="undoResult.post_merge_refs.length" class="refs">
      <thead>
        <tr><th>引用</th><th>项目</th><th>当前指向</th><th>人工改指到</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="r in undoResult.post_merge_refs" :key="r.id">
          <td>#{{ r.id }} {{ r.usage }}</td>
          <td>{{ r.project_code }} · {{ r.project_name }}</td>
          <td><span class="badge primary">主图 #{{ r.resolved_photo_id ?? r.photo_id }}</span></td>
          <td>
            <select :value="reassignTarget[r.id]" @change="reassignTarget[r.id] = +$event.target.value">
              <option v-for="pid in undoResult.restored_photo_ids" :key="pid" :value="pid">
                #{{ pid }} {{ nameOf(pid) }}
              </option>
            </select>
          </td>
          <td>
            <button class="primary" @click="doReassign(r.id)">确认改指</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="muted">无归并后新增引用需要处理。</div>
    <div class="row" style="margin-top:12px">
      <button @click="undoResult = null">关闭</button>
    </div>
  </div>

  <div v-if="!groups.length" class="panel muted">还没有归并操作。去「候选审查」或「接触印样」做一次归并。</div>

  <div v-for="g in groups" :key="g.id" class="merge-group"
       :id="`group-${g.id}`"
       :style="$route.query.highlight == g.id ? 'border-color:var(--brand);box-shadow:0 0 0 3px rgba(47,111,237,.12)' : ''">
    <div class="row">
      <h2 style="margin:0">归并组 #{{ g.id }}</h2>
      <span v-if="g.undone_at" class="badge muted">已于 {{ fmt(g.undone_at) }} 撤销</span>
      <span v-else class="badge primary">生效中</span>
      <span class="muted">{{ fmt(g.created_at) }}</span>
      <div class="spacer" />
      <button v-if="!g.undone_at" class="danger" @click="doUndo(g)">撤销归并，恢复原有集合</button>
    </div>
    <p v-if="g.note" class="muted" style="margin:8px 0">备注：{{ g.note }}</p>

    <div class="merge-strip" style="margin-top:10px">
      <div v-for="m in g.members" :key="m.id" class="mp">
        <RouterLink :to="`/photos/${m.id}`">
          <img :src="m.thumb_url" />
        </RouterLink>
        <span v-if="m.id === g.primary_photo_id" class="tag badge primary">主图</span>
        <span v-else-if="!g.undone_at" class="tag badge merged">副本</span>
        <div class="muted" style="font-size:11.5px;margin-top:4px">
          #{{ m.id }} {{ m.filename }}<br />📷{{ m.photographer }}
          <span class="badge" :class="m.license_scope" style="margin-left:4px">{{ m.license_scope }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'

const route = useRoute()
const groups = ref([])
const undoResult = ref(null)
const reassignTarget = ref({})
const error = ref('')

function nameOf(id) {
  for (const g of groups.value) {
    const m = g.members.find((x) => x.id === id)
    if (m) return m.filename
  }
  return ''
}

async function load() {
  groups.value = await api.merges()
}

async function doUndo(g) {
  error.value = ''
  if (!confirm(`确认撤销归并组 #${g.id}？原文件不会删除，集合将恢复为归并前状态；归并后新增的引用会被列出由你人工处理。`)) return
  try {
    undoResult.value = await api.undo(g.id)
    for (const r of undoResult.value.post_merge_refs) {
      reassignTarget.value[r.id] = undoResult.value.restored_photo_ids[0]
    }
    await load()
  } catch (e) { error.value = e.message }
}

async function doReassign(refId) {
  error.value = ''
  try {
    await api.reassign(refId, reassignTarget.value[refId])
    undoResult.value.post_merge_refs = undoResult.value.post_merge_refs.filter((r) => r.id !== refId)
  } catch (e) { error.value = e.message }
}

function fmt(t) { return t ? new Date(t).toLocaleString('zh-CN') : '' }
onMounted(load)
</script>
