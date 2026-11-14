# Codex ↔ DSH Chat

让 **Codex Desktop** 和 **DeepSeek Harness (DSH)** 向明确指定的现有对话发送消息、关联回复并核对回执。

This repository contains a reusable agent Skill and a local Linux messaging helper. It routes by exact conversation IDs and keeps accepted, delivered, acknowledged, and uncertain outcomes separate.

## 内容

- [`skills/codex-dsh-chat/SKILL.md`](skills/codex-dsh-chat/SKILL.md)：助手工作流程与触发条件。
- [`scripts/chat.py`](skills/codex-dsh-chat/scripts/chat.py)：会话列表、配对、单次发送、回复和回执核对。
- [`runtime.md`](skills/codex-dsh-chat/references/runtime.md)：运行条件、环境变量、认证复用、存储和兼容边界。
- [`tests/test_chat.py`](tests/test_chat.py)：本机隔离测试，不连接真实助手、不发送消息。

## 安装 Skill

审阅文件后，把 `skills/codex-dsh-chat` 整个目录复制到你的助手技能目录。Codex 用户技能目录可使用 `~/.agents/skills/codex-dsh-chat`。不要覆盖已有同名技能。DSH 的技能发现位置取决于其运行配置；也可以直接给它此 Skill 的路径和脚本入口。

安装文件不代表当前聊天已重新加载。可在支持 Skill 发现的新聊天中调用 `$codex-dsh-chat`。

## 使用

需要现有 Codex Desktop、DSH web 服务和两侧适用的用户授权；依赖与配置见 [runtime.md](skills/codex-dsh-chat/references/runtime.md)。

```bash
cd skills/codex-dsh-chat
python3 scripts/chat.py --help
python3 scripts/chat.py list dsh --search '会话标题'
python3 scripts/chat.py list codex --codex-context YOUR_CODEX_UUID --search '对话标题'
python3 scripts/chat.py pair discussion --codex YOUR_CODEX_UUID --dsh session-YOUR_DSH_UUID
python3 scripts/chat.py send --pair discussion --from codex --id question-001 --message '请核对方案并带标记回复。'
python3 scripts/chat.py wait question-001 --timeout 60
```

DSH 回发：

```bash
python3 scripts/chat.py send --pair discussion --from dsh --id answer-001 --in-reply-to question-001 --message '我的核对意见是……'
python3 scripts/chat.py wait answer-001 --timeout 60
```

替换示例中的 ID。双方共享同一个私有 state 目录；新默认目录在 `~/.local/state/codex-dsh-chat`（遵循 `XDG_STATE_HOME`）。继续旧部署时显式使用原 `--state-dir`，保留旧 ID 的防重发证据。

`ACKNOWLEDGED` 表示已读回发送正文及其后的关联助手确认，不代表正文中的工作已完成。`UNKNOWN` 或残留 `SUBMITTING` 要核对，不能换 ID 重发。`wait` 超时不会把已接受的投递改报为失败。

每次 `send` 只投递一条消息。没有自动无限互聊、开机服务或模型配置修改。消息来源标签不构成身份认证或新增授权。

## 验证

```bash
python3 -m unittest discover -s tests -v
```

原本机实现于 2026-11-12 完成一次真实双向通信；公开包的适配差异和验证限制见 runtime.md。仓库不包含真实会话 ID、聊天内容、运行回执、认证文件或供应商程序副本。
