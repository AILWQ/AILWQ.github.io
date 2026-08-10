#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Google Scholar 个人主页抓取引用统计，写入 scholar-stats.json。

设计要点：
- 仅当数值确实变化时才写文件（避免每天产生无意义提交）。
- 抓取或解析失败时直接退出、不写文件（保留上一次的有效值，绝不破坏网站）。
- 输出格式与 index.html 读取的 scholar-stats.json 一致：
    {"citations": int, "hIndex": int, "i10Index": int, "source": "google-scholar", "updated": "YYYY-MM-DD"}

用法：
    python3 update_scholar_stats.py <scholar_user_id> <output_json_path>
示例：
    python3 update_scholar_stats.py b-MGt8gAAAAJ scholar-stats.json
"""

import sys
import json
import re
import time
import datetime
import urllib.request
import urllib.error

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def fetch_profile(user, retries=4):
    url = f"https://scholar.google.com/citations?user={user}&hl=en"
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
               "Accept": "text/html,application/xhtml+xml"}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", "replace")
                if "gsc_rsb_st" not in html:
                    # 可能是验证码/拦截页
                    print(f"[warn] 第 {attempt} 次返回页面未含统计块（可能被拦截），片段: "
                          f"{html[:160]!r}")
                    last_err = "no stats block (captcha?)"
                else:
                    return html
        except Exception as e:
            last_err = str(e)
            print(f"[warn] 第 {attempt} 次抓取失败: {e}")
        time.sleep(6)
    print(f"[error] 抓取最终失败: {last_err}")
    return None


def parse_stats(html):
    """从主页 HTML 解析 Citations / h-index / i10-index。返回 (c, h, i10) 或含 None。"""
    idx = html.find('id="gsc_rsb_st"')
    if idx == -1:
        return None, None, None
    block = html[idx:idx + 3000]

    def grab(label):
        # label 之后到第一个数字之间的内容里不应有其它数字（统计值紧随其后）
        m = re.search(re.escape(label) + r'[^0-9]{0,300}?(\d{1,6})', block)
        return int(m.group(1)) if m else None

    return grab('Citations'), grab('h-index'), grab('i10-index')


def main():
    if len(sys.argv) < 3:
        print("用法: update_scholar_stats.py <scholar_user_id> <output_json_path>")
        sys.exit(2)
    user, out = sys.argv[1], sys.argv[2]

    html = fetch_profile(user)
    if not html:
        print("[info] 未能抓取，保持现有 scholar-stats.json 不变。")
        sys.exit(0)

    c, h, i10 = parse_stats(html)
    if None in (c, h, i10):
        print(f"[warn] 解析不完整: citations={c} hIndex={h} i10Index={i10}，不更新。")
        sys.exit(0)

    new_vals = {"citations": c, "hIndex": h, "i10Index": i10}

    # 读取现有值做对比
    old = {}
    try:
        with open(out, "r", encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        old = {}

    if (old.get("citations") == c and old.get("hIndex") == h
            and old.get("i10Index") == i10):
        print(f"[info] 数值未变化 (c={c} h={h} i10={i10})，不更新文件。")
        sys.exit(0)

    data = {
        "citations": c,
        "hIndex": h,
        "i10Index": i10,
        "source": "google-scholar",
        "updated": datetime.date.today().isoformat(),
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"[ok] 已更新 scholar-stats.json: {data}")


if __name__ == "__main__":
    main()
