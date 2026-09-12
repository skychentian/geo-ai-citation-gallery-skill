/**
 * 浏览器控制台 / 注入示例：在抖音等公开分享页收集图片 CDN / video URL，
 * 再打本机 capture_server（127.0.0.1:8765）。
 *
 * 用法（每条公开页打开后）：
 *   1. 把下面 RANK / KIND 改成当前样本
 *   2. 整段贴进控制台运行，或由 Antigravity /browser / 无头脚本等价执行
 *   3. 本机已启动：CAPTURE_PROJECT=... python capture_server.py
 *
 * kind:
 *   - 图文 → "image"（多张图床 URL）
 *   - 口播 → "video"（至少一条可下载 mp4 URL；可选 poster 封面）
 *
 * 说明：以下是通用 DOM / performance 提示，勿写死易失效的私有 API。
 * 成品图由本机脚本下载，不是浏览器截屏文件。
 */
(async function pageHookExample() {
  const RANK = 1; // ← 改成清单排名
  const KIND = "image"; // "image" | "video"
  const HOST = "http://127.0.0.1:8765";

  const CDN_HINT =
    /douyincdn|byteicdn|byteimg|douyinpic|snssdk|amemv|ixigua|pstatp|tos-cn|obj\/|\/aweme\/|\/obj\//i;

  function uniq(arr) {
    return [...new Set(arr.filter(Boolean))];
  }

  function abs(u) {
    try {
      return new URL(u, location.href).href;
    } catch {
      return null;
    }
  }

  function fromCssBg(el) {
    const bg = getComputedStyle(el).backgroundImage || "";
    const m = bg.match(/url\(["']?([^"')]+)["']?\)/i);
    return m ? abs(m[1]) : null;
  }

  // 1) <img src / data-src / srcset>
  const fromImgs = [...document.querySelectorAll("img")].flatMap((img) => {
    const out = [];
    for (const attr of ["src", "data-src", "data-original", "data-url"]) {
      if (img.getAttribute(attr)) out.push(abs(img.getAttribute(attr)));
    }
    const ss = img.getAttribute("srcset") || "";
    ss.split(",").forEach((part) => {
      const u = part.trim().split(/\s+/)[0];
      if (u) out.push(abs(u));
    });
    return out;
  });

  // 2) 背景图
  const fromBg = [...document.querySelectorAll("*")]
    .slice(0, 800)
    .map(fromCssBg)
    .filter(Boolean);

  // 3) <video src> / <source> / poster
  const videos = [...document.querySelectorAll("video")];
  const fromVideo = videos.flatMap((v) => {
    const out = [];
    if (v.currentSrc) out.push(abs(v.currentSrc));
    if (v.src) out.push(abs(v.src));
    v.querySelectorAll("source").forEach((s) => {
      if (s.src) out.push(abs(s.src));
    });
    return out;
  });
  const poster =
    videos.map((v) => v.getAttribute("poster")).map(abs).find(Boolean) || null;

  // 4) performance 资源（常能看到 CDN）
  const fromPerf = performance
    .getEntriesByType("resource")
    .map((e) => e.name)
    .filter((u) => CDN_HINT.test(u) || /\.(jpe?g|png|webp|mp4|m3u8)(\?|$)/i.test(u));

  // 5) 粗滤：像媒体 CDN 的 http(s) URL
  let candidates = uniq([...fromImgs, ...fromBg, ...fromVideo, ...fromPerf]).filter(
    (u) => /^https?:\/\//i.test(u) && (CDN_HINT.test(u) || /\.(jpe?g|png|webp|mp4)(\?|$)/i.test(u))
  );

  // 图文优先图片；口播优先 mp4 / 视频后缀
  if (KIND === "image") {
    candidates = candidates.filter((u) => !/\.mp4(\?|$)/i.test(u) && !/\.m3u8(\?|$)/i.test(u));
  } else {
    const vids = candidates.filter((u) => /\.mp4(\?|$)/i.test(u) || /mime_type=video/i.test(u));
    candidates = vids.length ? vids : candidates;
  }

  const meta = {
    kind: KIND,
    page: location.href,
    title: document.title || "",
    poster: KIND === "video" ? poster : undefined,
  };

  // urlsafe base64（与 capture_server /meta 一致）
  const json = JSON.stringify(meta);
  const b64 = btoa(unescape(encodeURIComponent(json)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");

  async function hit(path) {
    const r = await fetch(HOST + path);
    if (!r.ok) throw new Error(path + " -> " + r.status);
    return r.text();
  }

  console.log("[page_hook] candidates", candidates.length, candidates.slice(0, 8));
  await hit(`/meta?rank=${RANK}&d=${b64}`);
  for (const u of candidates) {
    await hit(`/media?rank=${RANK}&u=${encodeURIComponent(u)}`);
  }
  const result = await hit(`/finish?rank=${RANK}`);
  console.log("[page_hook] finish", result);
  return { rank: RANK, kind: KIND, count: candidates.length, result };
})();
