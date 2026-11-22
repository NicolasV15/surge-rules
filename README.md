# 个人 Surge 规则集

Surge 从本仓库 `main` 的 GitHub Raw 地址加载规则，使用默认 24 小时的外部资源刷新周期。[查看可复制的 Surge 规则片段](surge-rule-snippet.txt)。片段要求本地已有同名策略组，并标出本机规则的插入位置。将相关行合并进已有的 `[Rule]`，保留本地的端口规则、校园网例外、局域网规则和 `FINAL`。接入后可在 Surge 的外部资源页面刷新对应规则集。

- `rules/track/` 跟踪上游。每天北京时间 10:37 检查，也可在 Actions 手动运行。规则语义变化进入一个待审核的 PR，合并到 `main` 后才发布。同步任务失败时不会改动已发布的规则。
- `rules/manual/` 从上游导入一次，由仓库主人维护。之后编辑这些文件即可。
- `local/` 保存个人补充。为某个类别加规则时，在该类别的基础清单之前加载补充清单。微信分流由 [local/wechat.list](local/wechat.list) 独立维护，依据自有连接记录和微信服务域名，包含三条已观察的图片 CDN IPv6 地址。应用内去广告重写仍由设备上的 Surge 模块管理。China 补全清单是试验候选，目前不在接入片段中。
- `sources.json` 记录来源、文件格式、维护方式和许可证。`snapshots.json` 存储快照 SHA-256。对自维护文件，它记录首次导入版本而非当前内容。上游注释、版权和许可证文本按来源保留。

## AI 分流

| 服务 | Surge 规则 | 来源和维护方式 |
| --- | --- | --- |
| Codex | [codex.list](local/codex.list) | 根据 [OpenAI 网络说明](https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps) 和本仓库已有规则维护。Codex 的登录、模型服务和 ChatGPT 共用部分域名。 |
| Gemini | [gemini.list](local/gemini.list) | 根据 [Gemini API 文档](https://ai.google.dev/api)、[Code Assist 源码](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/code_assist/server.ts) 和本仓库已有规则维护。覆盖 Gemini 网页、AI Studio、API 和 Code Assist。 |
| Claude Code | [claude-code.list](rules/track/claude-code.list) | 每天跟踪 [erwanjun 的 Claude Core 清单](https://github.com/erwanjun/surge-claude-rules/blob/main/Surge/Claude-Core.list)。包含其共用的 Claude 和 Anthropic 域名，以及 IP 回退规则。 |
| Antigravity | [antigravity.list](local/antigravity.list) | 根据 [Google Antigravity 网络说明](https://antigravity.google/docs/enterprise/#network-allowlists-and-mtls-endpoints) 维护专用网站和 Business AI Code 端点。与 Gemini 共用的 `cloudcode-pa.googleapis.com` 仍由 Gemini 清单匹配。 |

| 策略组 | 使用的清单 | 参考配置 |
| --- | --- | --- |
| `OpenAI` | codex.list | 默认主力美国节点 |
| `Google AI` | gemini.list、antigravity.list | 共用策略组，默认主力美国节点 |
| `Claude Code` | claude-code.list | 默认主力美国节点；可用 `hidden=1` 隐藏 |
| `Other AI Platform` | ai-other.list | 其他 AI 服务与集成；可用 `hidden=1` 隐藏 |

使用公开片段前，在自己的 `[Proxy Group]` 中定义对应组并选择已有出口。按域名共享的请求遵循其命中的清单。

[ai-other.list](local/ai-other.list) 包含 Copilot、Perplexity、NotebookLM、TRAE 国际站、Dify 云端和若干集成，包括 GitHub 通用 API `api.github.com`。TRAE 中国站 `trae.cn` 等国内站点沿用已有的地区分流规则。此前的两个 AI 总表 URL 保留给旧客户端。

## 验证与回退

本地运行：

```sh
python3 scripts/rules.py validate
python3 -m unittest discover -s scripts -p 'test_*.py'
```

Actions 同步使用专用分支 `automation/upstream-rules`，每次从 `main` 重建。个人改动请用其他分支。仓库需开启 **Allow GitHub Actions to create and approve pull requests**，同步工作流只创建或更新 PR，合并由仓库主人完成。同步任务会在创建 PR 前检查候选内容，普通人工 PR 也会执行验证。

发布后如发现分流异常，可撤销相应合并并刷新外部资源。首次迁移如需回退整个本机规则段，应使用部署时保存的旧 `[Rule]`、当前修订号和 `surge-cli profile section set Rule`。可先比较差异，保留迁移后新增的无关改动。

## 第三方来源

- [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) · [GPL-2.0](licenses/blackmatrix7-GPL-2.0.txt)
- [SukkaLab/ruleset.skk.moe](https://github.com/SukkaLab/ruleset.skk.moe) · [AGPL-3.0](licenses/Sukka-AGPL-3.0.txt)
- [erwanjun/surge-claude-rules](https://github.com/erwanjun/surge-claude-rules) · [MIT](licenses/erwanjun-MIT.txt)
- [anti-AD](https://github.com/privacy-protection-tools/anti-AD) · [MIT](licenses/anti-AD-MIT.txt)

第三方文件各自沿用上游许可证。仓库公开内容局限于规则和通用策略引用。
