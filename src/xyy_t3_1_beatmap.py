#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xyy_t3_1_beatmap.py —— 把 36 镜铺到已锁定主版音乐的时间轴上。

🚨 **2026-08-27 重写：镜头必须锚在「它要图解的那一句唱词」上，⛔ 不是按权重均分幕时长。**
   旧做法（每幕 9 镜按权重均分该幕时长）在幕III 出现了**最多 3 个镜头的错位**：
   1:38 画面是「尧让天下」，唱词已经在唱「小鸟做窝只用一枝」；
   1:42 画面是许由，唱词在唱「山上住着神人」。
   —— 因为幕内**唱词的实际唱出时间并不均匀**，均分必然漂。
   the director 用「每 4s 抽一帧对照画面与字幕」把它抓了出来。
   ⇒ 判据从「幕内均匀」改成「**每镜与它那句唱词同时在场**」。

🔴 ⛔ 不用 ASR 的**内容**做判断（🗣 音乐上 ASR 误差极大）；这里用的是
   T4_2 已产出的**逐句时间码**（位置用途）＋ 我设计的「镜↔唱词」对应表。

硬约束：
  · 36 镜、每幕 9 镜（配额窗 6–12）
  · 无人物镜 **≤5s**
  · 全片总长 **＝音乐总长**；credits 另接
  · H3 只能出整秒 4–15s ⇒ 生成 `ceil(设计秒数)`，剪辑时裁到设计值
  · 每镜设计时长 **≤ 已生成 clip 的实际时长**（不然裁不出来）

RUN: python3 xyy_t3_1_beatmap.py
"""
import argparse, json, math
import os
from pathlib import Path

ROOT = Path(os.environ.get("XYY_ROOT", "."))
FILM = ROOT / os.environ.get("XYY_FILM", "film")
SB = FILM / "T3_1-Storyboard/storyboard_xiaoyaoyou_r1.json"
LYR = FILM / "T1_1-Lyrics/lyrics_xiaoyaoyou_r3.json"
TC = FILM / "T4_2-Subtitles/lyric_timecode.json"
OUT = FILM / "T3_1-Storyboard/beatmap_xiaoyaoyou.json"

# ── 镜 ↔ 唱词句号（1–29）对应表 ────────────────────────────────────────
#    来源＝分镜设计时每镜标注的 canon 出处。一句可对多镜（镜在句内再按权重分）。
SHOT2LINE = {
    "S01": 1, "S02": 1, "S03": 1, "S04": 2, "S05": 3, "S06": 4, "S07": 5, "S08": 6, "S09": 7,
    "S10": 8, "S11": 9, "S12": 10, "S13": 10, "S14": 11, "S15": 11, "S16": 12, "S17": 12,
    "S18": 13,
    "S19": 15, "S20": 16, "S21": 16, "S22": 17, "S23": 17, "S24": 18, "S25": 18,
    "S26": 19, "S27": 21,   # ← S27（乘云驾龙）压在副歌一上；S26 接管 L19+L20
    "S28": 22, "S29": 22, "S30": 23, "S31": 24, "S32": 24, "S33": 25, "S34": 26, "S35": 27,
    "S36": 28,
}
# ⚠️ 句 14（小大之辩）、21（副歌一）、29（副歌三）没有专属镜 ——
#    自然并入前一镜（S18 唱到「小大之辩」、S27 唱到副歌一、S36 唱到副歌三），这是设计意图。
#
# 🔴 **尾奏归 credits，⛔ 不归画面**（ 原文：
#    「画面不够用 credits page 填充·禁截断音乐」）：
#    36 镜只覆盖**唱词区间 [0, OUTRO_START)**；末句唱完后的 12.16s 尾奏由 credits 承担，
#    尾奏音乐在 credits 底下继续播完 —— 音乐一秒没截。
#    首版让 S36 去扛尾奏，被撑到 26.89s；而 H3 单次最长只有 15s，根本生成不出来。

MUSIC_LEN = 170.944          # 实测（ffprobe）
INTRO_END = 3.90             # 首个唱词入点
OUTRO_START = 158.78         # 末个唱词出点
LONG_GAPS = [(78.76, 83.16), (116.76, 121.82)]   # >4s 的器乐空档（结构量）
SNAP = 3.0                   # 理论幕界与长空档相差 <SNAP 秒就吸附

# 逐镜镜长权重（1.0＝该幕均分）。快动作给短、大远景/表演给长。
W = {
    # 幕一：鲲化鹏，前半铺陈慢、化形一刻要顿住
    "S01": 1.05, "S02": 1.00, "S03": 0.85, "S04": 1.25, "S05": 1.20,
    "S06": 0.95, "S07": 1.10, "S08": 1.00, "S09": 0.90,
    # 幕二：小大之辩，嘲笑段落节奏碎，巨树两镜要撑住体量
    "S10": 0.95, "S11": 0.80, "S12": 1.00, "S13": 0.85, "S14": 0.85,
    "S15": 0.85, "S16": 1.20, "S17": 1.25, "S18": 1.05,
    # 幕三：无待，宋荣子/列子两段静，神人两镜是女主亮相
    "S19": 1.05, "S20": 1.00, "S21": 1.05, "S22": 0.95, "S23": 0.95,
    "S24": 0.80, "S25": 0.80, "S26": 1.20, "S27": 1.20,
    # 幕四：无用之用，收尾三镜要慢下来（含 12.16s 尾奏）
    "S28": 0.90, "S29": 0.90, "S30": 1.00, "S31": 0.90, "S32": 0.90,
    "S33": 0.95, "S34": 1.05, "S35": 1.15, "S36": 1.25,
}
EMPTY_MAX = 5.0              # 无人物镜上限
# 🔴 单镜上限：没有专属镜的句子（句14、副歌 21/28/29）与 12.16s 尾奏会全部并进**后一镜**，
#    首版把 S36 撑到 26.89s、S27 到 19.00s ——**一个 27 秒的单镜本身就不成立**，
#    而且 H3 单次最长只有 15s，根本生成不出来。
#    ⇒ 超限的镜**向前借时间**（把起点提前，缩短前一镜），迭代到收敛。
#    这保住了「唱词锚定」的主体，又不让并入的副歌/尾奏把末镜撑爆。
MAX_SHOT = 15.0              # H3 单次生成上限就是 15s ⇒ 超过就根本做不出来


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ignore-clip-cap", action="store_true",
                    help="clip 还没按新时长重掷时先出 beatmap，供生成器读取")
    A = ap.parse_args()
    sb = json.loads(SB.read_text(encoding="utf-8"))
    tc = {r["i"]: r for r in json.loads(TC.read_text(encoding="utf-8"))["lines"]}
    shots = {s["id"]: s for s in sb["shots"]}
    ids = [f"S{n:02d}" for n in range(1, 37)]
    assert set(ids) == set(SHOT2LINE), "镜↔唱词表与 36 镜不匹配"

    # 已生成 clip 的实际时长 ⇒ 设计时长不得超过它（不然裁不出来）
    import subprocess
    cap = {}
    for sid in ids:
        f = FILM / f"T4_1-Clips/clip_{sid}__MiniMax-H3.mp4"
        if f.exists():
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(f)], capture_output=True, text=True)
            cap[sid] = float(r.stdout.strip())

    # ── ① 求每镜的**起点锚**：同锚一句的镜，在该句窗内按权重分 ──
    #    🔴 关键：镜的**终点 ＝ 下一镜的起点**（末镜到音乐结束）。
    #    这样构造上就**不可能出现空档** —— 首版按「每句窗独立分配」，
    #    句 14（小和大的分别）、句 21/28/29（副歌）没有专属镜，
    #    它们的窗就成了 8.1s 与 14.6s 的空洞，S36 又被撑到 26.89s。
    #    ⇒ 没有专属镜的句子，自然并入**前一镜**的时长里（那正是设计意图：
    #      S18 唱到「小大之辩」、S27/S36 唱到副歌）。
    lw = {}
    for i_ in sorted(tc):
        nxt = tc.get(i_ + 1)
        lw[i_] = (tc[i_]["start"], nxt["start"] if nxt else OUTRO_START)

    by_line = {}
    for sid in ids:
        by_line.setdefault(SHOT2LINE[sid], []).append(sid)

    starts = {}
    for line, sids in by_line.items():
        a, b = lw[line]
        span = b - a
        wsum = sum(W[x] for x in sids)
        t0 = a
        for x in sids:
            starts[x] = t0
            t0 += span * W[x] / wsum
    starts["S01"] = 0.0                     # 首镜吃掉前奏

    order = sorted(ids, key=lambda x: starts[x])
    assert order == ids, f"锚点顺序与镜号顺序不一致：{order[:6]}"
    seg = {}
    for k, sid in enumerate(ids):
        e = starts[ids[k + 1]] if k + 1 < len(ids) else OUTRO_START
        seg[sid] = [starts[sid], e]

    # ── ②a 单镜 ≤MAX_SHOT：超限的把**起点提前**，向前一镜借时间 ──
    for _ in range(200):
        moved = False
        for k in range(len(ids) - 1, 0, -1):
            sid, prev = ids[k], ids[k - 1]
            d = seg[sid][1] - seg[sid][0]
            if d > MAX_SHOT + 1e-9:
                need = d - MAX_SHOT
                room = (seg[prev][1] - seg[prev][0]) - 2.0      # 前一镜至少留 2.0s
                take = min(need, max(0.0, room))
                if take > 1e-6:
                    seg[prev][1] -= take
                    seg[sid][0] = seg[prev][1]
                    moved = True
        if not moved:
            break

    # ── ②b 无人物镜 ≤5s：超限的钉住，把余量顺移给**后一镜** ──
    #    （相邻镜首尾相接 ⇒ 顺移即可，⛔ 不会产生空档）
    for _ in range(40):
        moved = False
        for k, sid in enumerate(ids[:-1]):
            d = seg[sid][1] - seg[sid][0]
            if not shots[sid]["chars"] and d > EMPTY_MAX + 1e-9:
                seg[sid][1] = seg[sid][0] + EMPTY_MAX
                seg[ids[k + 1]][0] = seg[sid][1]
                moved = True
        if not moved:
            break

    out, fails, short_clips = [], [], []
    print("镜 ↔ 唱词锚定（时间窗取自 T4_2 逐句时间码）：")
    for a_ in ["I", "II", "III", "IV"]:
        aid = [x for x in ids if shots[x]["act"] == a_]
        assert 6 <= len(aid) <= 12, f"幕{a_} {len(aid)} 镜越界"
        print(f"\n【幕{a_}】{len(aid)} 镜")
        for sid in aid:
            s0, s1 = seg[sid]; d = s1 - s0
            empty = not shots[sid]["chars"]
            if empty and d > EMPTY_MAX + 1e-6:
                fails.append(f"{sid} 无人物镜 {d:.2f}s > {EMPTY_MAX}s")
            if sid in cap and d > cap[sid] + 1e-6:
                msg = f"{sid} 设计 {d:.2f}s > 已生成 clip {cap[sid]:.2f}s（裁不出来）"
                (short_clips if A.ignore_clip_cap else fails).append(msg)
            out.append({"id": sid, "act": a_, "start": round(s0, 3), "dur": round(d, 3),
                        "end": round(s1, 3), "empty_shot": empty,
                        "lyric_line": SHOT2LINE[sid],
                        "gen_seconds": max(4, math.ceil(d)),
                        "chars": shots[sid]["chars"], "scene_cn": shots[sid]["scene_cn"]})
            print(f"   {sid} {s0:>7.2f}–{s1:>7.2f}  {d:>5.2f}s  ←第{SHOT2LINE[sid]:>2}句"
                  f"　{'（无人物）' if empty else ''}")

    out.sort(key=lambda r: r["start"])
    tot = sum(r["dur"] for r in out)
    cred_need = MUSIC_LEN - OUTRO_START
    print(f"\n═══ 36 镜合计 {tot:.3f}s ＝ 唱词区间 [0,{OUTRO_START}) "
          f"｜ 尾奏 {cred_need:.2f}s 由 credits 承担（音乐在其下播完，⛔ 未截断）")
    if abs(tot - OUTRO_START) > 0.02:
        fails.append(f"画面总长 {tot:.3f}s ≠ 唱词区间 {OUTRO_START}s（差 {tot-OUTRO_START:+.3f}s）")
    for x, y in zip(out, out[1:]):
        if abs(x["end"] - y["start"]) > 0.02:
            fails.append(f"{x['id']}→{y['id']} 不相接（差 {y['start']-x['end']:+.3f}s）")
    if short_clips:
        print(f"\n⚠️ 有 {len(short_clips)} 段 clip 还不够长，需按新时长重掷（--ignore-clip-cap 已放行写盘）：")
        for m in short_clips:
            print("   " + m)
    if fails:
        print("\n❌ 硬失败：")
        for f_ in fails:
            print("   " + f_)
        raise SystemExit(1)
    OUT.write_text(json.dumps({"music_len": MUSIC_LEN, "picture_end": OUTRO_START,
                               "credits_min_sec": round(cred_need, 3), "shot_to_line": SHOT2LINE,
                               "shots": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n✅ {OUT}")


if __name__ == "__main__":
    main()
