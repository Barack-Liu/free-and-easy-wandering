#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xyy_t1_2_song.py —— 《逍遥游》CP2：3 种曲风候选歌。

规约：
  · 唱词**程序化取自** T1_1-Lyrics/lyrics_xiaoyaoyou_r3.json，⛔ 不手抄
    （：手抄迟早漂）
  · 替身表（pronunciation_fix 里 处置=="替身"）在**这一步**施加到 payload；
    字幕层用 canon 字，两者由同一函数派生
  · 🗣 结构必须是 **1 前奏 ＋ 4 幕 ＋ 3 间奏 ＋ 1 尾奏**，且要在 API payload 里体现
  ·  lyrics 只放**裸结构标签 ＋ 真唱词**，
    ⛔ 不写括号舞台指示（会被唱成英文）；纯器乐段靠 `prompt` 描述
  ·  3 首必须是 **3 种真曲风**，
    **至少一席摇滚**，曲风写进文件名
  ·  3 首摊平在同一层，中间件进 _work/
  · 时长目标 ~165s（成片 ≤180s − credits ~10s）；膨胀源是「句尾可延长音」这类唱法自由度
    ⇒ prompt 明写 syllabic / 不拖长音 / 速度稳定

RUN:
  python3 xyy_t1_2_song.py --build          # 只出 payload JSON ＋ 主文档窄版块
  python3 xyy_t1_2_song.py --gen [--takes 1]  # 提交生成
"""
import argparse, hashlib, json, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import requests

ROOT = Path(os.environ.get("XYY_ROOT", "."))
sys.path.insert(0, str(ROOT / "_Shared/Program_Scripts"))
import auth as gmi_auth

FILM = ROOT / os.environ.get("XYY_FILM", "film")
LYR = FILM / "T1_1-Lyrics/lyrics_xiaoyaoyou_r3.json"
OUT = FILM / "T1_2-Song"
WORK = OUT / "_work"
import os
MODEL = os.environ.get("XYY_MUSIC_MODEL", "minimax-music-3.0")   # 可换 minimax-music-2.5 做代差对照
_CLAIMED = set()   # 本进程已认领的 request_id，⛔ 防两个 take 认领同一条
URL = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey"

# ── 三种**真曲风**（⛔ 不是参数微调）· 至少一席摇滚 ───────────────────────
#    差异靠**配器织体**，⛔ 不靠拉慢速度（拉慢会冲破时长窗）
#
# 🔴 2026-08-26 r1 实测：六 take 全部 227–295s（目标 ≤171s）。把最短那条（227.8s）用
#    mlx-whisper 拆开看：**唱词只占 98.8s，器乐/空白占 129.0s**，光前奏就 30.0s ——
#    而我写的是「Instrumental intro of about eight seconds」。
#    ⇒ 膨胀源是**器乐段**，⛔ 不是唱词字数、⛔ 不是 BPM。r2 的收紧只动器乐段：
#      把「about N seconds」改成写死的秒数，并明说**除这五段之外没有别的器乐段**。
TIGHT = (" The finished track runs two minutes and fifty seconds in total and then stops. The only "
         "instrumental passages in the whole song are the five named above; everywhere else the "
         "voice is singing. The singer comes back in on the very next bar after each interlude, and "
         "no bar of any verse is left without words.")

STYLES = {
    "guofeng-rock": (
        "Chinese guofeng rock ballad, male lead vocal in Mandarin. Distorted electric guitar power "
        "chords and a driving rock drum kit carry the song; an erhu and a bamboo dizi flute trade "
        "the melodic hook over them; electric bass locked to the kick. Tempo steady at about 96 BPM "
        "throughout. A four-second instrumental introduction on solo erhu. Three four-second "
        "instrumental interludes, each a short guitar-and-erhu unison riff. The last chorus is the "
        "loudest point of the song. A six-second instrumental ending that thins back down to the "
        "solo erhu. The singing is syllabic and forward-moving, one note per word, with no long "
        "held notes and no vocal runs."),
    "epic-orchestral": (
        "Epic Chinese orchestral song, male lead vocal in Mandarin. Large taiko-style frame drums, "
        "low strings and bianzhong bronze bells underpin a soaring string section; a guqin and a "
        "xiao vertical flute answer the vocal line. Tempo steady at about 88 BPM throughout. A "
        "four-second instrumental introduction on lone bronze bells. Three four-second instrumental "
        "interludes carried by the string section. The last chorus adds a wordless male choir "
        "underneath the lead vocal. A six-second instrumental ending that decays into a single "
        "struck bell. The singing is syllabic and forward-moving, one note per word, with no long "
        "held notes and no vocal runs."),
    # 🔴 2026-08-26 替补：`epic-orchestral` **结构性出局** —— 它 5 条 take 的唱词时长
    #    149.4–171.1s，即使把器乐段裁到规格（4+3×4+6＝22s）仍 ≥177s，⛔ 进不了 171s 窗。
    #    换成**唱得快、吐字密**的国风说唱：唱词时长本身就短，是直接冲着约束去的。
    "guofeng-rap": (
        "Chinese guofeng hip-hop track, male rapper in Mandarin. A hard boom-bap drum break and a "
        "deep sub bass carry the track; a pipa riff and a sampled xiao flute hook sit on top; light "
        "record crackle. Tempo steady at about 88 BPM with a double-time flow, so the words come "
        "fast. A four-second instrumental introduction on solo pipa. Three four-second instrumental "
        "interludes on the pipa riff alone. The last chorus is half-sung and doubled an octave up. "
        "A six-second instrumental ending that drops to the bare drum break. The delivery is rapid, "
        "percussive and strictly syllabic, one syllable per beat subdivision, with no held notes, "
        "no melisma and no sung tails."),
    "cyber-electronic": (
        "Cyberpunk electronic Chinese song, male lead vocal in Mandarin. A deep analogue synth bass "
        "pulse and a crisp programmed trap-influenced drum pattern drive the track; sampled guzheng "
        "plucks and a breathy xiao flute float above a wide pad; occasional granular vocal chops. "
        "Tempo steady at about 104 BPM throughout. A four-second instrumental introduction on a "
        "rising synth pulse. Three four-second instrumental interludes on a filtered synth "
        "arpeggio. The last chorus opens the filter fully and adds a sub-bass drop. A six-second "
        "instrumental ending that filters everything down to the synth pulse. The singing is "
        "syllabic and forward-moving, one note per word, with no long held notes and no vocal "
        "runs."),
}

# ── 演唱结构：🗣 1 前奏 ＋ 4 幕 ＋ 3 间奏 ＋ 1 尾奏 ──────────────────────
#    ⚠️ 间奏**只放在幕与幕之间**（3 处），幕内 ⛔ 不设间奏。
STRUCT = [
    ("[Intro]", None),
    ("[Verse]", "I"),
    ("[Interlude]", None),
    ("[Verse]", "II"),
    ("[Interlude]", None),
    ("[Verse]", "III"),
    ("[Interlude]", None),
    ("[Verse]", "IV"),
    ("[Outro]", None),
]
# 副歌行（原文「至人无己，神人无功，圣人无名」）在幕内出现时改挂 [Chorus] 标签
REFRAIN = "至人无己，神人无功，圣人无名"

# 🔴 2026-08-26 网页 playground 实读：GMI 控制台的 minimax-music-3.0 页面**参数与 API 完全一致**
#    （Style Prompt / Lyrics / Sample Rate / Bitrate / Output Format ＋ 一个 Lyrics Optimizer），
#    ⛔ **没有任何时长控件**。⇒ 走浏览器拿不到「更丰富的配置」，这条路对本模型是空的。
#    但目录里模型自己的 tag 说明写着支持 **[Verse] [Chorus] [Bridge] [Intro] [Outro]**，
#    ⛔ **没有 [Interlude]** —— 而 r1/r2 我一直在用它。未知标签很可能就是模型自行加长器乐段的口子。
#    ⇒ TAGSET 用来做对照实验，判据是**成品时长**，⛔ 不是「prompt 里写没写」。
TAGSET = {
    # 现行（对照组）：用 [Interlude]，模型词表里没有这个标签
    "cur":       {"intro": "[Intro]", "inter": "[Interlude]", "outro": "[Outro]"},
    # 只用模型明确支持的标签，间奏改用 [Bridge]
    "bridge":    {"intro": "[Intro]", "inter": "[Bridge]",    "outro": "[Outro]"},
    # 器乐段完全不给标签（靠 prompt 描述），幕之间直接换 [Verse]
    "notag":     {"intro": None,      "inter": None,          "outro": None},
    # 保留首尾标签、去掉幕间标签
    "endsonly":  {"intro": "[Intro]", "inter": None,          "outro": "[Outro]"},
}
TAGS = TAGSET[os.environ.get("XYY_TAGSET", "cur")]


def load():
    return json.loads(LYR.read_text(encoding="utf-8"))


def subs_map(d):
    return {f["char"]: f["替代"] for f in d["pronunciation_fix"] if f["处置"] == "替身"}


def build_lyrics(d):
    """canon 唱词 → payload 字面（施加替身表、去标点、拆行、挂结构标签）。"""
    sub = subs_map(d)
    acts = {a["id"]: a["lines"] for a in d["acts"]}
    out, applied = [], []
    for tag, act_id in STRUCT:
        if act_id is None:
            real = {"[Intro]": TAGS["intro"], "[Interlude]": TAGS["inter"],
                    "[Outro]": TAGS["outro"]}[tag]
            if real:
                out.append(real)                 # 纯器乐段：只放裸标签，⛔ 不放任何词
            continue
        cur = None                      # 本幕内当前挂着的标签
        for ln in acts[act_id]:
            t = ln
            for k, v in sub.items():
                if k in t:
                    applied.append((act_id, k, v, ln))
                    t = t.replace(k, v)
            t = re.sub(r"[，。；：、？！]", " ", t)
            t = re.sub(r"\s+", " ", t).strip()
            # 副歌行改挂 [Chorus]；⛔ 标签一段只出现一次，不是每行一个
            want = "[Chorus]" if t.startswith("至人无己") else tag
            if want != cur:
                out.append(want)
                cur = want
            out.append(t)
    return "\n".join(out), applied


def payload_body(d, style_key):
    """🔴 唯一的 payload 构造点 —— 文档渲染与实际提交**共用它**，
    否则会出现「文档说 A、实际发 B」（ 配套铁律）。"""
    lyrics, _ = build_lyrics(d)
    return {"lyrics": lyrics, "prompt": STYLES[style_key] + TIGHT,
            "sample_rate": 44100, "bitrate": 256000, "format": "mp3"}


def cmd_build():
    d = load()
    OUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(exist_ok=True)
    lyrics, applied = build_lyrics(d)
    n_han = len(re.findall(r"[一-鿿]", lyrics))
    print(f"payload 唱词纯汉字 {n_han} 字")
    print(f"结构标签：{[l for l in lyrics.split(chr(10)) if l.startswith('[')]}")
    print(f"替身实际命中 {len(applied)} 处：")
    for a in applied:
        print(f"   幕{a[0]}  {a[1]}→{a[2]}   「{a[3]}」")
    for k in STYLES:
        p = payload_body(d, k)
        f = WORK / f"payload__{k}.json"
        f.write_text(json.dumps({"model": MODEL, "payload": p}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        print(f"  ✅ {f.name}  sha256={hashlib.sha256(json.dumps(p, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]}")
    (WORK / "_lyrics_payload.txt").write_text(lyrics, encoding="utf-8")
    print(f"\n—— payload lyrics 字面 ——\n{lyrics}")


def claim_by_fingerprint(payload, label, tries=8, wait=30):
    """POST 超时后，按 **payload 内容指纹**（lyrics ＋ prompt 逐字相同）去列表里认领已建单的那条。
    ⚠️ 公司号是共享账号，列表里混着同事的请求 ⇒ ⛔ 必须按指纹过滤，不能按「最近 N 条」取。"""
    KEY, _ = gmi_auth.get_key()
    H2 = {"Authorization": f"Bearer {KEY}"}
    for i in range(tries):
        time.sleep(5 if i == 0 else wait)
        try:
            items = requests.get(f"{URL}/requests?limit=30", headers=H2, timeout=240).json()["requests"]
        except Exception:
            continue
        for it in items:
            if it.get("model") != MODEL or it["request_id"] in _CLAIMED:
                continue
            pl = it.get("payload") or {}
            if pl.get("lyrics") == payload["lyrics"] and pl.get("prompt") == payload["prompt"]:
                _CLAIMED.add(it["request_id"])
                print(f"  [{label}] 指纹认领 rid={it['request_id']}", flush=True)
                return it["request_id"]
    return None


def submit_poll(payload, label, max_min=20):
    KEY, _ = gmi_auth.get_key()
    H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    # 🔴 GMI 网关对 /requests 的 POST 有硬超时；超时/504 时**请求已经在服务端建单并会跑完**。
    #    ⛔ 绝不重试提交 —— 那是重复建单、重复计费。正解＝按内容指纹认领。
    rid = None
    try:
        r = requests.post(f"{URL}/requests", headers=H,
                          json={"model": MODEL, "payload": payload}, timeout=90)
        if r.status_code < 400:
            rid = r.json().get("request_id") or r.json().get("id")
        elif r.status_code != 504:
            return None, f"HTTP{r.status_code}:{r.text[:250]}"
    except requests.exceptions.RequestException as e:
        print(f"  [{label}] 提交端 {type(e).__name__} ⇒ 转指纹认领（⛔ 不重复提交）", flush=True)
    if not rid:
        rid = claim_by_fingerprint(payload, label)
        if not rid:
            return None, "提交端超时且指纹认领不到（可能真的没建单）"
    print(f"  [{label}] rid={rid}", flush=True)
    deadline = time.time() + max_min * 60
    while time.time() < deadline:
        time.sleep(10)
        try:
            rr = requests.get(f"{URL}/requests/{rid}", headers=H, timeout=90).json()
        except Exception:
            continue
        st = rr.get("status")
        if st == "success":
            o = rr.get("outcome") or {}
            u = (o.get("audio_url") or o.get("media_urls") or o.get("audio_urls"))
            if isinstance(u, list):
                u = u[0]["url"] if isinstance(u[0], dict) else u[0]
            if not u:
                return None, "success-no-url:" + json.dumps(o)[:250]
            return requests.get(u, timeout=900).content, rid
        if st in ("failed", "error"):
            return None, f"{st}|{json.dumps(rr.get('outcome') or {})[:250]}"
    return None, "poll-timeout"


def cmd_gen(takes):
    d = load()
    OUT.mkdir(parents=True, exist_ok=True); WORK.mkdir(exist_ok=True)
    MANP = OUT / "manifest_T1_2.json"
    man = json.load(open(MANP)) if MANP.exists() else {}
    only = os.environ.get("XYY_STYLES")            # 对照实验时只跑一种曲风，隔离变量
    ks = [k for k in STYLES if not only or k in only.split(",")]
    jobs = [(k, t) for k in ks for t in range(1, takes + 1)]

    def one(job):
        k, t = job
        label = f"{k}_{os.environ.get('XYY_TAGSET','cur')}_t{t}"
        tg = os.environ.get("XYY_TAGSET", "cur")
        sfx = "" if tg == "cur" else f"__tag-{tg}"
        # 🔴 raw take 直接落 _work/raw_takes/，⛔ 不写进交付目录顶层。
        #    2026-08-26 实证：后台还在补掷 take 时我 push 了一次 Drive，
        #    `T1_2-Song/*.mp3` 这个 glob 把两条**中间件 raw take** 一起传给了 the director。
        #    ⇒ 交付目录必须**只装交付物**，中间件从一开始就不该出现在那里
        #    （⛔ 不是"传之前记得过滤" —— 那是靠记性，靠不住）。
        RAWDIR = OUT / "_work/raw_takes"
        RAWDIR.mkdir(parents=True, exist_ok=True)
        dst = RAWDIR / f"逍遥游__{k}{sfx}__t{t}__{MODEL}.mp3"
        if dst.exists():
            print(f"  [{label}] 已存在，跳过"); return
        data, info = submit_poll(payload_body(d, k), label)
        if data is None:
            print(f"  ❌ [{label}] {info}"); man[label] = {"ok": False, "err": str(info)}
        else:
            dst.write_bytes(data)
            pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(dst)], capture_output=True, text=True)
            dur = float((pr.stdout or "0").strip() or 0)
            man[label] = {"ok": True, "style": k, "take": t, "mp3": str(dst),
                          "dur": round(dur, 2), "rid": info, "usd": 0.15,
                          "in_window": 150 <= dur <= 171}
            print(f"  ✅ [{label}] {dur:.1f}s {'✅窗内' if man[label]['in_window'] else '⚠️出窗(目标150-171s)'}")
        json.dump(man, open(MANP, "w"), ensure_ascii=False, indent=1)

    with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as ex:
        list(ex.map(one, jobs))
    ok = [v for v in man.values() if v.get("ok")]
    print(f"\n完成 {len(ok)}/{len(jobs)}　窗内 {sum(1 for v in ok if v.get('in_window'))}　共 ${round(0.15*len(ok),2)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--gen", action="store_true")
    ap.add_argument("--takes", type=int, default=1)
    a = ap.parse_args()
    if a.build:
        cmd_build()
    if a.gen:
        cmd_gen(a.takes)
    if not (a.build or a.gen):
        ap.print_help()
