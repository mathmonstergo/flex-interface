
import time
from .utils import *
import online_player_api as ol_api
import datetime
import hashlib

# args = [被@的qq  +  @的第一个词语 +  发消息人的昵称 + 第二个词语]


def bind_player(self, user_id, nickname, message_id, group_id, first_param, second_param, *args) -> str:
    """用户发起绑定的入口"""
    bind_model = self.config.get("bind_model")
    player_name = second_param  # 兼容大小写
    try:
        if player_name:
            if ol_api.check_online(player_name):
                if bind_model == 1:  # 严格绑定
                    # 1. 检查是否已绑定
                    if player_name in self.binding_mgr.get_user_bindings(user_id):
                        return f"您已绑定该角色"

                    if self.binding_mgr.is_player_bound(player_name):
                        return f"{player_name} 已被绑定"

                    # 2. 发送验证请求
                    return _verify_binding(self, user_id, player_name, group_id, message_id)
                
                else:  # 宽松绑定
                    return self.binding_mgr.bind_account(user_id, player_name)
            else:
                return f"玩家 {player_name}(区分大小写) 不在线"
        else:
            return "绑定格式错误，示例：绑定 cjjcbb"
    except Exception as e:
        self.server.logger.error(f"bind_player 出错: {str(e)}")
        return "绑定请求处理失败"

def _verify_binding(self, user_id: str, player_name: str, group_id: int, message_id: int):
    """只发送验证请求，不主动等待，由 on_info 回调处理"""
    try:
        # 存储请求信息（加锁避免竞争）
        with self.lock:
            if player_name in self.pending_bindings:
                return "该角色正在等待其他用户确认绑定"
            self.pending_bindings[player_name] = (user_id, group_id, message_id, time.time())  # 添加待绑定队列
        # 向游戏发送验证请求
        message = {
            "text": f"[绑定系统] QQ {user_id} 请求绑定账户，请在 60 秒内输入「确认绑定」完成操作",
            "color": "green", 
            "bold": False 
        }

        self.server.execute(f"tellraw {player_name} {json.dumps(message)}")
        # 启动60秒后自动清理的线程
        threading.Timer(60.0, _clean_expired_binding, args=(self, player_name,)).start()
        return "✅ 已发送绑定请求, 请登录该账号并在聊天框输入「确认绑定」(60s有效)"

    except Exception as e:
        self.server.logger.error(f"_verify_binding 出错: {str(e)}")
        return "绑定验证请求发送失败"

def _clean_expired_binding(self, player_name: str):
    with self.lock:
        if player_name not in self.pending_bindings:
            return
        # 检查是否真的超时（防止提前被确认）
        _, group_id, msg_id, timestamp = self.pending_bindings[player_name]

        if time.time() - timestamp < 60:
            return
        # 发送超时提示并删除记录
        self.pending_bindings.pop(player_name)
    
    # 发送QQ通知（可选）
    payload = build_payload( "reply", group_id,f"⚠️ 角色 {player_name} 的绑定请求已超时",msg_id)
    self.server.wscl.send_group_message(payload)

def unbind_player(self, user_id, nickname, message_id, group_id, first_param, second_param, *args) -> str:
    """处理解绑命令"""
    player_name = second_param
    if not second_param:
        return "请输入'解绑 游戏ID'进行解除绑定操作。"
    try:
        return self.binding_mgr.unbind_account(user_id, player_name)
    except Exception as e:
        self.server.logger.error(f"解绑出错: {str(e)}")
        return "解绑过程中发生错误"

def query_bindings(self, user_id, *args) -> str:
    """查询绑定信息"""
    try:
        return self.binding_mgr.get_user_bindings(user_id)
    except Exception as e:
        self.server.logger.error(f"查询绑定出错: {str(e)}")
        return "查询绑定信息时发生错误"


def get_ai_characters(self, *args):
    type = "get_ai_characters"
    group_id = self.group_ids_aync_chat[0]
    chat_type = 1
    payload =  {
        "action": type,
        "params": {
            "group_id": group_id,
            "chat_type": chat_type
        },
        "echo": type
    }
    self.server.wscl.send_group_message(payload)
    format_text = "get_ai_characters请求已发送"
    return format_text


def can_send_record(self, *args):
    payload =  {
        "action": "can_send_record",
        "params": {},
        "echo": "can_send_record"
    }
    self.server.wscl.send_group_message(payload)

    format_text = "请求已发送"
    return format_text

def get_group_list(self, *args):
    type = "get_group_list"
    payload = build_payload(type)
    self.server.wscl.send_group_message(payload)
    format_text = "群组信息已更新"
    return format_text

def online_info(self, *args):
    """获取玩家列表并通知"""
    amount, limit, players = self.mc_api.get_server_player_list()
    if players:
        player_str = "，".join(players)  # 用中文逗号分隔
        format_text = f"[CQ:face,id=161] 当前有 {amount} 个人在摸鱼: [{player_str}]"
    else:
        format_text = f"[CQ:face,id=161] 服务器倒闭了"
    return format_text


def stop_server(self, user_id, *args):
    self.server.execute('tellraw @a {"text":"[服务器将在 10 秒后关闭]","color":"gray"}')
    self.server.execute("title @a title {\"text\":\"注意!\",\"color\":\"red\"}")
    self.server.execute("title @a subtitle {\"text\":\"服务器将在 10 秒后关闭\",\"color\":\"gray\"}")
    time.sleep(11)
    self.server.execute("stop") 
    return f"{user_id}已尝试关闭服务器"


def sign_in(self, user_id, card, message_id, group_id, *args) -> str:
    """
    接收外部传入的 user_id（QQ号）进行签到
    返回签到反馈消息（可用于回复 QQ、MC 或日志）
    """
    try:
        message, message_to_mc = self.sign_handler.sign_in(user_id, card)
        if message_to_mc:
            self.server.execute(f'tellraw @a {{\"text\":\"{message_to_mc}\",\"color\":\"gray\"}}')

        return message
    except Exception as e:
        self.server.logger.warn(f"签到失败：{e}")
        return "签到失败"

def lucky_rank(self, *args) -> str:
    """
    调用类查询数据并广播消息, 与其他方法不一致.
    """
    try:
        msg, msg2mc = self.sign_handler.format_lucky_ranking()
        if msg2mc:
            self.server.execute(f'tellraw @a {{\"text\":\"{msg2mc}\",\"color\":\"gray\"}}')
        return msg
    except Exception as e:
        self.server.logger.warn(f"幸运排行榜查询失败：{e}", exc_info=True)
        return "幸运排行榜查询失败"
    
def my_info(self, user_id, nick_name, *args) -> str:
    """
    获取用户的签到信息，返回格式化的签到内容
    """
    try:
        sign_info, message_to_qq = self.sign_handler.query_user_sign_info(user_id, nick_name)
        if message_to_qq:
            self.server.execute(f'tellraw @a {{\"text\":\"{message_to_qq}\",\"color\":\"gray\"}}')
        # 返回用户签到信息
        return sign_info
    except Exception as e:
        self.server.logger.warn(f"查询用户信息失败：{e}")
        return "查询用户信息失败"
    
# def query_mc_info(self, user_id, nickname, message_id, group_id, first_param, second_param) -> str:
#     position = self.mc_api.get_player_info(second_param, 'Pos')
#     info = self.mc_api.get_player_info(second_param)
#     print(position)
#     return None


def sell_item(self, user_id, nickname, message_id, group_id, first_param, second_param, third_param) -> str:
    mysql_enable = self.config.get("mysql_enable") # 查询是否启用数据库
    luck_number = None
    if mysql_enable:
        effect_config = self.config.get("at_effect_config")
        prizes = self.config.get("prize_config", {}).get("prizes", [])
        item = second_param
        number = int(third_param) if third_param else 1
        
        if not item in effect_config: # 如果出售的道具不在道具列表
            return None
        
        try:
            # 检查用户自身是否签到
            luck_number = self.sign_handler.query_lucky_number(user_id)
            if not luck_number:
                return f"请签到后再试哦~"
            
            # 检查道具库存（从签到记录统计）
            item_count = self.sign_handler.check_item_stock(user_id, item)
            if item_count < number:
                return f"你没有足够的[{item}]道具!"
            qq_id = ''
            online_accounts = ['出售'] # 出售记录到这列

            comsume_success = False
            try:
                consumed_logs = self.sign_handler.consume_items_fifo(user_id, item, number)

                # 插入使用日志
                self.sign_handler.insert_usage_log(user_id, item, online_accounts, qq_id, consumed_logs)
                comsume_success = True
            except Exception as e:
                print(e)
                return "道具记录异常，请稍后再试"
            
            emerald = 0
            if comsume_success:
                sell_price = None
                for info in prizes:
                    if info.get("name") == item:
                        sell_price = info["sell_price"]
                        break

                factor = _get_price_factor(luck_number) # 日期哈希随机 + 用户幸运数字
                emerald = int(sell_price * number * factor)
                factor_str = f"{int(round(factor * 100))}%"

                self.sign_handler.update_emerald_drops(user_id, emerald)
                bot_name = self.server.config.get('bot_name')
                text_to_mc = f"[{bot_name}] {nickname} 成功以 {factor_str} 的价格 出售 {number} 个 {item}, 共获得 {emerald} 个绿宝石 !"  # MC
                send_gray_italic_message(self.server, text_to_mc)
                self.server.logger.info(f"[{user_id}-{factor}]成功以 {factor_str} 的价格 出售 {number} 个 {item}, 共获得 {emerald} 个绿宝石 !")  # 控制台
                return f"成功以 {factor_str} 的价格 出售 {number} 个 {item}, 共获得 {emerald} 个绿宝石 !"  # QQ
            
        except Exception as e:
            self.server.logger.error(f"道具出售失败: {str(e)}", exc_info=True)
            return "道具出售失败，请稍后再试"
        
def query_market_trend(self, user_id, nickname, *args) -> str:
    """付费查询今日行情（扣除100绿宝石）"""
    try:
        # 扣除费用
        self.sign_handler.update_emerald_drops(user_id, -50)
        # 获取行情系数
        base_factor = get_date_factor()  # 0.7-1.4
        trend = "溢价↑" if base_factor > 1.0 else "↓折扣" if base_factor < 1.0 else "正常价"
        bot_name = self.server.config.get('bot_name')
        text_to_mc = f"[{bot_name}] {nickname} 花费 50 绿宝石查询了今日行情, 今日道具售价系数：{base_factor:.2f}"
        send_gray_italic_message(self.server, text_to_mc)
        # 格式化返回信息
        return (
            "╔══今日行情══╗\n"
            f"  售价系数：{base_factor:.2f}倍\n"
            f"  市场趋势：{trend}\n"
            "╚════════╝\n"
            f"  本次查询花费50绿宝石"
        )
        
    except Exception as e:
        self.server.logger.error(f"查询行情失败: {str(e)}", exc_info=True)
        return "行情查询服务暂时不可用"
    
def _get_price_factor(lucky_number=None):
    # 1. 基于日期的基准系数
    date_factor = get_date_factor()
    # 2. 幸运数字微调（限制幅度±20%）
    if lucky_number is not None:
        lucky_effect = date_factor * (lucky_number / 100) * 0.2  # 最高20%
        date_factor += lucky_effect

    return round(max(0.7, min(2.0, date_factor)), 2)

def sync_emerald(self, *args):
    try:
        self.sign_handler.sync_balance_from_cmi()

        return "绿宝石同步完毕"
    except Exception as e:
        self.server.logger.error(f"绿宝石同步失败: {str(e)}", exc_info=True)
        return "绿宝石同步失败"


def double_xp(self, *args) -> str:
    """双倍经验切换"""
    try:
        current_state = self.server.xpboost_status
        if current_state:
            # 关闭双倍经验
            self.server.xpboost_status = False
            self.server.execute("xprate clear")
            new_state = "false"
        else:
            # 开启双倍经验
            self.server.xpboost_status = True
            self.server.execute("xprate 2 on")
            new_state = "true"
        state_str = "开启" if new_state == "true" else "关闭"
        bot_name = self.server.config.get('bot_name')
        text_to_mc = f"[{bot_name}] Mcmmo 双倍技能经验状态为: {state_str}"
        send_gray_italic_message(self.server, text_to_mc)
        return f"已{state_str}Mcmmo双倍经验活动"
    except Exception as e:
        self.server.logger.error(f"切换双倍经验失败: {str(e)}", exc_info=True)
        return "切换双倍经验失败"
    
def show_xprate(self, player: str) -> None:
    """显示当前经验倍率给指定玩家"""
    try:
        current_state = self.server.xpboost_status
        if current_state:
            commands = [
            f'panimation circle;effect:reddust;dur:5;pitchc:5;part:10;offset:0,1,0;radius:1;yawc:5;color:rs;target:{player}',
            f"execute at {player} run playsound minecraft:entity.pig.saddle master @a ~ ~ ~ 1 1",
            f'title {player} title {{"text":"MCMMO 活动！","color":"gold"}}',
            f'title {player} subtitle {{"text":"双倍技能经验开启中！","color":"yellow"}}',
        ]
            for cmd in commands:
                self.server.execute(cmd)


    except Exception as e:
        self.server.logger.error(f"显示经验倍率失败: {str(e)}", exc_info=True)
        return