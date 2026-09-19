<template>
  <div class="layout">
    <header class="topbar">
      <h1>图库归并工作台</h1>
      <nav>
        <RouterLink to="/upload">上传</RouterLink>
        <RouterLink to="/review">候选审查</RouterLink>
        <RouterLink to="/merges">归并记录</RouterLink>
      </nav>
    </header>
    <main>
      <RouterView />
    </main>
  </div>
</template>
