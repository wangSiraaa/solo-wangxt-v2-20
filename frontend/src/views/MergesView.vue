<template>
  <div>
    <div v-if="error" class="banner error">{{ error }}</div>
    <div v-if="undoResult" class="banner warn">
      归并 #{{ undoResult.group.id }} 已撤销，恢复照片：{{ undoResult.restored_photo_ids.map(i => '#' + i).join('、') }}。
      <template v-if="undoResult.references_needing_manual_review.length">
        <b>以下引用发生在归并之后，请人工处理：</b>
        {{ undoResult.references_needing_manual_review.map(r => `${r.project_name}（引用 #${r.id}）`).join('、') }}
      </template>
      <template v-else>归并期间没有新增引用，无需额外处理。</template>
    </div>

    <div class="card">
      <h2>归并记录</h2>
      <p class="hint">归并只改变照片状态，原文件、摄影师署名和项目引用全部保留，可随时撤销。</p>
      <div v-if="!groups.length" class="hint">暂无归并记录</div>
      <div v-for="g in groups" :key="g.id" class="card" style="background:#fafbfd">
        <div class="row">
          <b>归并组 #{{ g.id }}</b>
          <span v-if="g.status === 'active'" class="tag primary">生效中</span>
          <span v-else class="tag merged">已撤销</span>
          <span class="hint">{{ new Date(g.created_at).toLocaleString() }}</span>
          <div class="spacer"></div>
          <button v-if="g.status === 'active'" class="danger" @click="undo(g)">撤销归并</button>
        </div>
        <div class="contact-sheet" style="margin-top:10px">
          <div v-for="m in g.members" :key="m.photo.id" class="thumb">
            <img :src="`/api/photos/${m.photo.id}/file`" />
            <div class="meta">
              <b>#{{ m.photo.id }} {{ m.photo.original_filename }}</b>
              {{ m.photo.photographer }}
              <span :class="`tag license-${m.photo.license_scope}`">{{ m.photo.license_scope }}</span>
              <span v-if="m.photo.id === g.primary_photo_id" class="tag primary">主图</span>
              <span v-else-if="g.status === 'active'" class="tag merged">已归并</span>
              <div v-for="r in m.photo.references" :key="r.id">
                引用：{{ r.project_name }}
                <span v-if="r.needs_manual_review" class="tag review">需人工处理</span>
              </div>
              <div class="row" style="margin-top:4px">
                <input v-model="newRef[m.photo.id]" placeholder="新增引用项目" style="flex:1;padding:4px 6px;font-size:12px" />
                <button class="ghost" style="padding:4px 8px;font-size:12px" @click="addRef(m.photo)">添加</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '../api'

const groups = ref([])
const error = ref('')
const undoResult = ref(null)
const newRef = reactive({})

async function load() {
  groups.value = (await api.get('/merges')).data
}

async function undo(g) {
  error.value = ''
  try {
    undoResult.value = (await api.post(`/merges/${g.id}/undo`)).data
    await load()
  } catch (e) {
    error.value = e.friendlyMessage
  }
}

async function addRef(photo) {
  error.value = ''
  const project = newRef[photo.id]?.trim()
  if (!project) return
  await api.post(`/photos/${photo.id}/references`, { project_name: project })
  newRef[photo.id] = ''
  await load()
}

onMounted(load)
</script>
