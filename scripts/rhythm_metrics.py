#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正负一情绪节奏指标计算器（short-drama-posneg-one skill）

输入：JSON 标注文件
{
  "title": "短剧名",                          # 可选
  "episodes": [                                # 必填，至少 1 集
    {
      "no": 1,                                 # 集号，必填
      "length_min": 3.0,                       # 可选，集长（分钟）；缺省按事件时长求和
      "events": [                              # 情节点列表，必填
        {
          "name": "情节点名称",                 # 可选
          "type": "pos1|neg1|zero|transition", # 必填
          "intensity": 1-5,                    # 可选，正一/负一/零建议填
          "duration_min": 0.5                   # 可选，成片时长（分钟）
        }
      ]
    }
  ]
}

输出：每集与全集的确定性指标（stdout，UTF-8）。

用法：python3 rhythm_metrics.py <标注文件.json>
"""

import json
import sys

# ---- 经验参考阈值（非理论硬性标准，可按团队口径调整）----
NEG_RUN_WARN = 3        # 连续负一 >= 3 视为"压抑透支"
NO_ZERO_GAP_WARN = 4    # 无爽点跨度 >= 4 个情节点视为"爽点稀薄"
# ----------------------------------------------------------

SYMBOL = {"pos1": "+", "neg1": "-", "zero": "0", "transition": "·"}
TYPE_CN = {"pos1": "正一", "neg1": "负一", "zero": "零", "transition": "过渡"}
VALID_TYPES = set(TYPE_CN.keys())


def analyze_episode(ep):
    events = ep.get("events", [])
    no = ep.get("no", "?")

    # 集长：优先取 length_min，否则按事件时长求和
    length = ep.get("length_min")
    if length is None or length <= 0:
        length = sum(float(e.get("duration_min") or 0) for e in events)

    counts = {"pos1": 0, "neg1": 0, "zero": 0, "transition": 0}
    seq = []
    max_neg_run = 0
    neg_run = 0
    since_zero = 0
    max_gap = 0

    for e in events:
        t = e.get("type", "").strip().lower()
        if t not in VALID_TYPES:
            raise ValueError(f"集{no}: 未知 type '{t}'（应为 pos1/neg1/zero/transition）")
        counts[t] += 1
        intensity = e.get("intensity")
        if t == "zero":
            seq.append(f"0({intensity})" if intensity else "0")
        elif t in ("pos1", "neg1"):
            seq.append(f"{SYMBOL[t]}{intensity}" if intensity else SYMBOL[t])
        else:
            seq.append(SYMBOL[t])
        if t in ("pos1", "neg1", "zero"):
            if t == "neg1":
                neg_run += 1
                max_neg_run = max(max_neg_run, neg_run)
            else:
                neg_run = 0
            if t == "zero":
                since_zero = 0
            else:
                since_zero += 1
        max_gap = max(max_gap, since_zero)

    zeros = counts["zero"]
    density = (zeros / length) if length > 0 else 0.0

    flags = []
    if zeros == 0:
        flags.append("爽点缺失（本集零=0）")
    if max_neg_run >= NEG_RUN_WARN:
        flags.append(f"压抑透支（连续负一={max_neg_run}）")
    if max_gap >= NO_ZERO_GAP_WARN:
        flags.append(f"爽点稀薄（无爽点跨度={max_gap}个情节点）")

    return {
        "集号": no,
        "事件序列": " → ".join(seq),
        "正一": counts["pos1"],
        "负一": counts["neg1"],
        "零": counts["zero"],
        "过渡": counts["transition"],
        "集长(分)": round(length, 2),
        "爽点密度(个/分)": round(density, 3),
        "最长连续负一": max_neg_run,
        "最长无爽点跨度(情节点)": max_gap,
        "告警": flags,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python3 rhythm_metrics.py <标注文件.json>", file=sys.stderr)
        sys.exit(1)
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误: JSON 解析失败（{e}），请检查标注文件格式", file=sys.stderr)
        sys.exit(1)

    eps = data.get("episodes")
    if not eps:
        print("错误: episodes 为空", file=sys.stderr)
        sys.exit(1)

    results = [analyze_episode(ep) for ep in eps]
    total_len = sum(r["集长(分)"] for r in results)
    total_zero = sum(r["零"] for r in results)

    print(f"剧名: {data.get('title', '(未命名)')}")
    print(f"集数: {len(eps)}  |  总集长: {round(total_len, 2)} 分  |  总爽点数: {total_zero}"
          f"  |  平均密度: {round(total_zero / total_len, 3) if total_len > 0 else 0} 个/分")
    print("=" * 60)
    for r in results:
        print(f"集{r['集号']}: {r['事件序列']}")
        print(f"  正一={r['正一']} 负一={r['负一']} 零={r['零']} 过渡={r['过渡']}"
              f" | 集长 {r['集长(分)']}分 | 爽点密度 {r['爽点密度(个/分)']}/分"
              f" | 最长连续负一 {r['最长连续负一']} | 无爽点跨度 {r['最长无爽点跨度(情节点)']}")
        for f_ in r["告警"]:
            print(f"  [告警] {f_}")
    print("=" * 60)
    print("说明: 告警阈值（连续负一>=3、无爽点跨度>=4）为经验参考值；零数量=情绪高潮频次为理论口径。")


if __name__ == "__main__":
    main()
