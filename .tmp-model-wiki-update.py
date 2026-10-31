from pathlib import Path
import re
import runpy
import yaml

root = Path.cwd()
vault = root / 'llm wiki/wxbot'
api = runpy.run_path(str(vault/'scripts/wiki.py'))
Wiki, note_text = api['Wiki'], api['note_text']
wiki = Wiki(root)
record = 'raw/changes/2026-10-31-switchable-models'
if record in wiki.state['records']:
    raise SystemExit('Already ingested; append a correction instead')
changed = []


def src(path, anchor):
    rows = (root/path).read_text(encoding='utf-8-sig').splitlines()
    return dict(path=path, line=next(i for i,s in enumerate(rows,1) if anchor in s), anchor=anchor)


def save(key, meta, body):
    if record not in meta['changes']:
        meta['changes'].append(record)
    meta['last_verified'] = '2026-10-31'
    # Regenerate only the evidence list; preserve semantic body and external table formatting.
    body = re.sub(r'\n## 代码依据\n.*?(?=\n## 入库来源)', '\n## 代码依据\n\n' + '\n'.join(
        f"- `{s['path']}:{s['line']}` — `{s['anchor']}`" for s in meta['sources']) + '\n', body, flags=re.S)
    if f'[[{record}]]' not in body:
        body += f'\n\n[[{record}]]\n'
    path = vault/(key+'.md')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(note_text(meta, body), encoding='utf-8')
    changed.append(key)


for key,(path,meta,text) in wiki.pages.items():
    old = wiki.state['pages'].get(key, {})
    drift = any(api['digest'](wiki.source(s)) != old.get('sources',{}).get(s['path']) for s in meta['sources'])
    if not drift and key not in {'modules/runtime','modules/web','modules/wxbot','modules/butler'}:
        continue
    body = text.split('\n---\n',1)[1]
    for s in meta['sources']:
        s.update(src(s['path'],s['anchor']))
    if key=='modules/butler':
        body += '\n## 可切换后端\n\n统一后端见 [[modules/models]]；本地业务按 uses_local_runtime 初始化，适用于 Codex 和通用模型。旧 Hermes 空 model 配置保留历史远端业务兼容路径。\n'
    if key=='modules/runtime':
        body += '\n## 模型运行支撑\n\n[[symbols/reloadable-backend]] 固定请求代际；model_migration.py 将旧 direct 配置显式迁移为 wxbot→Butler，保留本机私有备份且不启动服务。见 [[modules/models]]。\n'
        meta['sources'] += [src('src/butler/runtime/model_migration.py','def migrate_model_connection(')]
    if key=='modules/web':
        body = body.replace('当前图谱任务只读前端源码，没有 UI 改动。其它页面字段契约仍待建档。','配置管理页现在按模型草稿显示适用字段，保存反馈区分模型热生效和需要重启的字段。见 [[modules/models]]；其它页面字段契约仍待建档。')
        meta['sources'] += [src('web/src/views/ConfigurationView.vue','const backendName =')]
    if key=='modules/wxbot':
        body += '\n## 统一模型通道\n\n有 installation 配置的安装仅允许 model.backend=butler；旧 direct 安装需显式 migrate。模型选择由 Butler 管理，见 [[modules/models]]。\n'
        meta['sources'] += [src('src/wxbot/main.py','def build_processor(')]
    if key=='symbols/butler-handle':
        body += '\n## 请求级模型一致性\n\nhandle 在 [[symbols/reloadable-backend]] 的 request 上下文中固定后端，直到最终结果/流式包和群游标处理结束。配置错误在未发送前明确失败，不自动落回另一个模型。\n'
    if key=='apis/butler-handle-stream':
        body += '\n## 模型配置错误\n\n在模型提交前的配置错误使用 code=model_configuration、retry_safe=True；wxbot 仅在尚无 backend/tool/answer_delta/summary_delta/complete 事件时保留安全重试标记。已提交或部分输出错误仍禁止自动重放。模型切换见 [[modules/models]]。\n'
    save(key,meta,body)


def new(key,kind,title,summary,sources,body):
    meta=dict(type=kind,module='models',coverage='core',summary=summary,last_verified='2026-10-31',sources=[src(*s) for s in sources],changes=[])
    save(key,meta,'# '+title+'\n\n'+body+'\n\n## 代码依据\n\n\n## 入库来源\n')


new('modules/models','module','统一模型后端','Butler 管理可切换模型与服务授权工具，wxbot 只调用 Butler',[
    ('src/butler/backends/__init__.py','def create_backend('),('src/butler/backends/models.py','class LocalModelBackend'),
    ('src/butler/runtime/model_switch.py','class ReloadableBackend'),('src/dashboard/config_schema.py','def row_metadata('),
    ('web/src/views/ConfigurationView.vue','const backendName =')], '''
所属 [[modules/butler]]；微信入口 [[modules/wxbot]] → Butler → codex/hermes/openai/responses/openclaw/cursor/ollama/echo。

`[agent].provider` 选择后端，Codex 读取 `[codex]`；通用后端读取 `[model]` 的 url/model/api_key/timeout/max_history/system_prompt，以及 Cursor executable/work_dir 或 OpenClaw agent。`[hermes]` 兼容旧配置。页面 [[modules/web]] 使用草稿 provider 过滤适用字段，密钥使用既有保持/替换/清空语义。

模型通过 [[symbols/reloadable-backend]] 在后续请求切换；身份、业务库、认证、端口和监听目录仍是启动配置，不随模型重载。配置保存并非网络验证，真实服务可用性需另行授权验证。

[[symbols/local-model-backend]] 对 OpenAI/Responses 支持经 ToolService 许可的原生函数工具；Codex 保留原工具实现。Hermes/OpenClaw/Cursor/Ollama 是完整结果路径，不宣称具有 Butler 原生工具桥；未处理的工具调用会失败。Cursor 始终 ask/sandbox 且独立目录，不执行来自聊天的 CLI 选项。

旧 direct 安装使用 `python -m butler migrate` 显式迁移；迁移仅将本机参数移到 Butler 并备份，禁止把备份提交 Git。业务表结构不变；远端模型对话会话不保证跨后端移植。模型 API Key 不是本地身份授权，见 [[concepts/identity-authority]]。
''')
new('symbols/reloadable-backend','symbol','ReloadableBackend','请求固定后端代际，在途完成后才关闭旧工作进程',[
    ('src/butler/runtime/model_switch.py','class ReloadableBackend'),('src/butler/runtime/model_switch.py','def request('),
    ('src/butler/runtime/model_switch.py','def _refresh(')], '''
所属 [[modules/models]]。`request()` 使用 ContextVar 固定本轮 generation；chat/reset/session_id 复用固定上下文。只复制模型字段，保留启动时服务身份、存储和路径；实际配置文件名由 Config.config_path 保存。

新请求读取配置并按差异构造后端，旧后端在用户计数归零后关闭；在途请求不迁移、不重放。Codex 代际工具凭据映射只在其生命周期内共同有效。解析/构造失败阻止新请求并暴露脱敏错误，保留旧代际供诊断与在途完成。

`runtime_status()` 报实际 backend/model、configured_backend、reload_error、active_requests 与 retiring_backends。数据库身份不随代际重建；消费方 [[symbols/butler-handle]]，相关行为通过临时 fake 后端并发测试验证。
''')
new('symbols/local-model-backend','symbol','LocalModelBackend','原生函数工具走服务签发身份，完整结果才进入历史',[
    ('src/butler/backends/models.py','class LocalModelBackend'),('src/butler/backends/models.py','def _native_chat('),
    ('src/butler/backends/compatible.py','def scope(')], '''
所属 [[modules/models]]，实现 ModelBackend 的 chat/reset/session_id/alive/close。scope 包含后端地址/模型、联系人、记忆/绑定版本、策略与用途；不同成员和 heartbeat 历史隔离。角色由服务目录读取，额外上下文不会授予权限。

OpenAI/Responses 原生工具循环最多 8 轮、32 次调用且受总时间限制。服务端 issue/definitions/call 决定身份、工具白名单、只读和记忆许可；模型不能传入 owner/contact/uid 等身份字段，服务 token 不进入模型上下文。

只接受完整终态；错误、不完整回复、未解决调用不写成功历史或发送正文。工具可能已产生副作用后模型失败，此时标记 retry_safe=False，不能自动重放。其它协议使用 CompatibleBackend 的完整结果实现，见 [[concepts/delivery-state]]。
''')

body='''# 统一 Butler 模型链路与随时切换

## 目标与背景

用户要求 wxbot→Butler→Codex/Hermes/Cursor/API+Key/其它智能体，页面随选择变化，模型运行中可切换。影响与设计见 [[impacts/2026-10-31-switchable-models]]。

## 文件与代码位置

后端工厂、compatible.py/models.py、config.py；runtime/model_switch.py/model_migration.py/upgrade.py；agent/core.py/server.py/heartbeat.py；wxbot/main.py；dashboard 的 config_schema/view/editor、model_stream_view、api/support/jobs；ConfigurationView.vue、smoke 及 web/dist。准确位置见本记录 pages 所列词条的 sources。

## 接口与字段

Butler 处理消息完整回复契约保持，模型选择移到 [agent].provider/[model]/[codex]，runtime 追加实际模型、配置模型、重载错误和在途代际状态。原生工具只通过服务签发身份授权，模型 Key 不授予本地权限。

## 数据库与迁移

无业务表结构变更。通用远端会话仅保存不透明标识；联系人、记忆和提醒继续由 Butler 持有。旧 direct 配置显式迁移、私有备份并修改本机链路，不自动处理真实运行配置。已有工作树安装向导的统一链路改动予以保留并验证。

## 前端消费点

配置页按草稿 provider 显示适用字段，保持/替换/清空密钥原值不回传；模型字段热生效、非模型字段提示手动重启。保留 Vue 壳、主题及用户已有联系人 UI 工作；重新构建 dist 并运行 smoke。

## 测试与异步任务

临时 fake 后端覆盖协议、工具授权、完整结果、身份隔离、并发代际和显式迁移；配置和前端假数据验证见 [[model-switch-verification]]。不发送真实微信，不调用真实模型，不重启业务进程。

## 风险与回滚

这次代码首次加载需使用者手动重启相关进程，之后模型参数才由新代码热切换。失败配置不静默回旧模型；已执行工具而最终回答失败不可重放。未承诺跨模型远端会话连续。回滚代码需同时恢复兼容配置；模型迁移原配置备份只留本机，避免泄漏。旧 Hermes 远端业务模式仍是兼容入口，不自动转换既有业务身份。
'''
(vault/(record+'.md')).parent.mkdir(parents=True,exist_ok=True)
(vault/(record+'.md')).write_text(note_text(dict(type='change',title='统一 Butler 模型链路与随时切换',pages=sorted(changed)),body),encoding='utf-8')
print('Updated graph entries:',len(changed))
