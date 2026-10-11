zidon v0.2.0 发布：把「发版 + 宣传」整条链路搬到了 GitHub 云端。

它解决的问题：小项目发版时，改 README、写 Release Notes、发社交动态、提交搜索引擎，一堆动作要手工做，做几次就懒得做了。

现在的流程：
1. 本地用 Ollama 小模型写草稿（i3 无显卡也跑得动，不占资源）
2. 你看一眼，确认或改一句
3. 推上去，GitHub Actions 自动建 Release、发动态、部署落地页、提交 IndexNow

内置的克制设计：所有对外内容必须经人工审批（未审批的草稿被 .gitignore 挡住，CI 也会再校验一次）；只调用各平台官方 API；不做自动关注、私信、群发评论；每平台有发帖最小间隔和每日上限；默认 dry-run，先看效果再真发。

工具零第三方依赖，只用了 Python 标准库。

https://github.com/yourname/zidon