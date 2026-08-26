# Hacker News 归档

## 连续性保证

采集使用 [Hacker News 官方 API](https://github.com/HackerNews/API) 的 `maxitem` 游标，而不是只读取首页：

1. 每次从远端仓库 `state.json` 的 `last_max_item` 之后开始。
2. 逐个读取到本次运行开始时的 `maxitem`，保留所有 `story` 类型条目。
3. 任何 ID 请求失败时不推进游标，也不提交不完整窗口。
4. 只有 GitHub push 成功后，新游标才成为下次运行的依据；推送失败时，下次会重跑同一窗口。

因此，自动任务暂停或单次失败只会延迟归档，不会制造静默缺口。

## 目录结构

```text
hackernews/
├── YYYY/MM/YYYY-MM-DD.md       # 当日中文精选，含原文和 HN 讨论链接
├── raw/YYYY/MM/DD/*.jsonl      # 游标窗口内的全部 story 快照
├── runs/YYYY/MM/DD/*.json      # 运行边界、数量和完整性记录
└── state.json                  # 远端已成功提交的连续采集游标
```

每篇精选至少记录：HN item ID、原始发布时间、抓取时间、抓取窗口、原文 URL、HN 讨论 URL、分数和评论数快照。

