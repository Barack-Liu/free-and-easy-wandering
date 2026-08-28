#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xyy_t4_1_clips.py —— 《逍遥游》T4_1：36 段正片 clip（MiniMax-H3 · first_frame_image i2v）。

前提：CP4 关键帧已由 the director 人审通过（🔒 2026-08-26）⇒ 每段 clip 的**首帧就是他审过的那一帧**。

H3 硬约束（目录参数表原文，⛔ 违反即报废）：
  · `first_frame_image` 与 `reference_images` **不能同请求混用**
    ⇒ 本步传不了角色参考图，角色一致性**全靠关键帧本身携带**（这是 T3_2 就喂足参考图的原因）
  · i2v 时 `ratio` **无效**（画幅跟随输入图）⇒ ⛔ 不传 ratio，16:9 由 2560×1440 的关键帧锁死
  · `duration` 只能整秒 4–15 ⇒ 生成 `ceil(设计秒数)`，剪辑时裁到 beatmap 的精确值

机检（⛔ 本步不是 checkpoint ⇒ **必须**机检，）：
  · **frame0 认图门**：clip 首帧 vs 输入关键帧的像素差 <8%，≥8% 判定模型没吃输入图 ⇒ 重掷
  · **完整性门**：判据是 `ffprobe 读得出时长`，⛔ 不是「文件存在」（截断文件会让 -f 放行）
  · **时长门**：实测时长 ≥ beatmap 设计值（不够长就没法裁到设计值）

RUN:
  python3 xyy_t4_1_clips.py --dry
  python3 xyy_t4_1_clips.py [--only S01,S02] [--workers 6]
"""
import argparse, json, sys, time
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(os.environ.get("XYY_ROOT", "."))
sys.path.insert(0, str(ROOT / "_Shared/Program_Scripts"))
import xyy_h3 as X

FILM = ROOT / os.environ.get("XYY_FILM", "film")
SB = FILM / "T3_1-Storyboard/storyboard_xiaoyaoyou_r1.json"
BM = FILM / "T3_1-Storyboard/beatmap_xiaoyaoyou.json"
KF = FILM / "T3_2-Keyframes"
OUT = FILM / "T4_1-Clips"
WORK = OUT / "_work"
MANP = OUT / "manifest_T4_1.json"
DIFF_GATE = 0.08


def frame0_diff(mp4: Path, kf: Path) -> float:
    png = WORK / f"_f0_{mp4.stem}.png"
    if not X.frame(mp4, png, 0):
        return 1.0
    a = np.asarray(Image.open(png).convert("RGB").resize((640, 360))).astype(float)
    b = np.asarray(Image.open(kf).convert("RGB").resize((640, 360))).astype(float)
    return float(np.abs(a - b).mean() / 255)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only"); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    sb = {s["id"]: s for s in json.loads(SB.read_text(encoding="utf-8"))["shots"]}
    bm = {s["id"]: s for s in json.loads(BM.read_text(encoding="utf-8"))["shots"]}
    ids = [f"S{n:02d}" for n in range(1, 37)]
    if a.only:
        keep = set(a.only.split(","));  ids = [i for i in ids if i in keep]
    OUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(parents=True, exist_ok=True)
    man = json.load(open(MANP)) if MANP.exists() else {}

    if a.dry:
        for sid in ids:
            b = bm[sid]
            print(f"\n══ {sid}  设计 {b['dur']:.2f}s → 生成 {b['gen_seconds']}s  {sb[sid]['scene_cn']}")
            print(json.dumps({"prompt": sb[sid]["clip_prompt"],
                              "first_frame_image": f"<uploaded:kf_{sid}>",
                              "duration": b["gen_seconds"], "resolution": "2K"},
                             ensure_ascii=False, indent=1))
        print(f"\n合计生成 {sum(bm[i]['gen_seconds'] for i in ids)}s"
              f"　≈ ${0.13*sum(bm[i]['gen_seconds'] for i in ids):.2f}")
        return

    def one(sid):
        b = bm[sid]
        kf = KF / f"kf_{sid}__MiniMax-H3.png"
        dst = OUT / f"clip_{sid}__MiniMax-H3.mp4"
        if dst.exists() and X.probe(dst).get("dur", 0) > 0:
            print(f"  [{sid}] 已存在，跳过"); return
        if not kf.exists():
            print(f"  ❌ [{sid}] 关键帧不存在"); man[sid] = {"ok": False, "err": "no-keyframe"}; return
        t0 = time.time()
        u = X.upload(kf)
        pl = {"prompt": sb[sid]["clip_prompt"], "first_frame_image": u,
              "duration": b["gen_seconds"], "resolution": "2K"}   # ⛔ 不传 ratio / reference_images
        data, info = X.submit_poll(pl, sid)
        if data is None:
            print(f"  ❌ [{sid}] {info}"); man[sid] = {"ok": False, "err": str(info)}
        else:
            tmp = WORK / f"_dl_{sid}.mp4"; tmp.write_bytes(data)
            pb = X.probe(tmp)
            d0 = frame0_diff(tmp, kf)
            long_enough = pb.get("dur", 0) >= b["dur"] - 0.05
            ok = (pb.get("dur", 0) > 0) and (d0 < DIFF_GATE) and long_enough
            if ok:
                tmp.replace(dst)
            man[sid] = {"ok": ok, "clip": str(dst) if ok else None, "rid": info,
                        "probe": pb, "frame0_diff": round(d0, 4),
                        "design_dur": b["dur"], "gen_seconds": b["gen_seconds"],
                        "usd": X.cost(b["gen_seconds"]), "sec": round(time.time() - t0, 1)}
            why = "✅" if ok else ("❌认图门 diff%.1f%%" % (d0 * 100) if d0 >= DIFF_GATE
                                  else "❌时长不足" if not long_enough else "❌文件损坏")
            print(f"  {why} [{sid}] {pb.get('w')}×{pb.get('h')} {pb.get('dur',0):.2f}s "
                  f"(设计 {b['dur']:.2f}s) diff={d0*100:.1f}% {man[sid]['sec']}s")
        json.dump(man, open(MANP, "w"), ensure_ascii=False, indent=1)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(one, ids))
    ok = [k for k, v in man.items() if v.get("ok")]
    bad = [k for k, v in man.items() if not v.get("ok")]
    print(f"\n完成 {len(ok)}/{len(ids)}　共 ${sum(v.get('usd',0) for v in man.values()):.2f}")
    if bad:
        print(f"❌ 未过闸：{bad}")


if __name__ == "__main__":
    main()
