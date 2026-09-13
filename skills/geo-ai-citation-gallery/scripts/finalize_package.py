#!/usr/bin/env python3
"""
收尾：校验统一交付包，删除 _过程/，确认根目录干净。

统一技能后：
  - 客户主交付 = gallery/index.html + gallery/images/（晨光陶瓷五 Tab）
  - 文案留档 = 文案/ + _机器可读/top.json
  - 偏好分析.md 为可选内部/归档（有则校验非空；无则警告不失败）
  - 禁止把绿头 KPI HTML 当主交付

用法：
  python scripts/finalize_package.py --package <包路径>
  python scripts/finalize_package.py --package <包路径> --keep-process
  python scripts/finalize_package.py --package <包路径> --require-preference
"""
import argparse
import json
import os
import re
import shutil

REQUIRED_FILES = ("README.md", "视频索引.md")
REQUIRED_DIRS = ("文案", "_机器可读")
BASE_ALLOWED = {
    "README.md",
    "偏好分析.md",
    "视频索引.md",
    "文案",
    "_机器可读",
    "gallery",
    "images",
    "index.html",
    "shots",
    "work",
}


def _safe_plat(platform):
    return re.sub(r"[^\w\u4e00-\u9fff]+", "_", platform or "").strip("_") or "platform"


def _find_gallery(pkg):
    """Return (html_path, images_dir) or (None, None). Prefer gallery/."""
    candidates = [
        (os.path.join(pkg, "gallery", "index.html"), os.path.join(pkg, "gallery", "images")),
        (os.path.join(pkg, "index.html"), os.path.join(pkg, "images")),
    ]
    for html, images in candidates:
        if os.path.isfile(html) and os.path.getsize(html) >= 200:
            return html, images
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True)
    ap.add_argument("--keep-process", action="store_true")
    ap.add_argument("--allow-empty-scripts", action="store_true")
    ap.add_argument(
        "--require-preference",
        action="store_true",
        help="将 偏好分析.md 视为硬性必填（默认可选归档）",
    )
    args = ap.parse_args()

    pkg = os.path.abspath(args.package)
    if not os.path.isdir(pkg):
        raise SystemExit(f"包不存在: {pkg}")

    errors = []
    warnings = []

    for name in REQUIRED_FILES:
        path = os.path.join(pkg, name)
        if not os.path.isfile(path) or os.path.getsize(path) < 20:
            errors.append(f"缺少或过短: {name}")
    for name in REQUIRED_DIRS:
        if not os.path.isdir(os.path.join(pkg, name)):
            errors.append(f"缺少目录: {name}/")

    pref = os.path.join(pkg, "偏好分析.md")
    if os.path.isfile(pref):
        if os.path.getsize(pref) < 40:
            errors.append("偏好分析.md 过短（空壳）")
    elif args.require_preference:
        errors.append("缺少 偏好分析.md（--require-preference）")
    else:
        warnings.append("无 偏好分析.md（可选归档；偏好洞察应已写入画廊 Tab）")

    html, images_dir = _find_gallery(pkg)
    if not html:
        errors.append(
            "缺少客户主交付画廊：需要 gallery/index.html（推荐）或根目录 index.html"
        )
    else:
        if images_dir and not os.path.isdir(images_dir):
            warnings.append(f"画廊 HTML 存在但缺 images/：{os.path.relpath(images_dir, pkg)}")
        # 拒绝把绿头 KPI 壳误当主交付：粗检晨光/五 Tab 信号
        try:
            with open(html, encoding="utf-8", errors="ignore") as f:
                head = f.read(8000)
            if "kpi-row" in head and "晨光" not in head and "cz-porcelain" not in head and "tab-tray" not in head:
                warnings.append(
                    "画廊 HTML 看起来像绿头 KPI 壳；客户主交付应套 assets/template.html（晨光陶瓷）"
                )
        except OSError:
            pass

    top_path = os.path.join(pkg, "_机器可读", "top.json")
    meta = {}
    videos = []
    if not os.path.isfile(top_path):
        errors.append("缺少 _机器可读/top.json")
    else:
        with open(top_path, encoding="utf-8") as f:
            doc = json.load(f)
        meta = doc.get("meta") or {}
        videos = doc.get("videos") or []
        if not videos:
            errors.append("top.json 中 videos 为空")

    scope_word = meta.get("scope_word") or "仅抖音"
    plat_dir = os.path.join(pkg, "平台偏好")
    if scope_word == "全平台":
        platforms = meta.get("platforms") or []
        if not os.path.isdir(plat_dir):
            errors.append("全平台模式缺少目录: 平台偏好/")
        else:
            for p in platforms:
                candidates = [
                    os.path.join(plat_dir, f"{p}.md"),
                    os.path.join(plat_dir, f"{_safe_plat(p)}.md"),
                ]
                if not any(os.path.isfile(c) and os.path.getsize(c) >= 40 for c in candidates):
                    errors.append(f"全平台模式缺少平台短文: 平台偏好/{p}.md")
    else:
        if os.path.isdir(plat_dir):
            errors.append("仅抖音模式不应存在 平台偏好/（请删除或改用全平台模式）")

    ok_paths = []
    missing_any = []
    missing_ok = []
    for v in videos:
        rel = v.get("script_path") or ""
        st = v.get("fetch_status") or "pending"
        full = os.path.join(pkg, rel) if rel else ""
        if not (full and os.path.isfile(full) and os.path.getsize(full) > 40):
            missing_any.append(rel or v.get("title") or "?")
        if st == "ok":
            if full and os.path.isfile(full) and os.path.getsize(full) > 200:
                ok_paths.append(rel)
            else:
                missing_ok.append(rel or v.get("title") or "?")
    if missing_any:
        errors.append(
            f"存在空号（Top 序号无对应 md，含失败占位）: {len(missing_any)} 条"
            f"（例: {missing_any[0]}）。请重跑 fetch_video_scripts.py --verify"
        )
    if missing_ok:
        errors.append(f"fetch_status=ok 但文案缺失/过短: {len(missing_ok)} 条（例: {missing_ok[0]}）")
    if not args.allow_empty_scripts and not ok_paths and videos:
        warnings.append(f"没有一条 fetch_status=ok 的文案（共 {len(videos)} 条清单）")

    for w in warnings:
        print(f"警告: {w}")

    if errors:
        print("收尾失败，请先补齐交付物：")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)

    process_dir = os.path.join(pkg, "_过程")
    if os.path.isdir(process_dir):
        if args.keep_process:
            print(f"保留过程目录（--keep-process）: {process_dir}")
        else:
            shutil.rmtree(process_dir)
            print("已删除: _过程/")

    allowed = set(BASE_ALLOWED)
    if scope_word == "全平台":
        allowed.add("平台偏好")

    extras = [
        name for name in os.listdir(pkg)
        if not name.startswith(".") and name not in allowed
    ]
    if extras:
        print("警告: 根目录仍有规范外文件/目录：")
        for name in extras:
            print(f"  - {name}")
        raise SystemExit(2)

    if html and os.path.basename(os.path.dirname(html)) == "gallery":
        gal = "gallery/index.html + gallery/images/"
    else:
        gal = "index.html + images/"

    pref_note = " / 偏好分析.md" if os.path.isfile(pref) else ""
    plat_note = " / 平台偏好/" if scope_word == "全平台" else ""
    print(
        f"交付完成。客户主交付: {gal} ｜ 归档: README.md / 视频索引.md / 文案/ / _机器可读/{pref_note}{plat_note}"
    )
    print(
        f"包: {os.path.basename(pkg)} ｜ 平台范围: {scope_word} ｜ "
        f"清单 {len(videos)} 条 ｜ 文案成功 {len(ok_paths)} 条"
    )


if __name__ == "__main__":
    main()
