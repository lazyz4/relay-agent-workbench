# GitHub 发布说明

## 两种目录布局

- 完整衍生仓库：保留原项目 Git 历史、引擎和组件参考；Relay 位于 workbench/，根 README 指向 Relay 文档及上游说明。
- 独立 Relay 源码包：只有运行所需代码、测试、示例与文档，解压后 README 和 start-relay.cmd 位于根目录；保留 LICENSE 和 THIRD_PARTY_NOTICES。

Relay-GitHub-ready.zip 使用第二种布局，适合解压到新建的个人仓库。它不是 Windows 可执行安装程序，运行仍需要 Python 3.10+。

## 上传前检查

1. 只使用自己的仓库地址。
2. 保留 LICENSE 和 THIRD_PARTY_NOTICES，检查 README 中的能力描述与实际功能一致。
3. 不上传 data/、.env、数据库、日志、密钥或公司内部资料。加密过的凭据文件也不属于公开源码。
4. connectors.json 使用虚构演示系统；实际公司的连接器配置应另外按授权范围管理。
5. 不添加未经实际运行的成功率、企业客户数、效率提升或上线声明。

可以在网页新建空仓库后上传解压目录中的文件，或使用 Git。以下命令需要你自己替换远端地址，本项目没有替你创建或推送 GitHub 仓库：

```text
git init
git add .
git status --short
git commit -m "Initial Relay MVP source and documentation"
git branch -M main
git remote add origin <你创建的空仓库地址>
git push -u origin main
```

提交前检查 git status 和暂存内容，确认不含运行数据。若该目录已是 Git 仓库，应沿用已有历史和远端配置，不要机械重复初始化或替换远端。

## 建议的公开项目描述

Relay 是一个可配置的企业业务 Agent 本地工作台，支持多模型 API、HTTP 业务工具、跨系统任务执行、写入确认和结果回查。当前以两套独立演示服务验证工程能力，真实企业环境的权限与效果需进一步验收。

这段介绍描述项目定位，不代表已经在真实企业生产环境中部署。
