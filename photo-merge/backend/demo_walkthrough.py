"""一键演示完整工作流（在 seed_demo.py 之后运行）：

1. 驳回两个“同场景不同照片”的误判候选并留档；
2. 归并日落近重复、城市夜景近重复；
3. 尝试归并两张不同授权的人像 → 被后端拒绝（页面可见红条）；
4. 在归并后的日落主图上补一条“归并后新引用”；
   → 之后到页面上点“撤销”，该引用会被提示人工处理。
"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(method, path, payload=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    photos = {p["filename"]: p for p in call("GET", "/api/photos")[1]}
    cands = call("GET", "/api/candidates?status=pending")[1]

    def cand(pred):
        return next(c for c in cands if pred(c))

    # 1) 误判驳回
    reef = cand(lambda c: c["photo_a"]["filename"] == "sunset_01_master.jpg"
                          and "07" in c["photo_b"]["filename"])
    s, r = call("POST", f"/api/candidates/{reef['id']}/reject",
                {"reason": "同一场景但前景由帆船变为礁石群，主体内容不同，是另一张照片"})
    print(f"[误判] sunset 礁石候选 #{reef['id']} -> {s} {r['status']}")

    frame = cand(lambda c: c["photo_a"]["filename"] == "skyline_01.jpg"
                           and "04_different" in c["photo_b"]["filename"])
    s, r = call("POST", f"/api/candidates/{frame['id']}/reject",
                {"reason": "同机位另一张成片，画面多一栋楼入画，属于不同照片而非重复上传"})
    print(f"[误判] skyline 另一帧候选 #{frame['id']} -> {s} {r['status']}")

    # 2a) 归并日落
    sunset = [p["id"] for f, p in photos.items()
              if f.startswith("sunset_0") and not f.startswith("sunset_07")]
    s, rec = call("POST", "/api/merges", {
        "photo_ids": sunset,
        "primary_photo_id": photos["sunset_01_master.jpg"]["id"],
        "note": "风光专题：精确重复/重压缩/调色/裁剪/缩放统一归并到主选片",
    })
    print(f"[归并] 日落组 #{rec['id']} -> {s}")

    # 2b) 归并城市夜景
    skyline = [p["id"] for f, p in photos.items() if f.startswith("skyline_0")
               and not f.startswith("skyline_04")]
    s, rec2 = call("POST", "/api/merges", {
        "photo_ids": skyline,
        "primary_photo_id": photos["skyline_01.jpg"]["id"],
        "note": "广告素材：压缩版与失焦版归并到全景主图",
    })
    print(f"[归并] 城市组 #{rec2['id']} -> {s}")

    # 3) 跨授权归并必须失败
    s, err = call("POST", "/api/merges", {
        "photo_ids": [photos["portrait_01_editorial.jpg"]["id"],
                      photos["portrait_02_recompress.jpg"]["id"]],
        "primary_photo_id": photos["portrait_01_editorial.jpg"]["id"],
    })
    print(f"[红线] 跨授权归并 -> HTTP {s}：{err['detail'][:46]}…")

    # 4) 归并后新引用（撤销时会被标记 needs_manual_review）
    projects = {p["code"]: p for p in call("GET", "/api/projects")[1]}
    s, ref = call("POST", "/api/refs", {
        "project_id": projects["MAG-2026-09"]["id"],
        "photo_id": photos["sunset_01_master.jpg"]["id"],
        "usage": "封面候选（归并之后新增）",
    })
    print(f"[新引用] #{ref['id']} 指向日落主图 -> {s}")

    print("\n现在打开 http://127.0.0.1:8000 → 「归并 / 撤销」撤销日落组，")
    print("即可看到“归并之后的新引用”被拦截并要求人工改指。")


if __name__ == "__main__":
    main()
