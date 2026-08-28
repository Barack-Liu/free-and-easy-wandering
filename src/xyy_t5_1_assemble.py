#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xyy_t5_1_assemble.py —— 成片装配：36 clip → 4K 母版（烧四层双语字幕 ＋ credits ＋ 混音乐）。

🔴 **两档输出（🗣 the director 2026-08-27）**：
   > 「在 the director 对于最终 MP4 定稿之前，先不要生成 4K 的 MP4，直接用 i2v 模型导出的
   >  video clips 的分辨率即可；因为 the director 可能对 MP4 有修改意见，每次都用 4K 版本来修改，
   >  太消耗时间。」
   ⇒ 默认 `--review`：**2560×1440 原生**（＝H3 clip 的原分辨率），⛔ 不升采样、⛔ 不锐化。
     每轮修改只重编这一档，省掉 4K 那一遍。
     实测：4K 那一遍单独就要 ~12 分钟，2K 原生 ~3 分钟。
   ⇒ 定稿后才跑 `--master4k` 出投稿母版。
   ⚠️ **两档共用同一个 ASS 文件** ⇒ 字幕版式逐帧一致
     （：libass 按 PlayRes 相对渲染，
      2K/4K 出来的版式 1:1，⛔ 不为分辨率另生成一份字幕）。

🔴 4K 的做法（ / ）：
   **先把无字幕底片升采样到 3840×2160，再用同一个 ASS 在 4K 上重烧字幕**，
   ⛔ 不是把烧好字的 2K 画面像素放大（那样字会糊）。
   同一个 ASS 文件原样使用 —— libass 按 PlayRes(1920×1080) 相对渲染，版式 1:1。
   ⛔ 不为分辨率另生成一份字幕。

🔴 时长（）：
   画面总长 **＝音乐总长**；credits 接在音乐播完**之后**，⛔ 不截断音乐。
   本片受比赛硬约束：成片必须 ≤180s。

裁剪：H3 出的 clip 比设计值长（如 5.17s vs 4.93s）⇒ **从头裁**，
   这样每段的第一帧仍是 the director 审过的那张关键帧。

RUN: python3 xyy_t5_1_assemble.py
"""
import argparse, hashlib, json, subprocess, sys
import os
from pathlib import Path

ROOT = Path(os.environ.get("XYY_ROOT", "."))
FILM = ROOT / os.environ.get("XYY_FILM", "film")
BM = FILM / "T3_1-Storyboard/beatmap_xiaoyaoyou.json"
CLIPS = FILM / "T4_1-Clips"
ASS = FILM / "T4_2-Subtitles/逍遥游_subtitles_4layer.ass"
SONG = FILM / "T1_2-Song/_MASTER/逍遥游__主版__国风说唱__minimax-music-3.0.mp3"
CRED = FILM / "T5_2-Credits/credits_4k.png"
OUT = FILM / "T5_1-Master"
WORK = OUT / "_work"
CRED_TAIL = 4.0      # credits 在音乐播完之后再留的时间
LIMIT = 180.0


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit("❌ " + " ".join(str(x) for x in cmd[:6]) + "\n" + r.stderr[-1500:])
    return r


def ok_file(p: Path) -> bool:
    """🔴 判据是「**ffprobe 读得出时长**」，⛔ 不是「文件存在」。
    2026-08-27 实证：pkill 掉编码进程留下**截断的 mp4**，`exists()` 照样为真 ⇒
    下游 concat 才报 `moov atom not found`。截断文件必须在守卫处就被判死。"""
    if not p.exists() or p.stat().st_size < 4096:
        return False
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return r.returncode == 0 and float(r.stdout.strip()) > 0
    except ValueError:
        return False


def sha_file(p: Path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(buf), b""):
            h.update(b)
    return h.hexdigest()


def stamp(*items) -> str:
    """把「这一步的全部输入」压成一个指纹。上游步骤传自己的 stamp ⇒ 变更沿链传播。"""
    h = hashlib.sha256()
    for it in items:
        h.update(repr(it).encode()); h.update(b"|")
    return h.hexdigest()


def cached(dst: Path, key: str) -> bool:
    """🔴 复用中间件的判据 = 文件完整 **且 输入指纹未变**。

    2026-08-27 实证（ L637 在装配层复发）：
    `ok_file()` 是**截断守卫**，它只回答「这个 mp4 读得出时长吗」。
    我却让它兼职当缓存判据 ⇒ 改完 ASS 重新装配，`picture_2k_subbed.mp4` 因为
    「存在且完整」被整个跳过，**烧进成片的还是上一版字幕**：the director 看到的
    1:38 鼹鼠特写上仍挂着「中枢 · 高台」。
    ⇒ 缓存键必须是**输入内容**，⛔ 不是文件名，也⛔不是「文件在不在」。
    """
    st = dst.with_suffix(dst.suffix + ".stamp")
    return ok_file(dst) and st.exists() and st.read_text(encoding="utf-8").strip() == key


def seal(dst: Path, key: str) -> None:
    dst.with_suffix(dst.suffix + ".stamp").write_text(key, encoding="utf-8")


# 人物卡是唯一活在这条横带里的图层（歌词在 ~984、说明在顶部、场景卡在 ~300）
NC_BAND = (800 / 1080, 890 / 1080)   # PlayResY 归一化后的上下沿


def band(vid: Path, t: float, pre: str = "") -> bytes:
    """取某帧「人物卡横带」的灰度像素。

    🔴 **判据必须缩放不变**（「像素判据须过缩放不变性自测」）：
    首版按**绝对行号**裁（`crop=iw:90:0:800`），2K 底片与 4K 成片对比时两个 crop
    根本不是同一块区域 ⇒ 「卡上/卡外」都报几十万像素，闸对**正确的 4K 母版**误报。
    ⇒ 改成按 `ih` 的**比例**裁；跨分辨率比对时再用 `pre` 把参照片先过一遍
    与成片**完全相同的前置滤镜**（升采样＋锐化），两边几何逐像素对齐。
    """
    y0, y1 = NC_BAND
    vf = f"{pre}crop=iw:ih*{y1 - y0:.6f}:0:ih*{y0:.6f},format=gray"
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(vid),
                        "-frames:v", "1", "-vf", vf, "-f", "rawvideo", "-"],
                       capture_output=True)
    return r.stdout


def verify_namecards(base: Path, subbed: Path, ass: Path, pre: str = "") -> None:
    """🔴 **读像素**的烧录自证：判据是「成片上那条带子里真的多出了字」，
    ⛔ 不是「ASS 文件写对了」，也⛔不是「装配脚本跑完没报错」。

    NameCard 是唯一活在 PlayResY 800–890 这条横带里的图层（歌词在 ~984，
    说明在顶部，场景卡在 ~300）⇒ 拿**烧字幕前/后**同一时刻的这条带子对比：
      · 卡片时刻：必须出现大量强差异像素（描边文字，差值远超编码噪声）
      · 卡片窗口外 0.8s：必须几乎没有（否则说明烧的是**别的版本**的时间轴）
    这一步能直接抓住「ASS 改了但成片用的是缓存旧版」这类错误。
    """
    import re as _re
    def sec(x):
        h, m, ss = x.split(":"); return int(h) * 3600 + int(m) * 60 + float(ss)
    cues = []
    for ln in ass.read_text(encoding="utf-8").splitlines():
        if ln.startswith("Dialogue"):
            f = ln.split(",", 9)
            if f[3].startswith("NameCard"):
                cues.append((sec(f[1]), sec(f[2]), _re.sub(r"\{[^}]*\}", "", f[9]).split("\\N")[0]))
    def hits(t):
        """返回**强差异像素占该横带的比例**（⛔ 不用绝对个数：2K 与 4K 的带子像素数差 2.25 倍）。"""
        a, b = band(base, t, pre), band(subbed, t)
        n = min(len(a), len(b))
        if not n:
            return 0.0
        return sum(1 for i in range(n) if abs(a[i] - b[i]) > 40) / n
    def clean_t(st, en):
        """🔴 反向样本必须是**没有任何人物卡**的时刻。
        首版取 `st-0.8s`，结果落进了**相邻那张卡**的窗口（宋荣子 86.50 收，
        列子 87.07 起）⇒ 闸对两张正确的卡误报。判据的反例也得自己成立。"""
        for d in (0.8, 1.6, 2.4, 4.0, 8.0, 16.0):
            for t in (st - d, en + d):
                if t < 0.2:
                    continue
                if all(not (a - 0.3 <= t <= b + 0.3) for a, b, _ in cues):
                    return t
        return None
    bad = []
    for st, en, txt in cues:
        on = hits((st + en) / 2)
        ot = clean_t(st, en)
        off = hits(ot) if ot is not None else 0
        if on < 0.004 or off > on * 0.25:
            bad.append(f"   ❌ {txt} @{st:.2f}–{en:.2f}s　卡上 {on:.3%}　"
                       f"卡外 {off:.3%}（取样 {ot:.2f}s）" if ot is not None else
                       f"   ❌ {txt} @{st:.2f}–{en:.2f}s　卡上 {on:.3%}　找不到无卡时刻")
    if bad:
        print("❌ 人物卡烧录自证失败（成片里的字幕≠当前 ASS）：")
        print("\n".join(bad))
        sys.exit(1)
    print(f"③ 人物卡烧录自证：{len(cues)} 张全部**在自己的时间窗内**出现、窗外消失 ✅")


def dur(p):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(p)])
    return float(r.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master4k", action="store_true",
                    help="定稿后才用：出 3840×2160 投稿母版")
    ap.add_argument("--locked", action="store_true",
                    help="声明 the director 已明确说过「定稿/审核通过」")
    a = ap.parse_args()
    # 🔴 ：🗣「在 the director 对于最终 MP4 定稿之前，
    #    先不要生成 4K 的 MP4」——审核期间每轮只改一两段，反复超分纯浪费。
    #    ⇒ 闸装在**执行路径上**，⛔ 不是写在文档里提醒我自己（ A：没闸）。
    if a.master4k and not a.locked:
        sys.exit("❌ --master4k 必须同时带 --locked（＝the director 已明说定稿/审核通过）。\n"
                 "   审核期间一律用 i2v 原生画幅零缩放的审核件。")
    FOURK = a.master4k
    OUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(parents=True, exist_ok=True)
    bm = json.loads(BM.read_text(encoding="utf-8"))
    shots = bm["shots"]; MUSIC = bm["music_len"]
    # 🔴 画面只覆盖**唱词区间**；末句唱完后的尾奏由 credits 承担
    #    （：「画面不够用 credits page 填充·禁截断音乐」）。
    #    首版让最后一镜去扛 12.16s 尾奏，被撑到 26.89s —— 一个 27 秒单镜不成立，
    #    而且 H3 单次最长 15s，物理上也生成不出来。
    PIC_END = bm.get("picture_end", MUSIC)
    CRED_SEC = round((MUSIC - PIC_END) + CRED_TAIL, 3)

    # ① 逐段从头裁到设计值（首帧＝已审关键帧）
    # 🔴 **按整帧分配，⛔ 不按秒**：24fps 下每段各自向帧边界取整，36 段会累积漂移
    #    （首版实测漂 +0.681s，把「画面＝音乐」这条自证打破了，也吃掉了比赛 180s 的余量）。
    #    正解：先算出总帧数 round(音乐×24)，再用**最大余数法**把它分给 36 镜，
    #    保证 Σ帧数 逐帧等于目标，⛔ 不靠"每段四舍五入然后祈祷"。
    FPS = 24
    total_frames = round(PIC_END * FPS)
    raw = [s["dur"] * FPS for s in shots]
    fr = [int(x) for x in raw]
    rem = total_frames - sum(fr)
    order = sorted(range(len(raw)), key=lambda i: -(raw[i] - fr[i]))
    for i in order[:rem]:
        fr[i] += 1
    assert sum(fr) == total_frames, (sum(fr), total_frames)
    print(f"帧分配：Σ{sum(fr)} 帧 = {sum(fr)/FPS:.3f}s（目标唱词区间 {PIC_END:.3f}s，"
          f"差 {sum(fr)/FPS-PIC_END:+.3f}s ＝ 半帧以内）")
    parts = []; cut_keys = []
    for s, n in zip(shots, fr):
        src = CLIPS / f"clip_{s['id']}__MiniMax-H3.mp4"
        dst = WORK / f"cut_{s['id']}.mp4"
        k = stamp("cut", sha_file(src), n)
        if not cached(dst, k):
            run(["ffmpeg", "-y", "-i", str(src), "-frames:v", str(n),
                 "-c:v", "libx264", "-crf", "14", "-preset", "medium",
                 "-r", "24", "-vsync", "cfr", "-pix_fmt", "yuv420p", "-an", str(dst)])
            seal(dst, k)
        cut_keys.append(k); parts.append(dst)
    lst = WORK / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")

    # ② 无字幕底片（2K 原生）
    base2k = WORK / "picture_2k_nosub.mp4"
    k_base = stamp("base2k", *cut_keys)
    if not cached(base2k, k_base):
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c:v", "libx264", "-crf", "14", "-preset", "medium",
             "-r", "24", "-pix_fmt", "yuv420p", "-an", str(base2k)])
        seal(base2k, k_base)
    d2 = dur(base2k)
    print(f"① 无字幕底片 {d2:.3f}s（唱词区间 {PIC_END:.3f}s，差 {d2-PIC_END:+.3f}s）")

    # ③ 烧字幕。审核档直接在 2K 原生上烧；只有定稿档才先升采样到 4K
    tag = "4k" if FOURK else "2k"
    sub4k = WORK / f"picture_{tag}_subbed.mp4"
    k_sub = stamp("sub", k_base, sha_file(ASS), tag)
    # 🔴 `pre` 必须在 if 外面定义 —— 命中缓存时也要拿它把参照片过一遍同样的滤镜
    pre = ("scale=3840:2160:flags=lanczos,unsharp=5:5:0.6:5:5:0.0," if FOURK else "")
    if not cached(sub4k, k_sub):
        vf = f"{pre}subtitles='{ASS}':fontsdir=/System/Library/Fonts"
        run(["ffmpeg", "-y", "-i", str(base2k), "-vf", vf,
             "-c:v", "libx264", "-crf", "16" if FOURK else "18", "-preset", "medium",
             "-r", "24", "-pix_fmt", "yuv420p", "-an", str(sub4k)])
        seal(sub4k, k_sub)
    print(f"② {'4K' if FOURK else '2K 原生'}烧字幕 {dur(sub4k):.3f}s")
    verify_namecards(base2k, sub4k, ASS, pre)

    # ④ credits 尾屏（接在音乐播完之后）
    cred = WORK / f"credits_{tag}.mp4"
    k_cred = stamp("cred", sha_file(CRED), CRED_SEC, tag)
    if not cached(cred, k_cred):
        cvf = ("" if FOURK else "scale=2560:1440:flags=lanczos,")
        run(["ffmpeg", "-y", "-loop", "1", "-t", f"{CRED_SEC}", "-i", str(CRED),
             "-vf", cvf + "fade=t=in:st=0:d=0.6,fade=t=out:st=%.2f:d=0.8,format=yuv420p" % (CRED_SEC - 0.8),
             "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-r", "24", str(cred)])
        seal(cred, k_cred)

    # ⑤ 拼接 ＋ 混音（音乐 + credits 段静音）
    lst2 = WORK / f"concat_final_{tag}.txt"
    lst2.write_text(f"file '{sub4k}'\nfile '{cred}'\n", encoding="utf-8")
    vid = WORK / f"final_video_{tag}.mp4"
    k_vid = stamp("vid", k_sub, k_cred)
    if not cached(vid, k_vid):
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst2),
             "-c", "copy", str(vid)])
        seal(vid, k_vid)
    master = OUT / ("逍遥游__4K母版__3840x2160.mp4" if FOURK
                    else "逍遥游__审核件__2560x1440.mp4")
    # 🔴 **原子写入**（）：先写 tmp → 校验完整 → rename。
    #    2026-08-27 实证：我在 the director 审片过程中直接覆盖了交付路径 ——
    #    ffmpeg 中途被 kill 会留下半截文件，正在看片的人当场播不下去。
    #    rename 在同一文件系统内是原子的 ⇒ 观看者要么看到旧的完整文件，要么看到新的完整文件。
    tmp = OUT / (master.stem + ".__writing__.mp4")
    run(["ffmpeg", "-y", "-i", str(vid), "-i", str(SONG),
         "-filter_complex", f"[1:a]apad=whole_dur={dur(vid):.3f}[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "256k", "-shortest", str(tmp)])
    if not ok_file(tmp):
        sys.exit("❌ 产出的 tmp 读不出时长 ⇒ 判定失败，⛔ 不覆盖现有交付件")
    tmp.replace(master)

    dv = dur(master)
    pr = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
              "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(master)])
    pa = run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
              "format=duration", "-of", "csv=p=0", str(master)])
    print(f"\n✅ {master}")
    print(f"   规格 {pr.stdout.strip()}　总长 {dv:.3f}s")
    apk = run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
               "stream=duration", "-of", "csv=p=0", str(master)])
    print(f"   自证：画面 {d2:.3f}s（＝唱词区间 {PIC_END:.3f}s）＋ credits {CRED_SEC}s ＝ {dv:.3f}s")
    print(f"   音乐 {MUSIC:.3f}s **完整播完**（尾奏 {MUSIC-PIC_END:.2f}s 在 credits 底下播），"
          f"⛔ 未截断；音轨实测 {apk.stdout.strip()}s")
    ok = dv <= LIMIT
    print(f"   比赛硬闸 ≤{LIMIT}s：{'✅ 通过' if ok else '❌ 超限'}（余量 {LIMIT-dv:+.2f}s）")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
