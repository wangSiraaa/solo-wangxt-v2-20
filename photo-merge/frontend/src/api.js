// 极简 API 封装：统一错误信息抛出，供页面 catch 后展示
async function request(method, path, body) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(path, opts)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    throw new Error(msg || `请求失败 ${res.status}`)
  }
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b ?? {}),
  patch: (p, b) => request('PATCH', p, b),
  meta: () => request('GET', '/api/meta'),
  photos: (status = 'all') => request('GET', `/api/photos?status=${status}`),
  photo: (id) => request('GET', `/api/photos/${id}`),
  candidates: (status) => request('GET', `/api/candidates?status=${status}`),
  reject: (id, reason) => request('POST', `/api/candidates/${id}/reject`, { reason }),
  rescan: () => request('POST', '/api/candidates/rescan'),
  merges: () => request('GET', '/api/merges'),
  merge: (payload) => request('POST', '/api/merges', payload),
  undo: (id) => request('POST', `/api/merges/${id}/undo`),
  projects: () => request('GET', '/api/projects'),
  refs: () => request('GET', '/api/refs'),
  addRef: (b) => request('POST', '/api/refs', b),
  reassign: (id, photo_id) => request('PATCH', `/api/refs/${id}/reassign`, { photo_id }),
  resolve: (id) => request('GET', `/api/refs/${id}/resolve`),
  audit: () => request('GET', '/api/audit'),

  upload(formData, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/photos')
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText))
        else {
          try { reject(new Error(JSON.parse(xhr.responseText).detail)) }
          catch { reject(new Error(`上传失败 ${xhr.status}`)) }
        }
      }
      xhr.onerror = () => reject(new Error('网络错误'))
      if (onProgress) xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
      xhr.send(formData)
    })
  },
}
