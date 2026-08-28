# Daily Content Archive

按平台归档每日信息简报，保留连续采集游标和可追溯来源。

## 平台目录

- [`hackernews/`](hackernews/)：Hacker News 全量 item 游标、帖子与高价值评论。
- [`twitter/`](twitter/)：X/Twitter AI 与科技账号、主题搜索和高价值回复。
- [`reddit/`](reddit/)：AI、开发、安全、开源与科技社区的新帖和评论。
- [`producthunt/`](producthunt/)：Product Hunt 每日完整榜单、AI/科技精选与评论。

未来增加其他平台时，使用新的同级目录，避免混用游标、来源口径和去重规则。每条精选都必须能回到原帖或评论；运行异常单独记账，并通过钉钉通知。

## 可靠性门槛

- `python3 scripts/archive_health.py --repo .`：校验 JSON/JSONL、状态引用、游标与 durable raw 对账、日报溯源和公开发布门槛。
- `python3 scripts/archive_lock.py --repo . acquire --name <platform> --owner <run-id>`：为采集或发布事务申请带超时恢复的租约锁；结束时由同一 owner 释放。
- 只有通过平台完整性门槛的数据才能成为公开日报；partial、测试或进行中快照保留在 GitHub 作为证据，但不进入 GitHub Pages 导航。

## 在线阅读

GitHub Pages：<https://convee.github.io/daily-content-archive/>
