#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xyy_t3_2_keyframes.py —— 《逍遥游》CP4：36 张关键帧。

路线（主文档 §2.4）：GMI 上 MiniMax 系**没有图像模型** ⇒ 关键帧＝
  H3 生成 4s 视频 → **抽首帧**。有人物的镜走 reference-to-video（喂角色母版参考图），
  无人物的镜走 text-to-video。

🔴 角色一致性**只有这一处着力点**：H3 规定「首/尾帧 与 reference_images 不能混用」，
   下游 T4_1 正片那步要用 first_frame_image，就传不了参考图 ⇒ 角色锁必须在这一步喂足。
   本片每个出场角色喂 2 张（全身 ＋ 脸部特写），上限 9 张。

RUN:
  python3 xyy_t3_2_keyframes.py --dry                 # 只打印 payload，⛔ 放量前必跑
  python3 xyy_t3_2_keyframes.py [--only S01,S02] [--workers 6]
"""
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

ROOT = Path(os.environ.get("XYY_ROOT", "."))
sys.path.insert(0, str(ROOT / "_Shared/Program_Scripts"))
import xyy_h3 as X

FILM = ROOT / os.environ.get("XYY_FILM", "film")
SB = FILM / "T3_1-Storyboard/storyboard_xiaoyaoyou_r1.json"
SEL = FILM / "T2_1-Characters/_selected"
OUT = FILM / "T3_2-Keyframes"
MANP = OUT / "manifest_T3_2.json"

REF = {
    "庄周": ["char_zhuangzhou__master_fullbody__MiniMax-H3.png",
             "char_zhuangzhou__master_face__MiniMax-H3.png"],
    "神人": ["char_shenren__master_fullbody__MiniMax-H3.png",
             "char_shenren__master_face__MiniMax-H3.png"],
}
# 配角没有母版立绘 ⇒ 不喂参考图，靠 prompt 里的外形描述（他们每人只出 1–2 镜，
# ⛔ 不值得为此再花 6 张母版的钱；跨镜一致性需求只在 尧/许由 的 S22↔S23，
#    那两镜靠同一句外形描述 ＋ 相邻镜连贯性维持）
NO_REF_ROLES = {"惠子", "宋荣子", "列子", "尧", "许由"}


def payload_for(shot, refs_uploaded):
    p = {"prompt": shot["kf_prompt"], "duration": 4, "resolution": "2K"}
    refs = []
    for c in shot["chars"]:
        for f in REF.get(c, []):
            refs.append(refs_uploaded[f])
    if refs:
        p["reference_images"] = refs          # ⛔ 此时不得再带 first/last_frame_image
    else:
        p["ratio"] = "16:9"                   # t2v 必须给具体画幅
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only"); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    sb = json.loads(SB.read_text(encoding="utf-8"))
    shots = sb["shots"]
    if a.only:
        keep = set(a.only.split(","))
        shots = [s for s in shots if s["id"] in keep]
    OUT.mkdir(parents=True, exist_ok=True)
    man = json.load(open(MANP)) if MANP.exists() else {}

    need = {f for s in shots for c in s["chars"] for f in REF.get(c, [])}
    ups = {}
    if not a.dry:
        for f in sorted(need):
            ups[f] = X.upload(SEL / f)
            print(f"  ⬆ {f} → {ups[f][:80]}")
    else:
        ups = {f: f"<uploaded:{f}>" for f in need}

    if a.dry:
        for s in shots:
            print(f"\n══ {s['id']} [{s['act']}] {s['scene_cn']} chars={s['chars']}")
            print(json.dumps(payload_for(s, ups), ensure_ascii=False, indent=1))
        return

    def one(s):
        sid = s["id"]
        stem = f"kf_{sid}__MiniMax-H3"
        # 🔴 抽帧源 mp4 落 _work/，⛔ 不与交付物 png 并排放。
        #    2026-08-26 实证：36 个 4.46s 的 mp4 躺在 T3_2-Keyframes/ 顶层，
        #    the director 打开目录后问「为何我还没审关键帧你就生成了 video clips」——
        #    它们其实是关键帧的必然副产品（H3 无图像模式，只能出视频再抽帧），
        #    但**目录长得像什么，人就会认为它是什么**。
        #    ⇒ 目录的可读性要靠**写入路径**保证，⛔ 不能指望人去分辨哪些是中间件。
        srcdir = OUT / "_work_抽帧源视频_非clips"
        srcdir.mkdir(parents=True, exist_ok=True)
        mp4, png = srcdir / f"{stem}.mp4", OUT / f"{stem}.png"
        if png.exists():
            print(f"  [{sid}] 已存在，跳过"); return
        t0 = time.time()
        data, info = X.submit_poll(payload_for(s, ups), sid)
        if data is None:
            print(f"  ❌ [{sid}] {info}")
            man[sid] = {"ok": False, "err": str(info)}
        else:
            mp4.write_bytes(data)
            X.frame(mp4, png, 0)
            pb = X.probe(mp4)
            man[sid] = {"ok": True, "png": str(png), "mp4": str(mp4), "rid": info,
                        "probe": pb, "usd": X.cost(4), "sec": round(time.time() - t0, 1),
                        "refs": [c for c in s["chars"] if c in REF]}
            print(f"  ✅ [{sid}] {pb.get('w')}×{pb.get('h')} {man[sid]['sec']}s")
        json.dump(man, open(MANP, "w"), ensure_ascii=False, indent=1)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(one, shots))
    ok = sum(1 for v in man.values() if v.get("ok"))
    print(f"\n完成 {ok}/{len(sb['shots'])}　共 ${round(X.cost(4)*ok,2)}")


if __name__ == "__main__":
    main()
