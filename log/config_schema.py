"""Field descriptions and validation shared by the dashboard reader and writer."""
import math
from urllib.parse import urlsplit

LABELS={
 'provider':('模型运行时','codex 或 hermes；保存后需自行重启 Butler。'),
 'data_dir':('Butler 数据目录','相对路径按 Butler 配置文件目录解析。'),
 'plugin_root':('Codex 插件目录','留空使用项目内 butler-wechat 插件；插件需匹配协议版本。'),
 'max_workers':('Codex 最大进程数','同时驻留的模型 worker 上限，范围1–8。'),
 'idle_seconds':('Codex 空闲回收（秒）','闲置运行时在后续请求时回收，会话记录保留。'),
 'url':('服务 API 地址','服务调用的基础地址；需要包含 http:// 或 https://。'),
 'api_key':('API Key','调用接口使用的密钥；原值不会回显。'),
 'token':('接口 Token','服务间认证令牌；通信两端需要保持一致。'),
 'host':('监听地址','本服务启动时绑定的主机或IP地址。'),
 'port':('监听端口','本服务启动时使用的端口。'),
 'model':('模型名称','发送给模型接口的 model 参数。'),
 'timeout':('请求超时（秒）','一次服务请求允许等待的最长时间。'),
 'root':('Hermes 数据目录','用于读取技能、档案、分组、心跳及日志文件。'),
 'send_identity':('发送用户身份','将微信会话身份提供给 Hermes。'),
 'profile_in_path':('地址包含 Profile','接口路径使用 /p/{profile}/v1/。'),
 'contacts':('联系人映射','JSON数组：微信名称 name、Profile profile、ASCII用户ID uid，可附 label/session_key。'),
 'bound_users':('绑定的私聊用户','微信会话名称列表；全部监听开启时不限制为此列表。'),
 'bound_groups':('绑定的群聊','微信群名称列表；群消息需要明确@机器人。'),
 'mention_names':('机器人群昵称','用于识别@机器人的昵称列表。'),
 'poll_interval':('未读轮询间隔（秒）','读取微信未读状态的间隔。'),
 'reply_delay_min':('最短回复等待（秒）','完整回复进入发件箱后的随机等待下限。'),
 'reply_delay_max':('最长回复等待（秒）','随机等待上限，不得小于下限。'),
 'command_prefix':('命令前缀','以此前缀开头的消息按命令处理。'),
 'database':('收发队列文件','相对路径按项目目录解析；切换文件会切换查看和运行的队列。'),
 'quiet_seconds':('连续消息合并间隔（秒）','最后一条消息后等待多久再合并提交。'),
 'max_wait_seconds':('最长合并等待（秒）','连续发言时单批允许等待的最长时间。'),
 'confirm_timeout':('发送确认等待（秒）','回车后等待新增自己消息气泡的时间。'),
 'max_model_requests':('模型并发数','同时等待 Butler/模型回复的请求数，微信界面仍串行收发。'),
 'failure_discard_seconds':('失败丢弃等待（秒）','从首次发送失败起计时，到期结束整轮剩余分块并保留记录。修改后现有失败任务也使用新期限。'),
 'chunk_chars':('长回复分块字数','普通聊天默认整条发送，超过此长度才分块；链接、代码不会截断，范围100–2000。'),
 'restart_chat_policy':('聊天重启恢复策略','discard=停止旧聊天回复续发；resume=恢复尚未开始的回复；结果不确定的不自动重发。新闻和提醒不受此项影响。'),
 'chunk_size':('每批粘贴字数','每次输入到微信输入框的字符数。'),
 'chunk_interval':('分批粘贴间隔（秒）','两批正文输入之间的等待时间。'),
 'enabled':('启用','开启或关闭此功能。'),
 'backend':('模型后端','butler、hermes、openai、ollama 或 echo。'),
 'max_history':('历史消息数量','提交模型时保留的历史条数。'),
 'system_prompt':('系统提示词','发送给模型的系统提示内容。'),
 'mode':('微信监听模式','main=主窗口，independent=独立聊天窗口。'),
 'listen_all':('监听全部会话','开启后处理所有私聊，群聊仅处理@机器人。'),
 'max_scan_pages':('寻找会话最大页数','存在待收发任务时寻找目标会话的页数上限。'),
 'switch_timeout':('切换会话等待（秒）','点击会话后等待目标标题出现。'),
 'window_class':('窗口类名','微信UI自动化控件定位条件。'),
 'chat_tab_name':('聊天入口名称','微信左侧聊天入口的控件名称。'),
 'session_list_id':('会话列表控件ID','微信左侧聊天对象列表的AutomationId。'),
 'search_depth':('控件搜索深度','查找微信控件的最大层级。'),
 'control_type':('控件类型','UI自动化定位使用的控件类型。'),
 'automation_id':('控件ID','UI自动化定位使用的AutomationId。'),
 'class_name':('控件类名','UI自动化定位使用的ClassName。'),
 'name':('控件名称','UI自动化定位使用的名称。'),
 'avatar_size':('群成员头像尺寸','用于区分群成员的头像采样尺寸。'),
 'avatar_left_offset':('头像水平偏移','群成员头像采样区域的水平偏移。'),
 'avatar_top_offset':('头像垂直偏移','群成员头像采样区域的垂直偏移。'),
 'member_names':('群成员昵称映射','稳定头像ID到真实昵称的JSON映射。'),
 'strip_width':('头像检测宽度','判断左右消息位置时采样的边缘宽度。'),
 'diff_threshold':('像素差阈值','与背景颜色差达到阈值才计为头像像素。'),
 'min_pixels':('最少头像像素','判定发送方所需的最少非背景像素数。'),
 'actions_enabled':('允许执行指令','允许 Butler 解析并执行模型返回的 action。'),
 'script_dir':('工具脚本目录','Butler 本地动作脚本所在目录。'),
 'respond_after_action':('工具执行后再组织回复','将执行结果再次交给模型生成用户回复。'),
 'flow_file':('消息流水文件','留空时按当前模型后端的数据目录推导。'),
 'file':('分组文件','用户分组JSON的路径，留空时使用默认位置。'),
 'config_file':('角色心跳配置文件','用户角色、工具白名单及心跳开关JSON路径。'),
 'state_file':('心跳状态文件','保存下次计划执行时间。'),
 'audit_file':('心跳记录文件','保存心跳执行过程记录。'),
 'min_interval_minutes':('心跳最短间隔（分钟）','随机心跳等待下限。'),
 'max_interval_minutes':('心跳最长间隔（分钟）','随机心跳等待上限。'),
 'role_skill':('角色 Skill','角色技能名称，需要带 butler-role 标签。'),
 'allowed_skills':('工具 Skill 白名单','允许此用户调用的工具技能列表，不包含角色技能。'),
 'heartbeat_enabled':('开启心跳','允许随机心跳选择此用户。'),
 'users':('用户角色与心跳策略','用户到角色、工具白名单和心跳开关的JSON映射。'),
 'groups':('用户分组','分组编号到微信会话名称列表的JSON映射。'),
 'home':('运行数据目录','Codex 独立登录目录或 log 的运行数据来源，依所在配置分组生效。'),
 'wxbot_config':('wxbot 配置文件','log 下次启动读取和维护的wxbot配置文件；留空使用项目默认。'),
 'butler_config':('Butler 配置文件','log 下次启动读取和维护的Butler配置文件；留空使用项目默认。'),
 'groups_file':('log 分组文件','log 下次启动使用的分组文件；留空使用默认。'),
}


def row_metadata(source,path,value,*,default_available=False):
    key=path[-1]
    label,description=LABELS.get(key,('扩展参数 · '+key,'配置文件中的扩展参数，保存时保留原有数据类型。'))
    if 'member_names' in path:label,description='群成员昵称 · '+key,'稳定成员ID对应的显示昵称。'
    if source in {'groups','log_groups'} and key.isdigit():label,description='分组 '+key,'此分组包含的微信会话名称列表。'
    if source=='butler' and tuple(path)==('codex','home'):
        label,description='Codex 独立登录目录','机器人自己的 Codex 登录和会话目录；不能指向他人的认证目录。'
    if source=='log_config' and key=='home':
        label,description='log 数据来源目录','看板读取业务数据的目录；不改变 Butler 的数据位置。'
    editor=('boolean' if type(value) is bool else 'integer' if type(value) is int else
            'number' if type(value) is float else 'json' if isinstance(value,(list,dict)) else 'string')
    effect=('保存后立即用于后续角色/心跳检查' if source in {'policies','log_policies'} else
            '保存后立即用于后续分组读取' if source in {'groups','log_groups'} else
            '保存后需自行重启 '+{'wxbot':'wxbot','butler':'Butler','log_config':'log'}.get(source,source))
    choices={('butler','agent','provider'):['codex','hermes'],
             ('wxbot','model','backend'):['butler','hermes','openai','ollama','echo'],
             ('wxbot','queue','restart_chat_policy'):['discard','resume'],
             ('wxbot','wechat','mode'):['main','independent']}.get((source,*path))
    widget='contacts' if source=='butler' and tuple(path)==('contacts',) else (
        'string-list' if isinstance(value,list) and all(isinstance(v,str) for v in value) else editor)
    return {'path':list(path),'label':label,'description':description,'editor':editor,'widget':widget,
            'choices':choices,'editable':True,'effect':effect,'default_available':default_available}


def validate_value(path,value,reference):
    name='.'.join(path)
    good=(type(value) is type(reference))
    if type(reference) is float:good=type(value) in (int,float)
    if not good:raise ValueError(name+' 的数据类型不正确')
    key=path[-1]
    if isinstance(value,str) and ('\x00' in value):raise ValueError(name+' 包含无效字符')
    if type(value) in (int,float):
        if not math.isfinite(value):raise ValueError(name+' 必须是有限数值')
        if key=='port' and (type(value) is not int or not 1<=value<=65535):raise ValueError(name+' 端口范围为1–65535')
        nonnegative={'quiet_seconds','reply_delay_min','reply_delay_max','max_history'}
        positive={'port','timeout','poll_interval','max_wait_seconds','confirm_timeout','max_model_requests',
                  'failure_discard_seconds','chunk_size','chunk_interval','max_scan_pages','switch_timeout','search_depth',
                  'avatar_size','strip_width','diff_threshold','min_pixels','min_interval_minutes','max_interval_minutes'}
        if (key in nonnegative and value<0) or (key in positive and value<=0):raise ValueError(name+' 数值超出允许范围')
    if key=='url' and isinstance(value,str):
        try:
            u=urlsplit(value)
            valid=u.scheme in {'http','https'} and bool(u.hostname) and u.port!=0 and not u.username and not u.password
        except ValueError:valid=False
        if not valid:raise ValueError(name+' 必须是有效的HTTP/HTTPS地址，凭据请填独立密钥项')
    if key in {'bound_users','bound_groups','mention_names','allowed_skills'} or (path[0]=='groups' and isinstance(value,list)):
        if any(not isinstance(v,str) or not v.strip() for v in value):raise ValueError(name+' 必须是非空字符串列表')
    if key=='backend' and value not in {'butler','hermes','openai','ollama','echo'}:raise ValueError('模型后端无效')
    if key=='provider' and value not in {'codex','hermes'}:raise ValueError('模型运行时无效')
    if key=='max_workers' and not 1<=value<=8:raise ValueError('Codex 最大进程数范围为1–8')
    if key=='idle_seconds' and value<=0:raise ValueError('空闲回收时间必须为正数')
    if key=='mode' and path[0]=='wechat' and value not in {'main','independent'}:raise ValueError('微信监听模式无效')
