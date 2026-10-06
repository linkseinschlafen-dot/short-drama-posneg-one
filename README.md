# short-drama-posneg-one · 正负一编剧理论剧本诊断 Skill

基于「正负一编剧理论」对短剧 / 微短剧剧本进行**情绪节奏诊断与优化**的 Skill：把剧情按情节点标注为正一（情绪奖励）、负一（情绪打压）、零（爽点 = 负一危机撞正一破局），量化单集爽点密度，生成情绪心电图，识别节奏问题并给出可落地的改写建议。

> 核心口诀：**负一危机撞上正一破局，抵消诞生一个"零"（爽点）；一集里零的数量 = 观众情绪高潮的次数。**

## 功能

- 情节点切分与标注（正一 / 负一 / 零 / 过渡，含强度、时长）
- 自动计算爽点密度、最长连续负一、最长无爽点跨度等指标
- 输出情绪心电图（文本波形）
- 诊断爽点缺失、爽点稀薄、压抑透支、反转迟滞、开局 / 结尾无钩子、情绪扁平等问题
- 给出"原情节 → 改写建议"对照，含经典组合重构（负负负+正 / 正负负 / 负正正）与钩子设计

## 目录结构

```
short-drama-posneg-one/
├── SKILL.md                          # Skill 主文档：诊断工作流与交付格式
├── references/
│   ├── theory.md                     # 正负一理论完整速览
│   └── diagnosis-examples.md         # 完整诊断示例
└── scripts/
    └── rhythm_metrics.py             # 情绪节奏指标计算器
```

## 使用

指标计算器接收标注 JSON，输出每集与全集的确定性指标：

```bash
python3 scripts/rhythm_metrics.py <标注文件.json>
```

输入 JSON 示例：

```json
{
  "title": "示例短剧",
  "episodes": [
    {
      "no": 1,
      "length_min": 3.0,
      "events": [
        {"name": "女主被当众羞辱", "type": "neg1", "intensity": 4, "duration_min": 0.5},
        {"name": "男主现身打脸全场", "type": "zero", "intensity": 5, "duration_min": 0.8}
      ]
    }
  ]
}
```

完整诊断流程与判定细则见 [SKILL.md](./SKILL.md)，理论讲解见 [references/theory.md](./references/theory.md)。

## 理论出处

徐老师正负一编剧写作理论（2026-10-06 教学分享）。
