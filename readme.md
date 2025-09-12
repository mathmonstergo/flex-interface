
# flex_interface

flex_interface 是一个基于 MCDReforged 的 Minecraft 服务器 QQ 群与游戏内互通插件，支持签到、道具、经济同步、AI 聊天等多种功能。

## 功能简介

- QQ 群与 MC 聊天互通
- QQ 群签到、幸运值、道具奖励
- 道具整蛊、出售、盲盒等互动玩法
- 经济（绿宝石）与 CMI 插件同步
- AI 自动聊天与话题生成
- 多群组支持、权限与频率控制

## 目录结构

```
flex_interface/
    __init__.py
    main.py
    bot_command_exec.py
    command_exec.py
    handler_db_bind.py
    handler_db_sign.py
    handler_effect_cmd.py
    manager_autochat.py
    manager_config.py
    manager_dbclient.py
    manager_wsclient.py
    utils.py
    config.json
    debug.log
```

## 安装与配置

1. **依赖环境**
   - Python 3.8+
   - MCDReforged
   - MySQL 数据库（用于数据持久化）

2. **安装插件**
   - 将 `flex_interface` 文件夹放入 MCDReforged 的 `plugins` 目录下。

3. **配置数据库**
   - 修改 `flex_interface/config.json`，填写数据库连接信息和相关参数。

4. **启动插件**
   - 启动 MCDReforged，插件会自动初始化数据库表结构。

## 常用指令

- `签到`：每日签到，获取幸运值和奖励
- `我的信息`：查询个人签到、道具、绿宝石等信息
- `出售 <道具名> <数量>`：出售道具换取绿宝石
- `绑定 <游戏ID>`：绑定 QQ 与 MC 账号
- `解绑 <游戏ID>`：解绑账号
- `在线`：查询当前在线玩家
- `行情`：查询今日道具出售行情

## 主要文件说明

- [`main.py`](flex_interface/main.py)：插件主入口，事件处理与消息分发
- [`bot_command_exec.py`](flex_interface/bot_command_exec.py)：QQ 指令处理
- [`handler_db_sign.py`](flex_interface/handler_db_sign.py)：签到与道具数据库逻辑
- [`handler_db_bind.py`](flex_interface/handler_db_bind.py)：账号绑定逻辑
- [`manager_autochat.py`](flex_interface/manager_autochat.py)：AI 聊天与上下文管理
- [`utils.py`](flex_interface/utils.py)：工具函数与消息构建

## 数据库结构

插件会自动创建所需表，无需手动建表。主要表有：

- `player_bindings`：QQ 与 MC 账号绑定关系
- `player_daily_sign`：签到与道具记录
- `sign_reward_logs`：签到奖励日志
- 其他相关表

## 全文由Github Copilot编写

欢迎提交 issue 或 PR 进行功能建议和 bug 反馈。

---

如需详细开发文档或二次开发，请参考各模块源码注释。