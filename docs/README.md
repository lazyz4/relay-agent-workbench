# 在线交互预览

此目录由 tools/build_demo.py 从主界面生成，通过 GitHub Pages 发布。

预览只使用浏览器内存和虚构数据，刷新即重置。不运行 Python 后端，不调用真实模型、业务接口或本地 8875 服务，也不接收 API Key。

可体验：查询任务、创建示例需求、生成模板周报、确认/取消、业务记录和演示自检。这些是明确标注的预设流程，不能当作真实 Agent 或跨服务 HTTP 验收。

完整模型、接口接入和验收能力请下载主项目运行。

重新生成与检查：

```text
python tools/build_demo.py
node tools/test_demo.cjs
```

Node.js 只用于此预览开发检查，不是 Python 本地应用的运行依赖。
