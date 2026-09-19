import { createRouter, createWebHistory } from 'vue-router'
import UploadView from './views/UploadView.vue'
import ReviewView from './views/ReviewView.vue'
import MergesView from './views/MergesView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/upload' },
    { path: '/upload', component: UploadView, name: 'upload' },
    { path: '/review', component: ReviewView, name: 'review' },
    { path: '/merges', component: MergesView, name: 'merges' },
  ],
})
