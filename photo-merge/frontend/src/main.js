import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import UploadPage from './pages/UploadPage.vue'
import ContactSheet from './pages/ContactSheet.vue'
import CandidatesPage from './pages/CandidatesPage.vue'
import MergesPage from './pages/MergesPage.vue'
import PhotoDetailPage from './pages/PhotoDetailPage.vue'
import './styles.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/sheet' },
    { path: '/upload', component: UploadPage, meta: { title: '上传' } },
    { path: '/sheet', component: ContactSheet, meta: { title: '接触印样' } },
    { path: '/candidates', component: CandidatesPage, meta: { title: '候选审查' } },
    { path: '/merges', component: MergesPage, meta: { title: '归并 / 撤销' } },
    { path: '/photos/:id', component: PhotoDetailPage, meta: { title: '照片详情' } },
  ],
})

createApp(App).use(router).mount('#app')
