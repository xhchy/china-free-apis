#!/usr/bin/env python3
"""
零依赖 API 探活脚本 — 检查 apis.json 里的所有接口是否还活着。

用法:
    python check.py
    python check.py --json
    python check.py --timeout 5
    python check.py --file my-apis.json
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

USER_AGENT = "ChinaFreeAPIs/1.0 (health check; +https://github.com/xhchy/china-free-apis)"


def check_one(item, timeout):
    """检查单个接口，返回结果字典。"""
    name = item.get("name", "?")
    url = item.get("url", "")
    started = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
            # 只读前 1KB，避免下载大文件
            resp.read(1024)
        elapsed = int((time.time() - started) * 1000)
        return {
            "name": name,
            "url": url,
            "status": status,
            "ms": elapsed,
            "ok": 200 <= status < 400,
            "error": "",
        }
    except urllib.error.HTTPError as e:
        return {"name": name, "url": url, "status": e.code, "ms": int((time.time() - started) * 1000),
                "ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"name": name, "url": url, "status": 0, "ms": int((time.time() - started) * 1000),
                "ok": False, "error": type(e).__name__ + ": " + str(e)[:60]}


def main():
    ap = argparse.ArgumentParser(description="检查免费 API 清单的存活状态")
    ap.add_argument("--file", default="apis.json", help="接口清单文件（默认 apis.json）")
    ap.add_argument("--timeout", type=int, default=8, help="单个请求超时秒数（默认 8）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 格式")
    ap.add_argument("--workers", type=int, default=4, help="并发数（默认 4，别太大，对公益站友好）")
    args = ap.parse_args()

    path = Path(__file__).parent / args.file
    if not path.exists():
        print(f"找不到 {path}", file=sys.stderr)
        sys.exit(2)
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"清单 JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(2)

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check_one, item, args.timeout): item for item in items}
        for f in as_completed(futures):
            results.append(f.result())
    # 保持清单原顺序
    order = {item["url"]: i for i, item in enumerate(items)}
    results.sort(key=lambda r: order.get(r["url"], 999))

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"正在检查 {len(items)} 个接口...\n")
        for r in results:
            mark = "✅" if r["ok"] else "❌"
            status = str(r["status"]) if r["status"] else r["error"].split(":")[0]
            print(f"{mark} {r['name']:<28} {status:<12} {r['ms']:>5}ms")
        alive = sum(1 for r in results if r["ok"])
        avg = int(sum(r["ms"] for r in results) / len(results)) if results else 0
        print(f"\n存活 {alive}/{len(results)}  |  平均响应 {avg}ms")

    # 有接口挂掉时返回 1，方便 CI 报警
    sys.exit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    main()
