import logging
from .handler_effect_cmd import EffectCommands  
from .manager_config import config
from mcdreforged.api.all import *
import online_player_api as ol_api
import random
from .utils import *
from .manager_config import config
from mcdreforged.api.types import PluginServerInterface
import time
# 获取 Logger 对象
logger = logging.getLogger("command_exec")


def fishing(psi: PluginServerInterface, user_id, *args):
    """钓鱼具体执行
    param: psi 服务器交互实例
    param: user_id QQ用户的QQ号码
    paramL *args 调用本方法时 args默认有3位,分别为x,y,z
    TODO:xyz代表了mc里面的坐标,之后编写方法去读取当前世界对应的xyz方块是否是水方块,若是才能进入下一步钓鱼,
    若不是则返回format_text="当前坐标没有水,无法钓鱼"
    现在只需要你帮我实现绑定用户到数据库(替代现在的存储数据方法),
    """
    result = "方法未启用"
    return result

def trick_binded_player(self, user_id: str, args: list) -> str:
    """@玩家给予游戏效果（消耗签到获得的道具）"""
    number = 1
    qq_id = args[0]  # 目标玩家QQ
    effect_type = args[1]  # 道具名称（对应reward_name）
    user_name = args[2]  # 使用者昵称
    second_param = args[3]
    mysql_enable = config.get("flex_mysql_config").get("enable") # 查询是否启用数据库

    effect_config = config.get("at_effect_config")

    if not effect_type in effect_config:  
        return None

    if second_param:  # 如果传入了使用次数
        number = int(second_param)
    if user_id == qq_id and user_id not in config.get("admin", []):
        self_effect = ["机票", "盲盒"]
        if effect_type not in self_effect:  # 目前只有机票 盲盒支持对自己操作
            return "你不能对自己那样做~"
    send_gray_italic_message(self.server, f"[苦力仆提醒] {user_name}在群里悄悄密谋着什么...")

    if mysql_enable:
        try:
            # 检查用户自身是否签到
            luck_number = self.sign_handler.query_lucky_number(user_id)
            if not luck_number:
                return f"请签到后再试哦~"
            
            # 检查道具库存（从签到记录统计）
            item_count = self.sign_handler.check_item_stock(user_id, effect_type)
            if item_count < number:
                return f"你没有足够的[{effect_type}]道具!"

            # 检查目标玩家
            game_accounts = self.binding_mgr.get_game_account_by_qq(qq_id)
            if not game_accounts:
                return f"QQ {qq_id} 未绑定游戏账号"
            
            # 执行效果
            online_accounts = []
            emerald_drops = 0
            pass_judge = False
            msg = ""
            box_msg = ""
            if effect_type == "盲盒":
                pass_judge = True
                box_msg, message_to_mc = self.sign_handler.open_box(qq_id, user_name)
                send_gray_italic_message(self.server, message_to_mc)

            else:
                for account in game_accounts:
                    if ol_api.check_online(account):
                        online_accounts.append(account)  # 不管是否成功 都算消耗
                        # 根据成功率决定是否执行
                        commands, msg, emerald_drops = EffectCommands.get_effect(effect_type, account, user_name, effect_config, luck_number)
                        for cmd in commands:
                            self.server.execute(cmd)
                        if effect_type == "机票": # 机票仅对一个在线账户生效
                            break
                    
            # 只有成功执行才标记道具已使用
            if online_accounts or pass_judge:
                if pass_judge:
                    online_accounts = ["无"]
                try:
                    # ✅ 消耗指定数量
                    consume_count = 1 # int(second_param) if second_param else 1
                    consumed_logs = self.sign_handler.consume_items_fifo(user_id, effect_type, consume_count)
                    # ✅ 插入使用日志
                    self.sign_handler.insert_usage_log(user_id, effect_type, online_accounts, qq_id, consumed_logs)
                    
                    # 更新绿宝石
                    if emerald_drops != 0:
                        self.sign_handler.update_emerald_drops(user_id, emerald_drops)

                    msg = msg.format(account_list=", ".join(online_accounts))  # mc所有的信息全部在handler内部执行了, only QQ return
                    
                    return box_msg if box_msg else msg  # 如果有message 那就一定是pass_judge
                except ValueError:
                    return f"你没有足够的[{effect_type}]道具（需要 {consume_count} 个）"
            
            return "目标玩家不在线"
        
        except Exception as e:
            self.server.logger.error(f"道具使用失败: {str(e)}", exc_info=True)
            return "道具使用失败，请稍后再试"
    else:
        return "请开启mysql服务并配置"
        

# def mc_realtime_info(self, user_id: str, args: list):
#     info= api.get_player_info(args[0],data_path="XpLevel", timeout=10)
#     parsed_info = api.convert_minecraft_json(str(info))

# def mc_pos_info(self, user_id: str, args: list):
#     info = api.get_player_coordinate(args[0])
#     parsed_info = api.convert_minecraft_json(str(info))
