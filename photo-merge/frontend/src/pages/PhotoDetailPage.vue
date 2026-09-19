<template>
  <h1 v-if="photo">#{{ photo.id }} {{ photo.filename }}</h1>
  <p class="sub">原始文件索引、感知指纹、摄影师署名、授权范围与全部引用——归并后这些信息仍然可追踪。</p>

  <div v-if="error" class="alert error">{{ error }}</div>

  <div v-if="photo" class="panel">
    <div style="display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:24px"
         class="detail-grid">
      <a :href="photo.original_url" target="_blank">
        <img :src="photo.original_url" style="width:100%;border-radius:10px" alt="原图" />
      </a>
      <div>
        <dl class="kv">
          <dt>状态</dt>
          <dd>
            <span v-if="photo.primary_id" class="badge merged">已归并副本 → 主图
              <RouterLink :to="`/photos/${photo.primary_id}`">#{{ photo.primary_id }}</RouterLink>
            </span>
            <span v-else class="badge primary">当前主图</span>
          </dd>
          <dt>摄影师</dt><dd>📷 {{ photo.photographer }}</dd>
          <dt>授权范围</dt><dd><span class="badge" :class="photo.license_scope">{{ photo.license_scope }}</span></dd>
          <dt>尺寸</dt><dd>{{ photo.width }} × {{ photo.height }}</dd>
          <dt>说明</dt><dd>{{ photo.caption || '—' }}</dd>
          <dt>存储文件</dt><dd class="mono">{{ photo.stored_name }}</dd>
          <dt>sha256</dt><dd class="mono" style="font-size:11px">{{ photo.sha256 }}</dd>
          <dt>pHash</dt><dd class="mono">{{ photo.phash }}</dd>
          <dt>上传时间</dt><dd>{{ fmt(photo.uploaded_at) }}</dd>
        </dl>
      </div>
    </div>
  </div>

  <div v-if="photo" class="panel">
    <h2>引用项目（{{ photo.refs.length }}）</h2>
    <p class="muted" style="margin-top:0;font-size:12.5px">
      引用永远记录“当时选了哪一个文件”；归并生效时解析到主图，撤销后回到本文件。
    </p>
    <table class="refs">
      <thead><tr><th>引用</th><th>项目</th><th>用途</th><th>解析结果</th><th>链路</th></tr></thead>
      <tbody>
        <tr v-for="r in photo.refs" :key="r.id">
          <td>#{{ r.id }}</td>
          <td>{{ r.project_code }} · {{ r.project_name }}</td>
          <td>{{ r.usage }}</td>
          <td>
            <RouterLink :to="`/photos/${r.resolved_photo_id}`">
              <span class="badge" :class="r.resolved_photo_id === photo.id ? 'primary' : 'merged'">
                当前取图 #{{ r.resolved_photo_id }}
              </span>
            </RouterLink>
          </td>
          <td>
            <button class="ghost" @click="resolve(r.id)">解析</button>
            <span v-if="paths[r.id]" class="mono">{{ paths[r.id].path.join(' → ') }}
              （{{ paths[r.id].hop_count }} 跳）</span>
          </td>
        </tr>
        <tr v-if="!photo.refs.length"><td colspan="5" class="muted">暂无引用</td></tr>
      </tbody>
    </table>

    <h2 style="margin-top:22px">登记一条引用</h2>
    <div class="row">
      <label class="field">项目
        <select v-model="newRef.project_id">
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.code }} · {{ p.name }}</option>
        </select>
      </label>
      <label class="field">用途
        <input v-model="newRef.usage" placeholder="如：封面" style="width:200px" />
      </label>
      <button class="primary" @click="addRef">登记引用</button>
    </div>
  </div>

  <RouterLink to="/sheet" class="muted">← 回接触印样</RouterLink>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api.js'

const route = useRoute()
const photo = ref(null)
const projects = ref([])
const paths = ref({})
const error = ref('')
const newRef = reactive({ project_id: null, usage: '内页插图' })

async function load() {
  const id = route.params.id
  photo.value = await api.photo(id)
  projects.value = await api.projects()
  if (!newRef.project_id && projects.value[0]) newRef.project_id = projects.value[0].id
}
async function resolve(refId) {
  error.value = ''
  try { paths.value[refId] = await api.resolve(refId) } catch (e) { error.value = e.message }
}
async function addRef() {
  error.value = ''
  try {
    await api.addRef({ photo_id: photo.value.id, ...newRef })
    await load()
  } catch (e) { error.value = e.message }
}
function fmt(t) { return t ? new Date(t).toLocaleString('zh-CN') : '' }
watch(() => route.params.id, load)
onMounted(load)
</script>
