# Product Hunt 归档

Product Hunt 以太平洋时间的 24 小时周期运行并在午夜刷新，因此任务分成两段：

- 上海时间 09:30：采集仍在进行的日榜快照，只用于早期发现，不生成正式日报、不推进完整日期。
- 上海时间 16:15：处理刚结束的 Product Hunt 日榜，执行完整性对账、生成正式日报、推送 GitHub 和钉钉。

结算任务同时从 `state.json` 回补所有缺失日期。主来源是已登录的本地浏览器：读取 Featured 与 All 的全部条目，再进入 AI/开发者工具等高相关产品页采集 maker 说明、完整可见评论快照及 24/72 小时复查结果。

完整日榜必须通过以下对账：All 分页到底、产品 ID 唯一、排名无重复、Featured 是 All 的子集、所有产品页链接可追溯、候选评论页已检查。状态分为 `open`、`closed_pending`、`complete`、`partial` 和 `revisit_due`。

发现层每天读取 Forums、Stories、Newsletters，以及页面实际提供的 AI Coding Agents、AI Infrastructure、Vibe Coding、Prompt Engineering 等分类链接；不存在或返回 404 的入口必须记为失败，不能计入覆盖。

若本地浏览器遇到 Cloudflare、登录失效、404、重定向或分页不完整，记录异常并钉钉告警；允许只读回退到同一 Product Hunt 官方公开页面，但必须在运行日志标注 `fallback`，不得把回退结果冒充浏览器完整采集。只有完整榜单和评论检查均成功并推送 GitHub 后才推进日期状态。
