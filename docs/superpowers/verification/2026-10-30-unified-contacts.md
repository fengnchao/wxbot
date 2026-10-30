# 统一联系人验证与启用

日期：2026-10-30。代码实施完成；本机运行数据库尚未迁移，现有服务未重启。

## 已验证

- 统一会话记录生成监听、角色/心跳、订阅投影；迁移后不回读或双写旧名单。
- 同名个人跨群和私聊共用记忆，保存各群昵称、原成员绑定、旧 ID 跳转及停用状态。
- 冲突记忆保留不同值及来源；模型读取、记忆搜索、管理员查看一致；编辑普通记忆不会在后续合并时恢复旧值。
- 个人改名按当前姓名/群昵称判断同名归并；历史名称只参与查询。
- 身份编辑及发现新成员同步更新统一版本，旧表单不能覆盖新修改；运行时发现的私聊可以复用原绑定补充实际目的地。
- 迁移只读预览、SQLite 一致性备份、临时库事务导入与发布、失败回滚和重复执行已通过测试。
- 只有监听/策略/订阅来源的记录不丢失；被动观测不会自动开启监听、心跳或订阅；缺少路由资料可在待补充筛选中完善。
- 普通启动不自动激活；直接/外部模式保留本机通道编辑，自定义数据库冲突在预览中阻止。
- 新联系人页、旧链接跳转、来源只读、保存版本冲突及记忆对话框通过离线 DOM/API 检查。

## 测试结果

完整离线 pytest：**1229 passed, 3 failed，88.76 秒**。

以下 3 项失败在修改前的提交 ae4fc0784e952a2d1fc0c403202877b78fb4ec93 已独立复现，本次未修改对应队列或输入实现：

1. `tests/test_queue_admin.py::test_multipart_cli_sent_and_retry_preserve_other_parts`：批次实际状态 done，预期 waiting_delivery。
2. `tests/test_queue_store.py::test_user_confirmed_actual_text_is_deferred_and_does_not_release_running_old_worker`：批次实际状态 done，预期 uncertain。
3. `tests/test_typing.py::test_typing_steps_keep_half_second_between_batches_and_one_final_enter`：0.49 秒时实际发生两次粘贴，预期一次。

`node tests/contacts_frontend_checks.js`、`node tests/log_frontend_checks.js` 均通过。`git diff --check` 通过，仅 Git 行尾转换提示。

独立代码审查发现的 3 项重要问题均先复现失败，再修复并通过回归：群昵称匹配改名、身份编辑版本失效、发现的私聊补充目的地。未进行真实微信发送或真实 UI @ 操作验证。

## 当前安装的只读核对

预览无阻塞错误：7 个收发会话、19 个旧身份绑定、33 条群昵称记录、2 份角色策略、3 个订阅目的地。

在项目 cache 中的临时数据库副本进行迁移演练，得到：21 位联系人、2 个群会话、11 组身份合并；保留全部 2 份角色策略及 3 个订阅目的地，无冲突记忆。副本不作为新的安装或运行数据来源，不包含复制的认证文件。

## 人工启用

先自行停止 Butler、log、wxbot 及仍在写入旧数据的心跳、新闻、Telegram、看门狗等后台进程。迁移程序不停止或重启已有服务。

在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -m butler contacts-preview --directory D:\work\code\wxbot
.\.venv\Scripts\python.exe -m butler contacts-migrate --directory D:\work\code\wxbot --acknowledge-stopped
.\.venv\Scripts\python.exe -m butler start
```

迁移命令检查配置的服务端口空闲，先创建原库和本机配置备份，再发布临时库结果。报告中的 `backup.directory`、`backup.database`、`backup.manifest` 指向本次备份。备份含本机私有配置，应留在安装者本机，禁止提交或外传。

启动后打开 log 的「联系人」页面，核对姓名、各群昵称、监听、角色/心跳、订阅和记忆。旧 JSON/TOML 名单保留为历史来源，成功激活后不再参与联系人读写。

回退需先停止写入者，再恢复同一批数据库与配置备份；启用后如已有新修改，先核对并导出增量。完整说明见 [安装与升级](../../CODEX_INSTALL.md#升级现有安装)。
