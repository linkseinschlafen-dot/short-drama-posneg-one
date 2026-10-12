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
      "events": [                              # 情节点列表，必填，按播出顺序
        {
          "id": "e3",                          # 可选；被 resolves 引用时必填，全剧唯一
          "name": "情节点名称",                 # 可选
          "type": "pos1|neg1|zero|transition", # 必填
          "intensity": 1-5,                    # 正一/负一/零建议填，整数 1–5
          "duration_min": 0.5,                 # 可选，成片时长（分钟）
          "resolves": ["e1", "e2"],            # 仅 pos1：这次正一破的是哪些负一危机（可跨集）
          "pending": true                      # 可选：结局悬而未决（刀有没有刺下去/合同签没签）
        }
      ]
    }
  ]
}

零（爽点）的两种标法：
  - type=zero：受压与破局在同一情节点内完成（当场受辱→当场打脸），
    本身已包含一次负一与一次正一。
  - type=pos1 + resolves：破局晚于危机（负一、负一、负一 + 正一），
    该正一与它破掉的负一抵消，诞生一个零；被破掉的负一强度之和记为"蓄压"。

钩子：一集最后一个非过渡情节点标了 pending=true 即为钩子，
type 决定钩子类型（neg1=负一钩子：悬念危机；pos1=正一钩子：极致盼望）。

输出：每集与全集的确定性指标（stdout，UTF-8）。

用法：python3 rhythm_metrics.py <标注文件.json>
"""

import json
import sys

# ---- 经验参考阈值（非理论原文，可按团队口径调整）----
NEG_RUN_WARN = 3          # 连续负一 >= 3 且之后没有破局，视为"压抑透支"
NO_ZERO_GAP_WARN = 4      # 无爽点跨度 >= 4 个情节点，视为"爽点稀薄"
NO_ZERO_GAP_MIN_WARN = 2  # 或无爽点时长 >= 2 分钟（需有时长数据）
LATE_BREAK_WARN = 2       # 危机到破局之间插入 >= 2 个非负一情节点，视为"反转迟滞"
OPENING_WINDOW_MIN = 0.5  # 开局检查窗口：30 秒
FLAT_AVG_WARN = 2.0       # 平均强度 <= 2 视为"情绪扁平"
# ----------------------------------------------------------

SYMBOL = {"pos1": "+", "neg1": "-", "zero": "0", "transition": "·"}
TYPE_CN = {"pos1": "正一", "neg1": "负一", "zero": "零", "transition": "过渡"}
VALID_TYPES = set(TYPE_CN)
EMOTIONAL = ("pos1", "neg1", "zero")


class InputError(Exception):
    pass


def _num(value, where, field):
    """接受数字或数字字符串；None 原样返回。"""
    if value is None:
        return None
    if isinstance(value, bool):
        raise InputError(f"{where}: {field} 应为数字，实际为 {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise InputError(f"{where}: {field} 应为数字，实际为 {value!r}")


def normalize(data):
    """校验并规范化输入，返回 (title, episodes)。"""
    if not isinstance(data, dict):
        raise InputError("顶层应为对象 {\"title\": ..., \"episodes\": [...]}")
    eps = data.get("episodes")
    if not isinstance(eps, list) or not eps:
        raise InputError("episodes 应为非空数组")

    ids = {}
    out = []
    for ei, ep in enumerate(eps):
        if not isinstance(ep, dict):
            raise InputError(f"第 {ei + 1} 个 episode 应为对象")
        no = ep.get("no", ei + 1)
        events = ep.get("events")
        if not isinstance(events, list):
            raise InputError(f"集{no}: events 应为数组")
        norm_events = []
        for k, e in enumerate(events):
            where = f"集{no} 第{k + 1}个情节点"
            if not isinstance(e, dict):
                raise InputError(f"{where}: 应为对象")
            t = e.get("type")
            t = t.strip().lower() if isinstance(t, str) else t
            if t not in VALID_TYPES:
                raise InputError(f"{where}: 未知 type {t!r}（应为 pos1/neg1/zero/transition）")
            intensity = e.get("intensity")
            if intensity is not None:
                iv = _num(intensity, where, "intensity")
                if iv != int(iv) or not 1 <= iv <= 5:
                    raise InputError(f"{where}: intensity 应为 1–5 的整数，实际为 {intensity!r}")
                intensity = int(iv)
            duration = _num(e.get("duration_min"), where, "duration_min")
            if duration is not None and duration < 0:
                raise InputError(f"{where}: duration_min 不能为负")
            resolves = e.get("resolves")
            if resolves is None:
                resolves = []
            elif isinstance(resolves, str):
                resolves = [resolves]
            if not isinstance(resolves, list) or not all(isinstance(r, (str, int)) and not isinstance(r, bool) for r in resolves):
                raise InputError(f"{where}: resolves 应为 id 数组（如 [\"e1\", \"e2\"]），实际为 {resolves!r}")
            pending = e.get("pending", False)
            if not isinstance(pending, bool):
                raise InputError(f"{where}: pending 应为 true/false（不加引号），实际为 {pending!r}")
            if resolves and t != "pos1":
                raise InputError(f"{where}: 只有 pos1 可以填 resolves（type=zero 已自带破局）")
            eid = e.get("id")
            if eid is not None:
                eid = str(eid)
                if eid in ids:
                    raise InputError(f"{where}: id {eid!r} 重复")
            ev = {
                "id": eid,
                "name": e.get("name") or "",
                "type": t,
                "intensity": intensity,
                "duration": duration,
                "resolves": [str(r) for r in resolves],
                "pending": pending,
                "ep_index": ei,
                "index": k,
            }
            for r in ev["resolves"]:
                target = ids.get(r)
                if target is None:
                    raise InputError(f"{where}: resolves 引用的 {r!r} 不存在或不在本情节点之前")
                if target["type"] != "neg1":
                    raise InputError(f"{where}: resolves 引用的 {r!r} 不是 neg1")
                if target.get("resolved_by"):
                    raise InputError(f"{where}: 负一 {r!r} 已被 {target['resolved_by']} 破局过")
                target["resolved_by"] = eid or f"集{no}#{k + 1}"
            if eid is not None:
                ids[eid] = ev
            norm_events.append(ev)
        length = _num(ep.get("length_min"), f"集{no}", "length_min")
        out.append({"no": no, "length": length, "events": norm_events})
    return data.get("title") or "(未命名)", out


def is_break(e):
    """是否产生零：type=zero，或带 resolves 的 pos1。"""
    return e["type"] == "zero" or (e["type"] == "pos1" and e["resolves"])


def symbol(e):
    t, i = e["type"], e["intensity"]
    s = "" if i is None else str(i)
    if t == "zero":
        return f"0({s})" if s else "0"
    if t == "transition":
        return SYMBOL[t]
    sym = SYMBOL[t] + s
    if is_break(e):
        sym += "⇒0"
    if e["pending"]:
        sym += "?"
    return sym


def analyze_episode(ep, all_eps):
    events = ep["events"]
    no = ep["no"]
    durations = [e["duration"] for e in events]
    known = [d for d in durations if d is not None]
    has_all_durations = bool(events) and len(known) == len(events)

    notes = []
    length = ep["length"]
    if length is None or length <= 0:
        length = sum(known) if known else None
        if not known:
            notes.append("集长与情节点时长均缺失，无法计算爽点密度")
        elif not has_all_durations:
            notes.append("集长缺失且部分情节点无时长，集长按已知时长求和，密度偏高，仅供参考")

    counts = {"pos1": 0, "neg1": 0, "zero": 0, "transition": 0}
    flags = []
    combos = []

    # --- 爽点与蓄压 ---
    zeros = []
    for e in events:
        counts[e["type"]] += 1
        if is_break(e):
            pressure = 0
            for r in e["resolves"]:
                pressure += _find(all_eps, r)["intensity"] or 0
            zeros.append((e, pressure))
    zero_count = len(zeros)
    density = zero_count / length if length else None

    if zero_count == 0:
        flags.append("爽点缺失：本集没有任何零（负一危机撞正一破局）")

    # --- 连续负一（压抑透支 / 蓄压爆发）与无爽点跨度 ---
    emo = [e for e in events if e["type"] in EMOTIONAL]
    max_neg_run, neg_run = 0, 0
    max_gap, since_zero = 0, 0
    for i, e in enumerate(emo):
        if e["type"] == "neg1":
            neg_run += 1
            max_neg_run = max(max_neg_run, neg_run)
        else:
            if neg_run >= NEG_RUN_WARN:
                if is_break(e):
                    combos.append(f"负一×{neg_run}+破局：极致压抑后的核弹级爆发")
                else:
                    flags.append(f"压抑透支：连续负一 {neg_run} 个后接的不是破局（{e['name'] or symbol(e)}）")
            neg_run = 0
        if is_break(e):
            since_zero = 0
        else:
            since_zero += 1
            max_gap = max(max_gap, since_zero)
    if neg_run >= NEG_RUN_WARN:
        notes.append(f"集末连续负一 {neg_run} 个未破局：下一集开头须尽快回收，否则压抑透支")
    # 无爽点时长：过渡也占时长
    max_gap_min, gap_min = 0.0, 0.0
    for e in events:
        if is_break(e):
            gap_min = 0.0
        else:
            gap_min = round(gap_min + (e["duration"] or 0), 6)  # 消除浮点累加误差
            max_gap_min = max(max_gap_min, gap_min)

    if zero_count > 0 and max_gap >= NO_ZERO_GAP_WARN:
        flags.append(f"爽点稀薄：最长无爽点跨度 {max_gap} 个情节点")
    elif zero_count > 0 and known and max_gap_min >= NO_ZERO_GAP_MIN_WARN:
        flags.append(f"爽点稀薄：最长无爽点时长约 {round(max_gap_min, 2)} 分钟")

    # --- 经典组合识别（相邻三个情绪情节点）---
    pattern = "".join({"neg1": "负", "pos1": "正", "zero": "零"}[e["type"]] for e in emo)
    if "正负负" in pattern:
        combos.append("正负负：乐极生悲、悬崖坠落")
    if "负正正" in pattern:
        combos.append("负正正：触底反弹、步步高升")

    # --- 反转迟滞：危机与破局之间插入过多非负一情节点 ---
    pos_in_ep = {id(e): i for i, e in enumerate(emo)}
    for e in emo:
        if e["type"] != "pos1" or not e["resolves"]:
            continue
        for r in e["resolves"]:
            target = _find(all_eps, r)
            if target["ep_index"] != ep_index(all_eps, ep):
                notes.append(f"「{e['name'] or symbol(e)}」破的是前集危机 {r}")
                continue
            a, b = pos_in_ep[id(target)], pos_in_ep[id(e)]
            filler = sum(1 for x in emo[a + 1:b] if x["type"] != "neg1")
            if filler >= LATE_BREAK_WARN:
                flags.append(f"反转迟滞：危机「{target['name'] or r}」到破局之间插入了 {filler} 个非负一情节点")

    # --- 开局钩子（仅第 1 集）---
    if ep_index(all_eps, ep) == 0 and events:
        if has_all_durations:
            t, opening = 0.0, []
            for e in events:
                if t >= OPENING_WINDOW_MIN:
                    break
                opening.append(e)
                t += e["duration"]
            if not any(e["type"] in EMOTIONAL for e in opening):
                flags.append("开局无钩子：第 1 集前 30 秒内没有冲突/悬念（全是过渡）")
        elif events[0]["type"] == "transition":
            flags.append("开局无钩子（按顺序判断）：第 1 集第一个情节点是过渡；补全时长可精确检查前 30 秒")

    # --- 结尾钩子 ---
    hook = "无"
    if emo:
        last = emo[-1]
        trailing = len(events) - 1 - events.index(last)
        if last["pending"] and last["type"] in ("neg1", "pos1"):
            hook = "负一钩子（悬念危机）" if last["type"] == "neg1" else "正一钩子（极致盼望）"
            if trailing:
                flags.append(f"钩子被过渡稀释：钩子之后还有 {trailing} 个过渡情节点，钩子应是本集最后一个情节点")
        else:
            why = "结尾是零，危机已解决" if is_break(last) else "最后一个情绪情节点未标 pending（结局已落地）"
            flags.append(f"结尾无钩子：{why}")
        for e in emo[:-1]:
            if e["pending"]:
                notes.append(f"「{e['name'] or symbol(e)}」标了 pending 但不在集末，不计为钩子")
    elif events:
        flags.append("结尾无钩子：本集没有任何情绪情节点")

    # --- 情绪扁平 ---
    ints = [e["intensity"] for e in emo if e["intensity"] is not None]
    avg = sum(ints) / len(ints) if ints else None
    if avg is not None and avg <= FLAT_AVG_WARN:
        flags.append(f"情绪扁平：情绪情节点平均强度 {round(avg, 2)}（≤{FLAT_AVG_WARN}）")
    if len(ints) < len(emo):
        notes.append(f"{len(emo) - len(ints)} 个情绪情节点未填强度")

    return {
        "no": no,
        "seq": " → ".join(symbol(e) for e in events) or "(空)",
        "counts": counts,
        "zeros": zero_count,
        "pressures": [p for _, p in zeros if p],
        "length": length,
        "density": density,
        "max_neg_run": max_neg_run,
        "max_gap": max_gap,
        "max_gap_min": max_gap_min if known else None,
        "avg_intensity": avg,
        "hook": hook,
        "combos": combos,
        "flags": flags,
        "notes": notes,
    }


def _find(all_eps, eid):
    for ep in all_eps:
        for e in ep["events"]:
            if e["id"] == eid:
                return e
    raise KeyError(eid)


def ep_index(all_eps, ep):
    return next(i for i, x in enumerate(all_eps) if x is ep)


def fmt(x, nd=2):
    return "—" if x is None else str(round(x, nd))


def main():
    if len(sys.argv) < 2:
        print("用法: python3 rhythm_metrics.py <标注文件.json>", file=sys.stderr)
        sys.exit(1)
    try:
        with open(sys.argv[1], encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {sys.argv[1]}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"错误: JSON 解析失败（{e}），请检查标注文件格式", file=sys.stderr)
        sys.exit(1)

    try:
        title, eps = normalize(data)
    except InputError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    results = [analyze_episode(ep, eps) for ep in eps]
    total_len = sum(r["length"] or 0 for r in results)
    total_zero = sum(r["zeros"] for r in results)
    # 平均密度只统计有集长的集，避免无时长集的爽点抬高密度
    timed_zero = sum(r["zeros"] for r in results if r["length"])

    print(f"剧名: {title}")
    print(f"集数: {len(eps)}  |  总集长: {fmt(total_len or None)} 分  |  总爽点数: {total_zero}"
          f"  |  平均密度: {fmt(timed_zero / total_len if total_len else None, 3)} 个/分")
    print("=" * 60)
    for r in results:
        c = r["counts"]
        print(f"集{r['no']}: {r['seq']}")
        print(f"  正一={c['pos1']} 负一={c['neg1']} 零={r['zeros']} 过渡={c['transition']}"
              f" | 集长 {fmt(r['length'])}分 | 爽点密度 {fmt(r['density'], 3)}/分")
        print(f"  最长连续负一 {r['max_neg_run']} | 最长无爽点跨度 {r['max_gap']} 个情节点"
              f"（约 {fmt(r['max_gap_min'])} 分） | 平均强度 {fmt(r['avg_intensity'])} | 结尾钩子: {r['hook']}")
        if r["pressures"]:
            print(f"  蓄压破局: {'、'.join(str(p) for p in r['pressures'])}（被破负一强度之和，越大爽感越强）")
        for x in r["combos"]:
            print(f"  [组合] {x}")
        for x in r["flags"]:
            print(f"  [告警] {x}")
        for x in r["notes"]:
            print(f"  [提示] {x}")
    print("=" * 60)
    print("符号: +正一 -负一 0(n)当场爽点 ⇒0破局产生爽点 ?悬而未决 ·过渡")
    print("说明: 零的数量=情绪高潮次数为理论口径；告警阈值为经验参考值，非理论原文。")


if __name__ == "__main__":
    main()
