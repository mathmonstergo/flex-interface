from mcdreforged.api.event import MCDRPluginEvents
from mcdreforged.api.types import PluginServerInterface, Info
from mcdreforged.api.all import *
import minecraft_data_api as api
import re
import random
from .utils import *
import threading
import logging
from . import bot_command_exec
from . import command_exec
from .manager_config import config
from .manager_config import group_info
from .manager_dbclient import MySQLManager
from collections import defaultdict
from .handler_db_bind import SimplePendingBindManager
from .handler_db_bind import PlayerBindingManager
from .handler_db_sign import PlayerSignManager
from collections import defaultdict, deque
import time
# 获取 Logger 对象
logger = logging.getLogger("main")
# "出售": {"command": "sell_item", "message_type": "reply", "permission": "default","times_limit": 5},
# "今日行情": {"command": "query_market_trend", "message_type": "reply", "permission": "default","times_limit": 5},
        # "机票": "fly_charge",
            # {"name": "机票", "rarity": 7, "category": "QQ", "base_amount": 1, "sell_price": 500},
class flexInterface:
    def __init__(self, server: PluginServerInterface):
        self.server = server
        self.config = config
        self.group_ids = config.get("group_ids")
        self.group_ids_aync_chat = [g for g in self.group_ids if g not in config.get("group_ids_aync_chat_disable", [])]  # 移除无需消息同步的群
        self.user_message_times = {}
        self.user_last_message = {}
        self.mc_api = api
        self.mysql_mgr = None
        self.binding_mgr = None
        self.pending_bindings = {}
        self.lock = threading.Lock() 
        self.user_command_timestamps = defaultdict(lambda: deque())
    def initialize(self, config_db):
        """统一初始化所有组件"""
        self.__initialize_database(config_db)  # 挂载数据库
        self.__initialize_handlers()  # 获取功能类实体 绑定，签到

    def __initialize_database(self, config_db):
        """私有方法：初始化数据库连接"""
        try:
            self.mysql_mgr = MySQLManager(self.server, config_db)
            self.mysql_mgr.init_sync()  # 同步初始化连接池

            if not self.mysql_mgr.test_connection():
                raise RuntimeError("MySQL连接测试未通过")

            self.server.logger.info("Mysql已挂载到flexInterface")
        except Exception as e:
            self.server.logger.critical(f"数据库初始化失败: {str(e)}")
            raise

    def __initialize_handlers(self):
        """初始化业务管理器(需要与数据库交互的), 绑定，道具指令，签到奖励"""
        if not self.mysql_mgr:
            raise RuntimeError("需要先初始化数据库连接")
        self.binding_mgr = PlayerBindingManager(self.mysql_mgr)
        self.pending_bind_mgr = SimplePendingBindManager()
        self.sign_handler = PlayerSignManager(self.server, self.mysql_mgr, self.binding_mgr, config.get("prize_config"))
    
    
    def parse_message(self, content, prefix_to_match=["world", "Mainland"]):
        # 如果提供了 prefix_to_match，检查 [prefix] 是否在 prefix_to_match 列表中
        for prefix in prefix_to_match:
            prefix_pattern = r"^\[" + re.escape(prefix) + r"\]"
            if re.match(prefix_pattern, content):  # 匹配到一个符合的 prefix
                # 解析玩家消息：[prefix]player_name: message
                player_message_pattern = r"^\[[^\]]+\][^:]+: .*$"
                match = re.match(player_message_pattern, content)
                
                if match:
                    # 提取 prefix、player_name 和 message
                    prefix_player_message_pattern = r"^\[(.*?)\](.*?): (.*)$"
                    inner_match = re.match(prefix_player_message_pattern, content)
                    
                    if inner_match:
                        prefix = inner_match.group(1).strip()         # 获取 [prefix] 中的部分
                        player_name = inner_match.group(2).strip()   # 获取玩家名
                        message = inner_match.group(3)       # 获取玩家的消息
                        
                        # 返回三个变量
                        return prefix, player_name, message

        # 如果没有匹配到，返回三个空字符
        return '', '', ''

    def on_info(self, server_interface: PluginServerInterface, info: Info):
        """处理 Minecraft 服务器事件"""
        prefix, player, message = self.parse_message(info.content)
        # prefix = ''
        # message = ''
        # if info.is_player:
        #     player = info.player
        #     message = info.content
        if message:
            if message != "确认绑定":
                threading.Thread(target=self.handle_on_info, args=(prefix, player, message)).start()
            else:
                threading.Thread(target=self._handle_binding_confirmation,args=(player,)).start()

    def on_server_start(self, server_interface: PluginServerInterface):
        """服务器启动事件"""
        self.server.logger.info("服务器已启动")
        self.handle_server_start()
        
    def on_server_stop(self, server_interface: PluginServerInterface, *_):
        """服务器停止事件"""
        self.server.logger.info("服务器已停止")
        self.handle_server_stop()

    def on_player_joined(self, server_interface: PluginServerInterface, player: str, _):
        """玩家加入事件"""
        self.server.logger.info(f"玩家 {player} 加入了游戏")
        threading.Thread(target=self.handle_player_join, args=(player,)).start()

    def on_player_left(self, server_interface: PluginServerInterface, player: str):
        """玩家离开事件"""
        self.server.logger.info(f"玩家 {player} 离开了游戏")
        threading.Thread(target=self.handle_player_left, args=(player,)).start()

    def on_player_death(self, server: PluginServerInterface, player, event, content):
        """处理玩家死亡事件"""
        for i in content:
            if i.locale == 'zh_cn':  # 指定语言
                killer = i.killer
                weapon = i.weapon
                self.server.logger.info(i.raw)
                self.handle_player_death(i.raw)

    def on_player_advancement(self, server: PluginServerInterface, player, event, content):
        player: str = player  # 玩家名
        event: str = event  # 成就类型（翻译键名称）
        for i in content:
            if i.locale == 'zh_cn':  # 需要明确指定你要使用哪种语言
                advancement = i.advancement
                self.handle_player_advancement(i.raw)  # 转发原版成就消息文本

    def handle_on_info(self, prefix: str, player: str, message: str):
        message_type = "default"
        message_formated = f"{player}: {message}"
        if prefix == "Mainland":
            message_formated = f"[主城] {player}: {message}"
        elif prefix =="world":
            message_formated = f"[生存] {player}: {message}"
        elif prefix == "world_nether":
            message_formated = f"[地狱] {player}: {message}"
        elif prefix == "world_the_end":
            message_formated = f"[末地] {player}: {message}"
        payload = build_payload(message_type, self.group_ids_aync_chat, message_formated)
        
        self.server.wscl.send_group_message(payload)

        ai_response = self.server.chat.generate_ai_response(context=message, source="MC玩家",user=player)
        if ai_response:
            message_2 = f"{ai_response}"
            payload_2 = build_payload(message_type, self.group_ids_aync_chat, message_2)
            self.server.wscl.send_group_message(payload_2)
            send_to_mc_message = {
                "text": "",
                "extra": [
                    {"text": f"[Creep] {ai_response} "}
                ]
            }
            self.server.execute(f'tellraw @a {json.dumps(send_to_mc_message, ensure_ascii=False)}')

    def _handle_binding_confirmation(self, player_name: str):
        """处理玩家确认绑定的回调（线程中执行）"""
        try:
            with self.lock:
                if player_name not in self.pending_bindings:
                    message_to_mc = {
                    "text": f"[绑定系统] 当前没有绑定请求，或绑定请求已超时",
                    "color": "yellow",
                    }
                    self.server.execute(f"tellraw {player_name} {json.dumps(message_to_mc)}")
                    return  # 没有对应的绑定请求
                # 获取绑定请求信息
                user_id, group_id, msg_id, timestamp = self.pending_bindings.pop(player_name)
                # 关键检查：是否超时
                if time.time() - timestamp > 60:
                    payload = build_payload("reply", group_id, f"⏰ 绑定请求已超时（超过60秒未确认）", msg_id)
                    self.server.wscl.send_group_message(payload)
                    return
            # 执行最终绑定
            message_to_qq = self.binding_mgr.bind_account(user_id, player_name)
            payload = build_payload( "reply",group_id, message_to_qq, msg_id, user_id)
            self.server.wscl.send_group_message(payload)
            if "成功" in message_to_qq:
                message_to_mc = {
                "text": f"[绑定系统] 已成功将 {player_name} 绑定至QQ: {user_id}",
                "color": "green",
                }
            self.server.execute(f"tellraw {player_name} {json.dumps(message_to_mc)}")
            
        except Exception as e:
            self.server.logger.error(f"绑定确认回调出错: {str(e)}")

    def handle_server_start(self):
        """处理服务器启动事件"""
        message_type = "default"
        message = "[CQ:face,id=185] 服务器已启动完成~"
        payload = build_payload(message_type, self.group_ids_aync_chat, message)
        self.server.wscl.send_group_message(payload)
        # =========== 启动时同步经济插件的余额==========
        try:
            self.sign_handler.sync_balance_from_cmi()  # 该方法仅将CMI的经济缓存到cache_current
        except Exception as e:
            self.server.logger.error(f"绿宝石同步失败: {str(e)}", exc_info=True)
        try:
            # 检测当前时间， 设置周五-周日双倍经验
            current_weekday = time.localtime().tm_wday  # 获取当前是星期几，0表示星期一，6表示星期天
            self.server.logger.info(f'当前星期{current_weekday}')
            if current_weekday in [4, 5, 6]:  # 如果是就开启
                if not self.server.xpboost_status:
                    bot_command_exec.double_xp(self)
        except Exception as e:
            self.server.logger.error(f"双倍经验设置失败: {str(e)}", exc_info=True)
    def handle_server_stop(self, *_):
        """处理服务器停止事件"""
        message_type = "default"
        message = "[CQ:face,id=187] 服务器已停止运行~"
        payload = build_payload(message_type, self.group_ids_aync_chat, message)
        self.server.wscl.send_group_message(payload)

    def handle_player_join(self, player: str):
        """处理玩家加入事件"""
        message_type = "default"
        message = f"[CQ:face,id=151] {player}开始摸鱼了~"
        payload = build_payload(message_type, self.group_ids_aync_chat, message)
        self.server.wscl.send_group_message(payload)
        self.sign_handler.apply_emerald_to_player_on_join(player)  # 玩家加入时同步绿宝石账户
        bot_command_exec.show_xprate(self, player)  # 玩家加入时显示当前经验倍率
        
    def handle_player_left(self, player: str):
        """处理玩家离开事件"""
        message_type = "default"
        message = f"[CQ:face,id=151] {player}停止了摸鱼~"
        payload = build_payload(message_type, self.group_ids_aync_chat, message)
        self.server.wscl.send_group_message(payload)
        self.sign_handler.sync_balance_from_cmi()  # 每当玩家退出,统一将CMI的经济缓存到cache_current(cmi也是在玩家退出后才更新economy字段)

    def handle_player_death(self, message):
        """处理玩家死亡事件"""
        message_type = "default"
        message = "[CQ:face,id=37] " + message
        payload = build_payload(message_type, self.group_ids_aync_chat, message)
        self.server.wscl.send_group_message(payload)

    def handle_player_advancement(self, message):
        """处理玩家成就事件"""
        message_type = "default"
        message = "[CQ:face,id=160] " + message
        payload = build_payload(message_type, self.group_ids_aync_chat, message)
        self.server.wscl.send_group_message(payload)

    #==============================QQ2MC===============================

    def __handle_text__(self, group_id, user_id, nickname, card, message_id, message_content, group_name=None):
        """
        处理/过滤信息
        如果是指令，先处理带参数的指令，再处理不带参数的指令制作方法
        """
        payload = None
        message = None
        # 初始化变量
        reply = False
        at_target = None
        at_qq = None
        at_parts = []
        parts = []
        at_def = ""
        text_content = ""
        text_to_auto_chat = ""
        # 识别回复/@消息的格式
        self.server.logger.debug(message_content)
        for item in message_content:
            item_type = item.get("type")
            item_data = item.get("data", {})

            if item_type == "reply":
                reply = True  # 标记为回复消息

            elif item_type == "at":
                at_target = item_data.get("name")
                at_qq = item_data.get("qq")
                text_to_auto_chat = at_target + ":"
            elif item_type == "text":
                text_content += item_data.get("text", "")
                text_to_auto_chat += item_data.get("text", "")
                parts = text_content.strip().split(maxsplit=2)
                if at_target:
                    at_def = "at"
                    at_parts = text_content.strip().split(maxsplit=1)
            elif item_type == "face":
                face_id = item_data.get("id")
                text_content += f"[表情:{face_id}]"
                text_to_auto_chat += text_content
            elif item_type == "image":
                image_url = item_data.get("url", "")
                text_content += f"[图片:{image_url}]"
                text_to_auto_chat += "[图片]"
            elif item_type == "video":
                image_url = item_data.get("url", "")
                text_content += f"[视频:{image_url}]"
                text_to_auto_chat += "[视频]"
            elif item_type == "record":
                voice_url = item_data.get("url", "")
                text_content += f"[语音:{voice_url}]"
                text_to_auto_chat += "[语音]"
        command_from_qq, _ = parse_text(text_content)
        command_config = config.get("command_config", {})
        first_param = parts[0] if len(parts) > 0 else None  # 一般是指令类型
        second_param = parts[1] if len(parts) > 1 else None  
        third_param = parts[2] if len(parts) > 2 else None
        # ========================  使用@ 道具的args ============================
        args = []
        if at_target and at_qq != config.get("bot"):  # 如果@玩家
            command_from_qq = at_def  # 如果有@ 则使用另一种读取指令的方式
            at_command = at_parts[0] if len(at_parts) > 0 else None
            second_param = at_parts[1] if len(at_parts) > 1 else None
            args = [at_qq] + [at_command] + [card] + [second_param]
                # 被@的qq  +  @的第一个词语 +  发消息人群昵称 + 第二个词语
        # ========================  使用@ 道具的args ============================

        target_config = command_config.get(command_from_qq)
        # 检测是否是 /指令, 如果是正确指令就检查权限
        if target_config and not reply:
            self.server.logger.info("目标指令存在")
            user_id = str(user_id)
            permission = target_config.get("permission")  # 权限
            command_executor = target_config.get("command")  # 指令
            message_type = target_config.get("message_type")  # 回复格式
            times_limit = target_config.get("times_limit") # 每分钟每位用户可执行该指令的最大次数
            now = time.time()
            time_window = 60  # 60秒时间窗口
            user_queue = self.user_command_timestamps[user_id]

            # 清理超过一分钟的记录
            while user_queue and now - user_queue[0] > time_window:
                user_queue.popleft()

            if times_limit and len(user_queue) >= times_limit:
                message = f"你在一分钟内最多只能使用该命令 {times_limit} 次，请稍后再试。"
            else:
                user_queue.append(now)    
                if has_permission(config, user_id, permission):
                    if at_qq and at_qq != config.get("bot"):  # @ 机器人的方法
                        self.server.logger.info("进入command_exec")
                        method_to_call = getattr(command_exec, command_executor, None)
                        if callable(method_to_call):
                            message = method_to_call(self, user_id, args)
                    else:
                        self.server.logger.info("进入bot_command_exec")
                        method_to_call = getattr(bot_command_exec, command_executor, None)
                        if callable(method_to_call):
                            message = method_to_call(self, user_id, card, message_id, group_id, first_param, second_param, third_param)
                else:
                    message = "你不能这样命令我"
            if message:  # 处理完毕后有消息就发送到QQ
                payload  = build_payload(message_type, group_id, message, message_id, user_id)

        else:  # 非指令消息直接转发到MC
            if group_id in self.group_ids_aync_chat:  # 过滤不想同步消息的群
                message_from_qq = build_message_from_qq(group_id, card, user_id, reply, text_content, at_target, group_name)
                self.server.execute(f'tellraw @a {message_from_qq}')
        return payload, text_to_auto_chat


    def on_websocket_data(self, data):
        if "post_type" in data:
            post_type = data.get("post_type")
            if post_type == 'message':
                self.server.logger.info("进入handle_websocket_message")
                threading.Thread(target=self.handle_websocket_message, args=(data,)).start()
        elif "echo" in data and data["echo"] is not None:
            self.server.logger.info("进入handle_websocket_echo")
            self.handle_websocket_echo(data)

    def handle_websocket_message(self, data):
        """处理 message"""

        try:
            post_type = data.get("post_type")
            group_id = str(data.get("group_id"))
            self.server.logger.debug(f"data: {data}")

            if post_type == "message" and data.get("message_type") == "group":
                group_ids = self.group_ids
                if group_id in group_ids:
                    group_name = None
                    if group_info:
                        group_name = group_info.get(group_id).get("group_name")
                    user_id = data.get("user_id")
                    nickname = data.get("sender", {}).get("nickname")
                    card = data.get("sender", {}).get("card")
                    if not card:
                        card = nickname
                    message_content = data.get("message", [])
                    message_id = str(data.get("message_id"))

                    if self.should_block_message(user_id, message_content):
                        self.server.logger.info(f"拦截用户 {user_id} 的消息: {message_content}")
                        return
                    
                    self.server.logger.info("进入__handle_text__")
                    payload, text_to_auto_chat = self.__handle_text__(group_id, user_id, nickname, card, message_id, message_content, group_name)
                    
                    if payload:  # 如果指令处理返回了内容,就发送
                        self.server.logger.info("payload构建完毕")
                        self.server.wscl.send_group_message(payload)
                    elif text_to_auto_chat: # 用AI构建payload的内容
                        ai_response = None
                        payload_ai = None
                        ai_response_build = None
                        lucky_number = self.sign_handler.querry_today_sign(user_id)
                        ai_response = self.server.chat.generate_ai_response(context=text_to_auto_chat, source="QQ用户", group=group_id,user=card, lucky_number=lucky_number)
                        if ai_response:  # 如果超时了就不管
                            modes = ["default", "reply", "at"]
                            weights = [60, 20, 20]  # 60% default, 30% reply, 10% at
                            # 按权重随机选择（k=1表示选1个，返回的是列表，取第一个元素）
                            reply_mode = random.choices(modes, weights=weights, k=1)[0]
                            if random.random() < 0.01:
                                reply_mode = "record"
                            payload_ai = build_payload(reply_mode, group_id, ai_response, message_id, user_id)
                            ai_response_build = build_message_from_qq(group_id, config.get("bot_name"), "114514", None, ai_response, None, group_name)
                        else:
                            chance = random.random()
                            if chance < 0.001:  # 几率触发枪毙
                                reply_mode = random.choice(["default", "reply", "at"])
                                payload_ai = build_payload(reply_mode, group_id,"[CQ:face,id=169]", message_id, user_id)
                        if payload_ai:
                            self.server.wscl.send_group_message(payload_ai) # 发送QQ消息
                        if group_id in self.group_ids_aync_chat and ai_response_build:  # 发送至MC
                            self.server.execute(f'tellraw @a {ai_response_build}')
        except Exception as e:
            self.server.logger.error(f"[handle_websocket_message] 处理消息失败: {e}")

    def handle_websocket_echo(self, data):
        """处理 echo, 一般是将echo的data缓存起来"""
        echo = data.get("echo")
        data = data.get("data")
        if echo.startswith("get_group_list"):
            for group in data:
                gid = str(group['group_id'])  # 确保键统一为字符串类型
                if gid not in group_info:
                    new_info = {
                        'group_name': group['group_name'],
                        'member_count': group['member_count'],
                        'max_member_count': group['max_member_count']}
                    if group_info.get(gid) != new_info:
                        group_info[gid] = new_info
            self.server.logger.info(f"已初始化群组信息:{group_info}")
    def on_ws_status_change(self, connected: bool):
        # if connected:
        #     type="default"
        #     info = "苦力仆已上线~"
        #     group_id = config.get("group_ids")
        #     payload = build_payload(type, group_id, info)
        #     self.server.wscl.send_group_message(payload)
        # else:
        #     self.server.logger.warning("[WS 状态] 机器人已断开，等待重连中")
        pass

    def close(self):
        """关闭数据库连接"""
        if self.mysql_mgr.connection:
            self.mysql_mgr.connection.close()  # 使用 connection.close() 来关闭连接
        self.server.logger.info("数据库连接已关闭")

    def should_block_message(self, user_id, message_content):
        """返回 True 表示拦截，False 表示放行"""
        if self.is_frequency_exceeded(user_id):
            return True
        if self.is_repeated_content(user_id, message_content):
            return True
        return False

    def is_frequency_exceeded(self, user_id):
        """检查该用户是否超出发送频率限制"""
        now = time.time()
        times = self.user_message_times.get(user_id, [])
        times = [t for t in times if now - t < 60]  # 只保留最近60秒内的消息时间
        times.append(now)
        self.user_message_times[user_id] = times
        return len(times) > 10  # 如果消息超过10条，则视为频率过高

    def is_repeated_content(self, user_id, message_content):
        """检查该用户是否发送了重复的内容"""
        now = time.time()
        last_info = self.user_last_message.get(user_id)
        if last_info:
            last_message, last_time, repeat_count = last_info
            if message_content == last_message and (now - last_time) < 30:  # 30秒内重复相同消息
                repeat_count += 1
                self.user_last_message[user_id] = (last_message, now, repeat_count)
                if repeat_count > 5:
                    return True  # 内容一样且30秒内发送重复
            else:
                self.user_last_message[user_id] = (message_content, now, 1)
                return False
        else:
            self.user_last_message[user_id] = (message_content, now, 1)
            return False