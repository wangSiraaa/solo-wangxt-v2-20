<template>
  <h1>上传照片</h1>
  <p class="sub">
    上传即进入本地文件目录，服务端会执行 <b>裁剪（可选）→ 长边限尺寸 → JPEG 压缩</b>，
    并计算 sha256 与 64bit 感知哈希；哈希接近只会产生候选，不会删除任何文件。
  </p>

  <div v-if="error" class="alert error">{{ error }}</div>
  <div v-if="done" class="alert ok">
    已入库《{{ done.filename }}》（{{ done.width }}×{{ done.height }}，pHash={{ done.phash }}）。
    <RouterLink :to="`/photos/${done.id}`">查看详情</RouterLink>
    ，或去 <RouterLink to="/candidates">候选审查</RouterLink>。
  </div>

  <div class="panel">
    <div
      class="upload-drop"
      :class="{ drag }"
      @click.prevent="pick"
      @dragover.prevent="drag = true"
      @dragleave.prevent="drag = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="onPick" />
      <div v-if="!previewUrl">点击选择，或把照片拖到这里</div>
      <img v-else :src="previewUrl" style="max-height:300px;border-radius:8px" alt="预览" />
    </div>

    <div v-if="previewUrl" style="margin-top:16px">
      <label class="row" style="font-size:13px;color:var(--muted)">
        <input type="checkbox" v-model="cropEnabled" /> 上传前手工裁剪（在图上拖拽框选；
        后端按归一化坐标对原图裁剪）
      </label>

      <div v-if="cropEnabled" class="crop-wrap" ref="cropWrap"
           @mousedown="startCrop" style="margin-top:12px">
        <img ref="previewImg" :src="previewUrl" @load="onImgLoad" alt="裁剪底图" />
        <div v-if="crop" class="crop-box"
             :style="{
               left: crop.x * 100 + '%', top: crop.y * 100 + '%',
               width: crop.width * 100 + '%', height: crop.height * 100 + '%',
             }"
             @mousedown.stop="startMove">
          <span class="rh" @mousedown.stop="startResize"></span>
        </div>
      </div>

      <div class="row" style="margin-top:16px">
        <label class="field">原始文件名
          <input :value="file.name" disabled style="width:240px" />
        </label>
        <label class="field">摄影师署名 *
          <input v-model="photographer" placeholder="如：林溪" style="width:160px" />
        </label>
        <label class="field">授权范围 *
          <select v-model="licenseScope">
            <option v-for="s in scopes" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <label class="field" style="flex:1;min-width:220px">说明
          <input v-model="caption" placeholder="场景 / 版本备注" />
        </label>
      </div>

      <div class="row" style="margin-top:16px">
        <button class="primary" :disabled="uploading" @click="submit">
          {{ uploading ? `上传中 ${Math.round(progress * 100)}%` : '压缩并上传' }}
        </button>
        <button @click="reset">换一张</button>
        <span class="muted" style="font-size:12px">
          裁剪框：{{ crop ? (crop.x.toFixed(2)+', '+crop.y.toFixed(2)+', '+crop.width.toFixed(2)+'×'+crop.height.toFixed(2)) : '未框选' }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api.js'

const fileInput = ref(null)
const cropWrap = ref(null)
const file = ref(null)
const previewUrl = ref('')
const drag = ref(false)
const cropEnabled = ref(false)
const crop = ref(null)
const photographer = ref('')
const licenseScope = ref('editorial')
const caption = ref('')
const scopes = ref(['internal', 'editorial', 'commercial', 'exclusive'])
const uploading = ref(false)
const progress = ref(0)
const error = ref('')
const done = ref(null)

onMounted(async () => {
  const m = await api.meta().catch(() => null)
  if (m) scopes.value = m.license_scopes
})

function pick() { fileInput.value.click() }
function onPick(e) { setFile(e.target.files[0]) }
function onDrop(e) { drag.value = false; setFile(e.dataTransfer.files[0]) }

function setFile(f) {
  error.value = ''; done.value = null
  if (!f) return
  file.value = f
  previewUrl.value = URL.createObjectURL(f)
  crop.value = null
  if (!photographer.value) photographer.value = '未署名'
}

function reset() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  file.value = null; previewUrl.value = ''; crop.value = null
  fileInput.value.value = ''
}

// 归一化（0~1）裁剪框，鼠标操作 ----------------------------------------------------------------

function pos(ev) {
  const r = cropWrap.value.getBoundingClientRect()
  return {
    x: Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)),
    y: Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height)),
  }
}

let dragMode = null
let start = null
let origin = null

function startCrop(ev) {
  start = pos(ev); origin = { ...start }
  crop.value = { x: start.x, y: start.y, width: 0.001, height: 0.001 }
  dragMode = 'new'
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', endDrag)
}
function startMove(ev) {
  start = pos(ev); origin = { ...crop.value }
  dragMode = ev.target.classList.contains('rh') ? 'resize' : 'move'
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', endDrag)
}
function onMove(ev) {
  const p = pos(ev)
  const dx = p.x - start.x, dy = p.y - start.y
  if (dragMode === 'new') {
    crop.value = {
      x: Math.min(origin.x, p.x), y: Math.min(origin.y, p.y),
      width: Math.abs(dx), height: Math.abs(dy),
    }
  } else if (dragMode === 'move') {
    crop.value = {
      ...origin,
      x: Math.min(1 - origin.width, Math.max(0, origin.x + dx)),
      y: Math.min(1 - origin.height, Math.max(0, origin.y + dy)),
    }
  } else if (dragMode === 'resize') {
    crop.value = {
      ...origin,
      width: Math.min(1 - origin.x, Math.max(0.02, origin.width + dx)),
      height: Math.min(1 - origin.y, Math.max(0.02, origin.height + dy)),
    }
  }
}
function endDrag() {
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', endDrag)
  if (crop.value && crop.value.width < 0.03) crop.value = null
}
function onImgLoad() { /* 尺寸由 getBoundingClientRect 处理 */ }

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', endDrag)
})

async function submit() {
  error.value = ''
  if (!file.value) return error.value = '请先选择文件'
  if (!photographer.value.trim()) return error.value = '摄影师署名必填'
  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('photographer', photographer.value.trim())
  fd.append('license_scope', licenseScope.value)
  fd.append('caption', caption.value.trim())
  if (cropEnabled.value && crop.value) fd.append('crop', JSON.stringify(crop.value))
  uploading.value = true; progress.value = 0
  try {
    done.value = await api.upload(fd, (p) => (progress.value = p))
    reset()
  } catch (e) {
    error.value = e.message
  } finally {
    uploading.value = false
  }
}
</script>
