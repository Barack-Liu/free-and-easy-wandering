#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xyy_t4_2_build_ass.py —— 四层中英双语 ASS ＋ 阅读速度硬闸。

层与位置逐条对齐最新一期[redacted]（<another project>）：
  唱词中 LyricCN  底部中央 MarginV 96   ｜ 唱词英 LyricEN 底部中央 MarginV 54（挂在中文下方）
  剧情说明 Story  顶部中央 MarginV 100  ｜ 人物卡 NameCardL/R/C 底部左/右/中 MarginV 196
  场景卡 SceneCard 左上 MarginV 300
  ⇒ 剧情说明在**顶部**、唱词在**底部**，⛔ 两者不会互相占位。

🔴 阅读速度硬闸（）：
  中文 ≤9 字/秒、英文 ≤20 字符/秒，**判据取同屏所有层的总和**，⛔ 不是分层各自达标。
  实现：对每条 cue，取与它**有任何重叠**的所有 cue 组成一组，
  用「该组总字数 ÷ 该组时间并集」判定 —— 这样短暂交叠不会被漏掉。

PlayRes 1920×1080：libass 按 PlayRes 相对渲染，同一个 ASS 原样烧到 4K 版式 1:1
（：⛔ 不为分辨率另生成一份）。

RUN: python3 xyy_t4_2_build_ass.py
"""
import json, re
import os
from pathlib import Path

ROOT = Path(os.environ.get("XYY_ROOT", "."))
FILM = ROOT / os.environ.get("XYY_FILM", "film")
TC = FILM / "T4_2-Subtitles/lyric_timecode.json"
SC = FILM / "T4_2-Subtitles/subtitle_content.json"
BM = FILM / "T3_1-Storyboard/beatmap_xiaoyaoyou.json"
OUT = FILM / "T4_2-Subtitles/逍遥游_subtitles_4layer.ass"

CN_RATE, EN_RATE = 9.0, 20.0
HAN = re.compile(r"[一-鿿]")
# 显示得越久 ⇒ 同屏字数除以更长的时间并集 ⇒ 速率越低。⛔ 不是靠删内容，是靠给足阅读时间。
CARD_DUR, STORY_DUR = 3.8, 5.4

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: LyricCN,Hiragino Sans GB,60,&H00FFFFFF,&H000000FF,&H00202020,&H80000000,1,0,0,0,100,100,0,0,1,3.2,1.6,2,60,60,96,1
Style: LyricEN,Helvetica Neue,36,&H00D8D8D8,&H000000FF,&H00202020,&H80000000,0,0,0,0,100,100,0,0,1,2.4,1.2,2,60,60,54,1
Style: Story,Hiragino Sans GB,40,&H00E8E8E8,&H000000FF,&H00202020,&H80000000,0,0,0,0,100,100,0,0,1,3.0,1.6,8,80,80,100,1
Style: NameCardL,Hiragino Sans GB,38,&H0080E0FF,&H000000FF,&H00202020,&H80000000,1,0,0,0,100,100,0,0,1,2.8,1.4,1,90,90,196,1
Style: NameCardR,Hiragino Sans GB,38,&H0080E0FF,&H000000FF,&H00202020,&H80000000,1,0,0,0,100,100,0,0,1,2.8,1.4,3,90,90,196,1
Style: NameCardC,Hiragino Sans GB,38,&H0080E0FF,&H000000FF,&H00202020,&H80000000,1,0,0,0,100,100,0,0,1,2.8,1.4,2,90,90,196,1
Style: SceneCard,Hiragino Sans GB,36,&H00C8C8C8,&H000000FF,&H00202020,&H80000000,1,0,0,0,100,100,0,0,1,2.8,1.4,7,70,70,300,1
Style: NameCard,Hiragino Sans GB,38,&H0080E0FF,&H000000FF,&H00202020,&H80000000,1,0,0,0,100,100,0,0,1,2.8,1.4,2,0,0,0,1
Style: TitleCN,Songti SC,132,&H00A8D6F0,&H000000FF,&H00101010,&H80000000,1,0,0,0,100,100,10,0,1,5.0,3.0,5,60,60,0,1
Style: TitleEN,Helvetica Neue,46,&H00DCDCDC,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,4,0,1,3.0,1.8,5,60,60,0,1
Style: TitleSub,Hiragino Sans GB,26,&H00AAAAAA,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,2,0,1,2.2,1.4,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(t):
    t = max(0.0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def violations(cues):
    bad = []
    for c in cues:
        grp = [d for d in cues if d[1] > c[0] and d[0] < c[1]]
        span = max(d[1] for d in grp) - min(d[0] for d in grp)
        if span <= 0:
            continue
        cn = sum(len(HAN.findall(d[3])) for d in grp)
        en = sum(len(d[4]) for d in grp)
        if cn / span > CN_RATE or en / span > EN_RATE:
            bad.append((max(cn / span / CN_RATE, en / span / EN_RATE), c, grp, span, cn, en))
    bad.sort(key=lambda x: -x[0])
    return bad


def resolve(cues, max_iter=200):
    """贪心消解：超限时**延长该组里最"可延"的那条**（说明卡 > 卡片），
    因为速率＝总字数 ÷ 时间并集 —— 给足阅读时间比删内容好。
    ⛔ 唱词的时间码由唱腔决定，绝不改动。"""
    EXT = {"Story": 8.5, "SceneCard": 6.0, "NameCard": 6.0}
    for _ in range(max_iter):
        bad = violations(cues)
        if not bad:
            break
        _, c, grp, *_ = bad[0]
        def extendable(d):
            if d[2] not in EXT or (d[1] - d[0]) >= EXT[d[2]]:
                return False
            # 🔴 卡片有本镜边界 ⇒ 延长后不得越界（审片意见 #1 #2 的根因就在这）
            return d[7] is None or (d[1] + 0.3) <= d[7] - 0.10
        cand = [d for d in grp if extendable(d)]
        if not cand:
            break
        cand.sort(key=lambda d: (0 if d[2] == "Story" else 1, d[1] - d[0]))
        d = cand[0]
        i = cues.index(d)
        cues[i] = (d[0], d[1] + 0.3, d[2], d[3], d[4], d[5], d[6], d[7])
    return cues


def main():
    tc = json.loads(TC.read_text(encoding="utf-8"))["lines"]
    sc = json.loads(SC.read_text(encoding="utf-8"))
    bm = {s["id"]: s for s in json.loads(BM.read_text(encoding="utf-8"))["shots"]}
    by_i = {r["i"]: r for r in tc}
    # (start, end, style, cn, en, rendered, shot_start, shot_end)
    # 后两项只有**卡片**有 —— 消解器据此禁止把卡片延长越出本镜
    cues = []

    for r in tc:
        en = sc["lyric_en"][str(r["i"])]
        cues.append((r["start"], r["end"], "LyricCN", r["canon"], "", r["canon"], None, None))
        cues.append((r["start"], r["end"], "LyricEN", "", en, en, None, None))

    for st in sc["story"]:
        r = by_i[st["at"]]
        s0 = r["start"] + 0.15
        txt = st["cn"] + r"\N{\fs30\c&HC0C0C0&}" + st["en"]
        cues.append((s0, min(s0 + STORY_DUR, r["end"] + 1.2), "Story", st["cn"], st["en"], txt, None, None))

    # ── 片头标题（🗣 the director 2026-08-27：「像电影开头会介绍电影名等信息一样」）──
    # 🔴 **叠在开场画面上**，⛔ 不做成独立卡片：成片离比赛 180s 硬闸只剩 0.96s，
    #    位置放在**前奏区间**（首句唱词在 4.10s 开始）⇒ 与唱词层不打架。
    T0, T1 = 0.90, 4.90
    FAD = r"{\fad(500,600)}"
    for txt, style, y in ((sc["title"]["cn"], "TitleCN", 470),
                          (sc["title"]["en"], "TitleEN", 592),
                          (sc["title"]["sub"], "TitleSub", 650)):
        cn = txt if style != "TitleEN" else ""
        en = txt if style == "TitleEN" else ""
        if style == "TitleSub":
            cn, en = txt, ""
        cues.append((T0, T1, style, cn, en,
                     FAD + "{\\pos(960,%d)}" % y + txt, None, None))

    scene_end = {}
    for sid, (cn, en) in sc["scene_cards"].items():
        s0 = bm[sid]["start"] + 0.25
        e0 = min(s0 + CARD_DUR, bm[sid]["end"] - 0.12)
        scene_end[sid] = e0
        txt = cn + r"\N{\fs26\c&HB0B0B0&}" + en
        cues.append((s0, e0, "SceneCard", cn, en, txt, bm[sid]["start"], bm[sid]["end"]))

    # 🔴 人物卡两条硬约束（🗣 the director 2026-08-27 审片意见 #1 #2）：
    #    ① **横向位置＝该镜人物实际所在**（x 由逐镜看关键帧实测），用 \pos() 精确落位，
    #       ⛔ 不用 L/C/R 三档 —— 列子在画面中央偏右，卡却在左下角就是这么来的。
    #    ② **必须限制在自己那一镜的 [start, end] 内**。首版被阅读速度消解器一路延长，
    #       S19「宋荣子」的卡越界跑到了 S20 列子的镜头上 ——
    #       **人物卡活过它自己那一镜，就会给错误的画面贴标签。**
    for sid, (cn, en, xf) in sc["name_cards"].items():
        sh = bm[sid]
        s0 = max(sh["start"] + 0.45, scene_end.get(sid, 0) + 0.2)
        e0 = min(s0 + CARD_DUR, sh["end"] - 0.12)          # ← 硬钳到本镜内
        if e0 - s0 < 1.2:                                   # 本镜放不下就贴着镜尾放
            s0, e0 = max(sh["start"] + 0.2, sh["end"] - 1.6), sh["end"] - 0.12
        x = int(min(max(xf, 0.18), 0.82) * 1920)
        txt = (r"{\pos(%d,884)}" % x) + cn + r"\N{\fs28\c&H70C8E0&}" + en
        cues.append((s0, e0, "NameCard", cn, en, txt, sh["start"], sh["end"]))

    cues.sort(key=lambda c: (c[0], c[2]))
    cues = resolve(cues)

    # ── 阅读速度硬闸：同屏所有层总和 ──────────────────────────────
    v = violations(cues)
    bad = [(c[2], round(c[0], 2), cn, en, round(span, 2),
            round(cn / span, 1), round(en / span, 1)) for _, c, grp, span, cn, en in v]
    if bad:
        print(f"❌ 阅读速度超限 {len(bad)} 处（中文门 {CN_RATE} 字/s，英文门 {EN_RATE} 字符/s）：")
        for b in sorted(set(bad))[:20]:
            print(f"   {b[0]:<10} @{b[1]:>7}s  同屏 中{b[2]}字/英{b[3]}字符 ÷ {b[4]}s "
                  f"= {b[5]}字/s · {b[6]}字符/s")
    else:
        print(f"✅ 阅读速度全绿（中文 ≤{CN_RATE} 字/s、英文 ≤{EN_RATE} 字符/s，同屏总和口径）")

    lines = [f"Dialogue: 0,{ts(c[0])},{ts(c[1])},{c[2]},,0,0,0,,{c[5]}" for c in cues]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n✅ {OUT}　{len(cues)} 条 cue")
    for k in ("LyricCN", "LyricEN", "Story", "SceneCard"):
        print(f"   {k:<10} {sum(1 for c in cues if c[2]==k)} 条")
    print(f"   NameCard*  {sum(1 for c in cues if c[2].startswith('NameCard'))} 条")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
