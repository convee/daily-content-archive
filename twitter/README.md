# X / Twitter 归档

## 采集范围

使用用户已登录的本地浏览器，只读采集 AI、开发者工具和前沿科技内容。范围由 `sources.json` 明确定义，包括官方机构、研究者/工程师、主题搜索；不是对整个平台的全量镜像。

每两小时读取各账号时间线并向下滚动到已提交检查点之前。帖子以 status ID 去重；高信号帖子继续打开回复和引用页，保存能补充技术细节、数据、反例、一手使用反馈或风险判断的回复。

若登录失效、页面限流、验证码、账号不可见或评论加载不全，则不推进对应来源检查点，写入运行日志并通过钉钉告警。任务绝不点赞、转发、回复或关注。

## 目录

```text
twitter/
├── YYYY/MM/YYYY-MM-DD.md
├── raw/YYYY/MM/DD/posts-*.jsonl
├── raw/YYYY/MM/DD/comments-*.jsonl
├── runs/YYYY/MM/DD/*.json
├── sources.json
└── state.json
```
