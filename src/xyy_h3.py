#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xyy_h3.py —— 《逍遥游》的 MiniMax-H3 公共客户端（提交 / 轮询 / 上传 / 抽帧 / 记账）。

为什么抽出来：T2_1（角色）、T3_2（关键帧）、T4_1（clip）三步用的是**同一个端点、同一套坑**，
三份复制迟早漂（改一处忘两处）。⛔ 别再往别的脚本里复制 submit_poll。

H3 硬约束（来自 GMI 目录 parameters 原文，⛔ 违反会被端上拒绝或静默降级）：
  · frame-based（first_frame_image / last_frame_image）与 reference_images **不能同请求混用**
  · i2v 时 `ratio` 无效（画幅跟随输入图）⇒ 16:9 必须靠关键帧本身锁死
  · `duration`（4–15 整秒）与 `resolution`（768P / 2K）**都是必填**
  · 2K 实返 2560×1440 / 24fps；duration=N 实返约 N+0.46s（剪辑按 ffprobe 实测对齐，⛔ 别按参数算）
  · 图必须走 upload-url → PUT(Content-Type 逐字 image/png) → public_url，⛔ 禁 raw base64
"""
import hashlib, json, subprocess, sys, time
import os
from pathlib import Path

import requests

ROOT = Path(os.environ.get("XYY_ROOT", "."))
sys.path.insert(0, str(ROOT / "_Shared/Program_Scripts"))
import auth as gmi_auth

URL = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey"
MODEL = "MiniMax-H3"
USD_PER_S = {"2K": 0.13, "768P": 0.08}

_KEY, ACCT = gmi_auth.get_key()
H = {"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"}
_ucache = {}


def upload(p: Path) -> str:
    """内容哈希做缓存 key（⛔ 不用 mtime：同一张图重跑不该重传）。"""
    h = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    if h in _ucache:
        return _ucache[h]
    r = requests.post(f"{URL}/upload-url", headers=H,
                      json={"file_name": p.name, "file_type": "png"}, timeout=90)
    r.raise_for_status(); j = r.json()
    pr = requests.put(j["upload_url"], data=p.read_bytes(),
                      headers={"Content-Type": "image/png"}, timeout=900)
    if pr.status_code >= 400:
        raise RuntimeError(f"PUT {pr.status_code}: {pr.text[:200]}")
    u = j.get("public_url") or j["upload_url"].split("?")[0]
    _ucache[h] = u
    return u


def submit_poll(payload, label, max_min=35):
    """返回 (mp4_bytes, request_id) 或 (None, 错误串)。"""
    assert not ({"first_frame_image", "last_frame_image"} & payload.keys()
                and "reference_images" in payload), \
        f"[{label}] 首/尾帧 与 reference_images ⛔ 不能同请求混用（H3 硬约束）"
    assert payload.get("duration") and payload.get("resolution"), \
        f"[{label}] duration / resolution 都是必填"
    r = requests.post(f"{URL}/requests", headers=H,
                      json={"model": MODEL, "payload": payload}, timeout=180)
    if r.status_code >= 400:
        return None, f"HTTP{r.status_code}:{r.text[:250]}"
    j = r.json(); rid = j.get("request_id") or j.get("id")
    if not rid:
        return None, "no-request-id:" + json.dumps(j)[:200]
    print(f"  [{label}] rid={rid}", flush=True)
    deadline = time.time() + max_min * 60
    while time.time() < deadline:
        time.sleep(15)
        try:
            rr = requests.get(f"{URL}/requests/{rid}", headers=H, timeout=90).json()
        except Exception:
            continue
        st = rr.get("status")
        if st == "success":
            o = rr.get("outcome") or {}
            mu = o.get("media_urls") or o.get("video_urls") or o.get("video_url")
            if not mu:
                return None, "success-no-url:" + json.dumps(o)[:250]
            u = mu if isinstance(mu, str) else (mu[0]["url"] if isinstance(mu[0], dict) else mu[0])
            return requests.get(u, timeout=1800).content, rid
        if st in ("failed", "error"):
            return None, f"{st}|{json.dumps(rr.get('outcome') or {})[:250]}"
    return None, "poll-timeout"


def frame(mp4: Path, png: Path, n=0):
    """抽第 n 帧。⛔ 判据是「ffprobe 读得出」而不是「文件存在」——
    截断的 mp4 会让 [ -f ] 放行，下游才炸（[redacted] 260826 踩过）。"""
    subprocess.run(["ffmpeg", "-y", "-i", str(mp4), "-vf", f"select=eq(n\\,{n})",
                    "-vframes", "1", str(png)], capture_output=True)
    return png.exists() and png.stat().st_size > 0


def probe(mp4: Path):
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
                         "-show_entries", "format=duration", "-of", "json", str(mp4)],
                        capture_output=True, text=True)
    try:
        d = json.loads(pr.stdout or "{}")
        s = (d.get("streams") or [{}])[0]
        return {"w": s.get("width"), "h": s.get("height"), "fps": s.get("r_frame_rate"),
                "dur": float((d.get("format") or {}).get("duration") or 0)}
    except Exception:
        return {}


def cost(seconds, resolution="2K"):
    return round(seconds * USD_PER_S[resolution], 4)
