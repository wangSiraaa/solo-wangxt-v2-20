import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// 统一把后端 409/422 的 detail 信息抛给界面展示
api.interceptors.response.use(
  (r) => r,
  (err) => {
    const detail = err.response?.data?.detail
    err.friendlyMessage = typeof detail === 'string' ? detail : '请求失败，请重试'
    return Promise.reject(err)
  },
)

export default api
