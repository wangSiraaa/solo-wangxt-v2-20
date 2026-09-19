<template>
  <div>
    <div class="card">
      <h2>上传照片</h2>
      <div v-if="error" class="banner error">{{ error }}</div>
      <div v-if="notice" class="banner success">{{ notice }}</div>
      <form @submit.prevent="submit">
        <div class="row">
          <div style="flex:1">
            <label>图像文件</label>
            <input type="file" accept="image/*" required @change="onFile" />
          </div>
          <div style="flex:1">
            <label>摄影师署名</label>
            <input v-model="form.photographer" required placeholder="如：张三" />
          </div>
          <div style="flex:1">
            <label>授权范围</label>
            <select v-model="form.license_scope">
              <option value="editorial">editorial（编辑用途）</option>
              <option value="commercial">commercial（商业用途）</option>
              <option value="internal">internal（内部用途）</option>
            </select>
          </div>
          <div style="flex:1">
            <label>引用项目（可选）</label>
            <input v-model="form.project_name" placeholder="如：夏季旅游专题" />
          </div>
        </div>
        <div class="row" style="margin-top:14px">
          <button type="submit" :disabled="uploading">{{ uploading ? '上传中…' : '上传' }}</button>
          <span class="hint">上传后系统计算感知哈希，哈希接近的照片只会生成候选，不会自动删除任何图片。</span>
        </div>
      </form>
    </div>

    <div class="card">
      <h2>接触印样（全部在库照片）</h2>
      <div class="contact-sheet">
        <div v-for="p in photos" :key="p.id" class="thumb">
          <img :src="`/api/photos/${p.id}/file`" :alt="p.original_filename" />
          <div class="meta">
            <b>{{ p.original_filename }}</b>
            #{{ p.id }} · {{ p.photographer }}
            <span :class="`tag license-${p.license_scope}`">{{ p.license_scope }}</span>
            <span v-if="p.status === 'merged'" class="tag merged">已归并</span>
            <div v-if="p.references.length">引用：{{ p.references.map(r => r.project_name).join('、') }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '../api'

const photos = ref([])
const error = ref('')
const notice = ref('')
const uploading = ref(false)
const file = ref(null)
const form = reactive({ photographer: '', license_scope: 'editorial', project_name: '' })

function onFile(e) { file.value = e.target.files[0] }

async function load() {
  photos.value = (await api.get('/photos')).data
}

async function submit() {
  error.value = ''; notice.value = ''
  if (!file.value) { error.value = '请选择图像文件'; return }
  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('photographer', form.photographer)
  fd.append('license_scope', form.license_scope)
  if (form.project_name) fd.append('project_name', form.project_name)
  uploading.value = true
  try {
    const { data } = await api.post('/photos/upload', fd)
    notice.value = `已上传 #${data.id} ${data.original_filename}，如有相似照片请到「候选审查」人工确认`
    await load()
  } catch (e) {
    error.value = e.friendlyMessage
  } finally {
    uploading.value = false
  }
}

onMounted(load)
</script>
