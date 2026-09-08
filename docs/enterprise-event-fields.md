# 企业云端事件字段与本地采集说明

本文依据 git-ai-wrapper 提交 `1f1440f` 的实际实现整理，记录日期为 2026-09-08。对应固定上游 Git AI `v1.7.0`。

当前企业上传只有两类事件：`checkpoint` 和 `commit`。实际 JSON 字段名是 **`event_type`**，不是 `eventType`。

每次 HTTPS POST 请求包含一条事件，结构如下：

```json
{
  "completeData": {
    "schema_version": 1,
    "event_type": "checkpoint"
  }
}
```

以上仅展示请求层级，不是完整合法事件。请求使用 `Content-Type: application/json`，鉴权信息放在 `token` 请求头中。下面所有事件字段均位于 `completeData` 内；标记“可选”的字段在没有数据时省略，不补空字符串或零。

实现依据：[企业上传补丁](../patches/enterprise-metrics.patch)，重点对应补丁中的 `domain.rs`、`identity.rs`、`projection.rs`、`sink.rs` 和 `store.rs`。运行与配置约定见 [企业上传说明](enterprise-metrics.md)。

## 1. 公共字段

| 字段 | 类型 | 含义 | 本地采集或生成方式 |
|---|---|---|---|
| `schema_version` | 整数 | 上传数据结构版本，当前为 `1` | 程序固定赋值 |
| `event_type` | 字符串 | `checkpoint` 或 `commit` | 根据本地指标类型映射 |
| `event_id` | 字符串 | 单条上传事件的唯一标识，用于去重 | 首次进入企业队列时生成 UUID 并持久化；重试不换 ID |
| `event_timestamp` | 时间字符串 | 事件发生时间，UTC RFC3339 格式 | checkpoint 优先使用检查点时间；commit 使用源指标事件时间 |
| `client_version` | 字符串 | Git AI wrapper 构建版本 | 构建时嵌入，例如 `v1.7.0-tac.v0.2.0`；不是 TCLI 版本号 |
| `organization_id` | 字符串 | 所属组织标识 | 来自构建时嵌入的发布配置 |
| `user_id` | 字符串 | 当前仓库配置的用户邮箱 | 采集时读取仓库实际生效的 Git `user.email` |
| `repo_id` | 字符串 | 规范化后的仓库远端地址 | 优先读取 origin URL；没有 origin 时，仅在只有一个 remote 的情况下使用它 |
| `tool` | 字符串，可选 | 归因工具，如 `codebuddy`、`codex` | checkpoint 来自工具适配器；commit 仅有一个工具/模型分组时填写 |
| `model` | 字符串，可选 | 模型名称 | checkpoint 来自工具元数据或本地会话记录；commit 来自归因统计分组 |
| `session_id` | 字符串，可选 | 脱敏后的会话标识 | 对本地会话标识进行 HMAC-SHA256；commit 当前不上传此字段 |

### 身份字段约定

- `user_id` 上传的是邮箱，`repo_id` 上传的是规范化仓库 URL，二者不是哈希值。
- `user_id` 表示采集时的 Git 配置用户，不是历史提交的 author。支持全局配置回退及仓库、worktree 等有效配置覆盖。
- URL 会移除凭据、`.git` 后缀和尾部斜杠，并规范化 SSH/HTTPS 表示。非默认端口保持区分；不会自动合并主机别名。
- 身份在采集时保存快照，上传重试时不重新读取当前仓库配置。
- 缺少邮箱或明确的仓库 URL 时，事件进入 `waiting_identity`，不猜测身份。后来补配置也不会自动改写旧事件；新事件使用新配置。
- `event_id` 标识上传事件，不表示一个跨文件的逻辑 checkpoint，也不表示会话中的顺序。

## 2. checkpoint：编辑过程事件

`event_type` 为 `checkpoint`。除公共字段外，还包含：

| 字段 | 类型 | 含义 | 本地采集或计算方式 |
|---|---|---|---|
| `kind` | 字符串 | 本次变更的归因类别 | 根据 checkpoint 类型转换，取值见下表 |
| `measurement_mode` | 字符串 | `direct`：直接记录；`recovery`：补偿恢复 | 根据 checkpoint 是否带已知恢复类型判断 |
| `lines_added` | 整数 | 本次文件变更新增行数 | 直接模式比较文件前后内容；恢复模式使用恢复出的归因行数 |
| `lines_deleted` | 整数 | 本次文件变更删除行数 | 直接模式比较文件前后内容；当前恢复路径填写 `0` |
| `lines_added_sloc` | 整数，可选 | 新增的非空白行数 | 直接模式对新增行执行 trim，排除空白行 |
| `lines_deleted_sloc` | 整数，可选 | 删除的非空白行数 | 直接模式对删除行执行同样过滤 |
| `file_id` | 字符串，可选 | 脱敏的文件标识 | 将仓库标识与规范化文件路径组合后做 HMAC-SHA256 |
| `tool_use_id` | 字符串，可选 | 脱敏的单次工具调用标识 | 从本地工具调用元数据获取，结合会话标识做 HMAC-SHA256 |
| `trace_id` | 字符串，可选 | 脱敏的本地追踪关联标识 | 从 checkpoint 的追踪属性获取，再做 HMAC-SHA256 |
| `edit_kind` | 字符串，可选 | 编辑入口：`file_edit` 或 `bash` | 来自工具适配器传入的编辑元数据 |
| `checkpoint_type` | 字符串，可选 | 补偿恢复的具体类型 | 来自本地恢复流程；直接记录通常没有此字段 |

### kind 取值

| 值 | 含义 |
|---|---|
| `ai_agent` | AI Agent 编辑产生的归因 |
| `ai_tab` | AI 补全产生的归因 |
| `known_human` | 有明确人工编辑证据的归因 |
| `unknown` | 无法明确归因；本地旧类型 human 映射为此值 |

### checkpoint_type 取值

| 值 | 含义 |
|---|---|
| `recovered_bash` | 从 Bash 执行相关证据恢复归因 |
| `recovered_session_event_mtime` | 结合会话事件和文件修改时间恢复归因 |
| `recovered_commit_metadata` | 从提交相关元数据恢复归因 |
| `recovered_edge_extension` | 从扩展提供的证据恢复归因 |

### checkpoint 统计口径

- 一条 checkpoint 上传事件对应一个文件事实。一次操作涉及多个文件时可能产生多条事件。
- SLOC 当前只排除空白行，不排除注释行，不能直接理解为“有效业务代码行”。
- 恢复模式的新增行数表示“恢复出的归因行数”；当前 SLOC 也使用该恢复行数，删除行数和删除 SLOC 为零。应与直接编辑统计分开分析。
- 未识别的 kind、checkpoint_type 或 edit_kind 不会被随意转换后上传。

## 3. commit：最终提交事件

`event_type` 为 `commit`。除公共字段外，还包含：

| 字段 | 类型 | 含义 | 本地采集或计算方式 |
|---|---|---|---|
| `commit_id` | 字符串 | 完整 Git 提交 SHA | 从已处理的 Git 提交获取，保留原始 SHA |
| `committed_at` | 时间字符串 | Git committer 时间，UTC RFC3339 | 从提交元数据读取；不是上传时间 |
| `git_diff_added_lines` | 整数 | 本次提交新增的总行数 | Git AI 原生提交 diff 统计 |
| `git_diff_deleted_lines` | 整数 | 本次提交删除的总行数 | Git AI 原生提交 diff 统计 |
| `ai_additions` | 整数 | 提交新增行中归属于 AI 的行数 | 将编辑阶段的归因记录映射到最终提交，汇总 AI 归因 |
| `human_additions` | 整数 | 提交新增行中有明确人工归因的行数 | 使用原生 known-human 归因统计 |
| `unknown_additions` | 整数 | 提交新增行中未明确归因的行数 | 总新增 − AI 新增 − 明确人工新增 |
| `tool_model_breakdown` | 数组 | 按工具和模型细分的 AI 新增行数 | 从原生提交统计的工具/模型分组转换 |
| `is_rewrite` | 布尔值 | 是否为历史重写事件 | 当前上传路径固定为 false，未接入 rewrite 类型 |
| `is_merge` | 布尔值 | 是否为合并提交 | 当前上传路径固定为 false；多父提交不进入此类上传 |

### tool_model_breakdown 明细

每项包含：

| 字段 | 类型 | 含义 |
|---|---|---|
| `tool` | 字符串 | 工具名称 |
| `model` | 字符串 | 模型名称 |
| `ai_additions` | 整数 | 该工具和模型对应的 AI 新增行数 |

示例片段：

```json
{
  "tool_model_breakdown": [
    {
      "tool": "codebuddy",
      "model": "deepseek-v4-pro",
      "ai_additions": 12
    }
  ]
}
```

### commit 校验与统计口径

```text
git_diff_added_lines = ai_additions + human_additions + unknown_additions
ai_additions = 所有 tool_model_breakdown 项的 ai_additions 之和
```

- 原生统计中的 all 汇总项不会再作为明细重复累计。
- 缺少必要统计、父提交数量证据或分组不一致时，事件会被隔离，不会用零或 false 填充缺失证据后上传。
- 多父提交不进入当前 commit 上传路径；根提交和普通单父提交可以进入。
- commit 可能包含多个会话，因此不伪造唯一 session_id。
- 仅当工具/模型明细恰好只有一个分组时，公共 tool/model 字段才填写；完整构成以明细数组为准。
- event_timestamp 表示源指标事件时间，committed_at 表示 Git 提交元数据中的 committer 时间，二者不必相同。

## 4. 本地采集到云端的完整过程

### 4.1 工具产生编辑证据

AI 工具的 Hooks 或 IDE 插件触发 Git AI。工具适配器读取 Hook 输入及必要的本地会话记录，取得工具、模型、会话、文件和调用信息。不同工具的数据来源不同，没有证据的可选字段不会被猜测补齐。

### 4.2 后台计算文件变化

Git AI 对比先前记录的文件内容与当前内容，计算新增、删除及非空白行数，维护工作区归因记录，并按文件生成 checkpoint 指标。恢复流程根据已有证据补充归因。

直接记录的行数计算位于上游 `src/daemon/checkpoint.rs` 的 `compute_file_line_stats()`；补偿记录位于 `src/authorship/attribution_recovery.rs`。

### 4.3 提交后计算最终归因

Git 操作通过 Trace2 进入后台处理流程。Git AI 结合实际提交 diff、工作区归因和提交元数据，计算 commit 统计。不是把所有 checkpoint 的新增行数直接相加。

提交统计采集位于上游 `src/authorship/post_commit.rs`，企业转换规则位于补丁中的 `src/enterprise_metrics/projection.rs`。

### 4.4 指标与企业队列落盘

本地源指标保存在 metrics 表，企业事件引用保存在 enterprise_inbox。源指标和企业队列引用在同一 SQLite 事务中保存。随后转换为本文列出的白名单字段，写入 enterprise_events，每个目的端对应一条 enterprise_deliveries 投递记录。

默认数据库路径：

```text
~/.git-ai/internal/metrics-db
```

| 表 | 用途 |
|---|---|
| `metrics` | 上游本地源指标 |
| `enterprise_inbox` | 源指标引用、冻结身份、事件 ID 与转换状态 |
| `enterprise_events` | 转换后的企业上传事件 |
| `enterprise_deliveries` | 每个目的端的投递状态、尝试次数、租约与 ACK 时间 |

### 4.5 异步发送并保存回执

后台使用 Native TLS 发送 HTTPS 请求，按配置的成功协议判断结果。成功后标记 delivered 并写入 ack_at；重试保留原 event_id。网络发送不在 Git/Hook 关键处理路径或数据库事务内执行。

可通过原生命令查看汇总状态：

```sh
tcli ga enterprise-telemetry status
```

status 是汇总信息；验证某次操作时，还应关联具体 event_id 或 commit_id。pending/inflight 或 flush 成功不代表云端已确认接收。

## 5. 当前不上传的内容与分析建议

当前企业上传 DTO 不包含：代码正文、diff 正文、提示词、会话全文、原始文件路径、提交说明、完整恢复元数据。分支、IP、主机名和 token 使用量等也不在本文列出的字段中。

这仅描述企业上传路径，不表示本地源指标从未采集这些内容。

当前没有独立的 session、token_usage、merge、rewrite 上传事件。is_merge/is_rewrite 字段存在，不代表已支持这些事件的生产上传。

云端报表建议：

- 用 checkpoint 分析编辑过程与工具活动。
- 用 commit 分析实际提交中的 AI 贡献。
- 将 direct 与 recovery 分开统计。
- 不将 unknown_additions 直接当作人工贡献。
- 不把 checkpoint 行数与 commit 行数相加，否则会重复计算。

## 6. 如何区分 AI、明确人工与未知归因

`event_type` 只区分“编辑过程 checkpoint”和“最终提交 commit”，不直接表示 AI 或人工。不能用 tool/ai_tools 是否为空判定归因，也不能将没有 AI 证据的代码自动归为人工。

### 6.1 checkpoint：按 kind 分类

| event_type | kind | 云端归因类别 | 本地证据来源 |
|---|---|---|---|
| checkpoint | ai_agent | AI 编辑 | Agent 编辑后的 Hook，以及相应的文件变化与 Agent 身份 |
| checkpoint | ai_tab | AI 编辑 | 适配器明确标记的 AI 补全事件及文件变化 |
| checkpoint | known_human | 明确人工编辑 | IDE/编辑器集成提供的明确人工编辑证据，通过本地 known-human 路径记录 |
| checkpoint | unknown | 未知归因 | 本地旧 Human 类型代表无明确归因的变化，上传时转换为 unknown |

AI 工具执行前的检查可能发现工作区已有修改。即便检查由 CodeBuddy/Codex 触发，也不能把这些已有修改归给该工具。非 AI checkpoint 不保存用于 AI 归因的 agent_id，因此其 tool/model/session_id 可以为空；这不是把 AI 代码改判成人工。

`measurement_mode` 是另一个独立维度：direct 表示直接记录；recovery 表示补偿恢复。当前恢复路径产生 ai_agent 记录，但应与直接编辑量分开统计。

### 6.2 commit：按行数拆分，不把整次提交强制分为 AI 或人工

commit 不包含 kind，一个提交可以同时包含 AI、明确人工和未知归因的新增行：

| 字段 | 归因类别 | 本地判定 |
|---|---|---|
| ai_additions | AI | 最终提交 diff 中有 AI 归因证据、实际进入提交的新增行 |
| human_additions | 明确人工 | 最终提交 diff 中有 KnownHuman 归因证据的新增行 |
| unknown_additions | 未知 | 新增总行数中剩余的无明确归因部分 |

本地通过 checkpoint 维护归因，再将归因映射到提交 diff。原生统计中 ai_additions 使用实际接受到提交中的 AI 行数；不是模型生成的全部行数，也不是历史 checkpoint 新增行数之和。

例如，一次提交新增 100 行，其中 AI 60 行、明确人工 25 行、未知 15 行，应分别保留三个数，不把整次提交标成“纯 AI”或“纯人工”。

commit 顶层 tool/model 仅在明细只有一个工具/模型分组时填写。多个工具参与时，顶层字段可能为空，但 ai_additions 仍大于零，应读取 tool_model_breakdown。没有顶层工具字段不等于没有 AI 贡献。

## 7. 云端统计推荐规则

本节为建议的云端消费与报表规则，不表示当前服务端已实现。现有 CSV 中的重复记录及表层字段映射仍需服务端核对。

### 7.1 先做事件幂等与数据范围过滤

1. 以 `(organization_id, event_id)` 建立事件幂等唯一约束。重复投递应返回成功确认，不重复插入；同 ID 内容不一致时记录冲突，不静默覆盖。
2. 历史报表先按上述键去重，再做行数聚合。`event_id` 去重解决重试重复；同一 repo/commit 是否接受多个客户端的独立观察，是另一项业务规则，不能直接对它们求和或把不同 commit_id 合并。
3. 将 simulation-only、simulation-unreleased 等测试数据排除在正式组织报表之外；后续使用明确的环境/数据来源隔离策略。
4. 校验 schema_version、事件类型、枚举、非负行数及 commit 加和关系。缺失或非法字段应进入异常数据处理，不能无条件转为零。
5. 按 organization_id/repo_id/user_id 限定分析范围。user_id 是采集时的 Git 配置邮箱，不应直接解释为历史提交作者。

### 7.2 编辑过程报表：只统计 checkpoint

默认编辑量报表选择 `measurement_mode = direct`，按 kind 分类：

| 指标 | 筛选条件 | 聚合字段 |
|---|---|---|
| AI 编辑新增行数 | kind 为 ai_agent 或 ai_tab | SUM(lines_added) |
| AI 编辑删除行数 | kind 为 ai_agent 或 ai_tab | SUM(lines_deleted) |
| 明确人工编辑新增行数 | kind 为 known_human | SUM(lines_added) |
| 明确人工编辑删除行数 | kind 为 known_human | SUM(lines_deleted) |
| 未知归因新增行数 | kind 为 unknown | SUM(lines_added) |
| 未知归因删除行数 | kind 为 unknown | SUM(lines_deleted) |

recovery 使用同样的分类，但独立展示为“恢复归因量”。不要直接累加到直接编辑量中并称为代码产出。

- 时间维度使用 event_timestamp，不使用接收入库时间。
- tool/model 用于 AI 编辑量分组；非 AI 记录保留明确人工/未知分类，不填造工具名称。
- SLOC 字段可能缺失，应同时展示其数据覆盖范围；不能把缺失当作零。当前 SLOC 不排除注释。
- checkpoint 数量表示文件事实数量，不等于工具调用次数、会话数量或用户操作次数。
- 编辑过程可能反复修改同一行；它是变化量，不是最终提交量。
- 删除行数表示该类编辑操作删除的行数，不足以证明被删除代码原本由谁编写。

### 7.3 提交贡献报表：只统计 commit

在完成幂等及提交观察规则处理后的数据集中：

```text
提交新增总行数 = SUM(git_diff_added_lines)
提交删除总行数 = SUM(git_diff_deleted_lines)
AI 提交新增行数 = SUM(ai_additions)
明确人工提交新增行数 = SUM(human_additions)
未知归因提交新增行数 = SUM(unknown_additions)

AI 提交新增占比 = AI 提交新增行数 / 提交新增总行数
明确人工新增占比 = 明确人工提交新增行数 / 提交新增总行数
未知归因新增占比 = 未知归因提交新增行数 / 提交新增总行数
```

- 分母为零时占比显示“不适用”或 NULL，不强行显示 0%。
- 时间维度使用 committed_at；event_timestamp 和云端 create_time 用于事件延迟与投递延迟分析。
- 三类新增占比之和应为 100%（允许显示舍入误差）。人工行数不能用“总量减 AI”替代，因为剩余量还包含 unknown。
- 工具/模型贡献通过展开 tool_model_breakdown 后聚合其 ai_additions。不要在展开明细后重复累加父记录的 git_diff_added_lines、human_additions 等字段。
- 展示每次提交时，以 repo_id + commit_id 关联；本地新 event_id 不能自动证明是新的 Git 提交。
- 当前 commit 没有按作者类别细分的删除字段，不能推导出“AI 提交删除行数”或“人工提交删除行数”。
- “AI 提交新增占比”不等于“AI 生成采纳率”。不能简单用 commit.ai_additions / checkpoint.lines_added 计算采纳率，因为事件时间、重复编辑及恢复记录口径不同。

### 7.4 对现有 CSV 表层字段的映射建议

| CSV 表层字段 | 推荐处理 |
|---|---|
| event_type | 从 complete_data.event_type 提取 |
| ai_tools | 可作为 tool 的展示列；不可作为 AI/人工分类依据；commit 多工具场景以明细数组为准 |
| ai_lines_added | 若定义为 AI 编辑新增量，仅对 AI 类型 checkpoint 提取 lines_added |
| ai_lines_deleted | 若定义为 AI 编辑删除量，仅对 AI 类型 checkpoint 提取 lines_deleted |
| ai_additions | 对 commit 提取 ai_additions |
| human_additions | 对 commit 提取 human_additions，含义限定为明确人工 |
| complete_data | 保留完整原始事件，用于审计、重新映射及统计校验 |

建议额外提供 kind、measurement_mode、unknown_additions 等可查询字段。若沿用一张表，不适用于某类事件的统计列宜为 NULL，避免 0 同时表示“没有发生”“不适用”和“没有映射”。

### 7.5 本次示例数据如何统计

2026-09-08 导出的样本中，排除模拟数据并按 event_id 去重后：

| 报表 | 归因类别 | 新增 | 删除 | 说明 |
|---|---|---:|---:|---|
| checkpoint 直接编辑 | AI | 12 | 0 | CodeBuddy 对 HookProbe.kt 的编辑 |
| checkpoint 直接编辑 | 未知 | 1867 | 1 | apm.yml 为 +3/-0，apm.lock.yaml 为 +1864/-1 |
| checkpoint 直接编辑 | 明确人工 | 0 | 0 | 样本没有 known_human 事件；不代表现实中没有人工操作 |
| commit 最终提交 | AI | 12 | — | bf41da7 提交，重复投递只计一次 |
| commit 最终提交 | 明确人工 | 0 | — | 本次提交对应字段为 0 |
| commit 最终提交 | 未知 | 0 | — | apm 配置的未提交变化不进入这次提交统计 |

该提交新增总行数为 12，删除总行数为 0，AI 提交新增占比为 100%。checkpoint 的 12 行与 commit 的 12 行不能相加成 24 行。表中的“—”表示当前协议不提供按归因类别细分的提交删除行数。
