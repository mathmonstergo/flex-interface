from typing import List, Tuple
from .manager_config import config
import random
import json
class EffectCommands:
    @staticmethod
    def get_effect(effect_type: str, account: str, user_name: str, at_effect_config: dict, luck_number: int) -> Tuple[List[str], str, int]:
        """
        根据幸运值计算效果成功/失败
        参数:
            effect_type: 效果类型
            account: 目标账号名
            user_name: 触发效果的用户名
            at_effect_config: 效果配置字典
            luck_number: 用户幸运值(0-100)
        返回:
            (指令列表, 结果消息)的元组
        """
        # 绿宝石掉落配置
        emerald_range = (5, 20)  # 绿宝石掉落范围5-20
        base_success_rate = 50    # 基础成功率50%
        success_rate_increase = 0.5  # 每点幸运值增加0.5%成功率
        
        # 计算最终成功率(幸运值加成)
        success_rate = base_success_rate + (luck_number * success_rate_increase)
        success_rate = min(max(success_rate, 0), 100)  # 限制在0-100%范围内
        
        # 判定是否成功
        is_success = random.random() * 100 < success_rate
        
        if is_success or effect_type == "机票":  # 成功暂时不奖励绿宝石, 机票充值必定成功
            emerald_drops = 0
            method_name = at_effect_config.get(effect_type)
            if not method_name:
                raise ValueError(f"未知的效果类型: {effect_type}")
            
            method = getattr(EffectCommands, method_name)
            commands, msg = method(account, user_name)  # 先解包
            return commands, msg, emerald_drops         # 再组合返回
        else:
            # 生成绿宝石掉落数量(成功为正数，失败为负数)
            emerald_drops = -random.randint(*emerald_range)
            commands, msg = EffectCommands.failed_effect(account, user_name, abs(emerald_drops))
            return commands, msg, emerald_drops
        
    @staticmethod  # 添加装饰器
    def failed_effect(account: str, user_name: str, emerald_drops: int) -> Tuple[List[str], str]:
        fail_messages = [
            f"{user_name} 的恶作剧反弹了！{account} 毫发无损，反而赚了 {emerald_drops} 个绿宝石！",
            f"{user_name} 转身就跑，结果绊了一跤，{emerald_drops} 个绿宝石全飞了出去！",
            f"{user_name} 的暗算还未近身，{account} 反手一掌，{emerald_drops} 个绿宝石震落在地！",
            f"{account} 看穿了 {user_name} 的把戏，{user_name} 慌乱中丢下 {emerald_drops} 个绿宝石！",
            f"{user_name} 的诡计被 {account} 当场识破，{emerald_drops} 个绿宝石散落一地！",
            f'"这点小把戏可骗不了我"，{account} 冷笑道。{user_name} 荷包里的 {emerald_drops} 个绿宝石被一把夺走。',
            f"{user_name} 的陷阱刚布下，{account} 已如鬼魅般现身：\"自取其辱！\" {emerald_drops} 个绿宝石被夺！",
            f"{account} 一把按住 {user_name}：\"玩得很开心？现在该我了！\" {emerald_drops} 个绿宝石被强行摸走！",
            f'"谁在搞鬼？！" {account} 突然转身，正好撞见 {user_name} 的小动作，{emerald_drops} 个绿宝石当场被缴！',
            f"{user_name} 的咒术还没吟唱完，{account} 已闪现到背后：\"太慢了。\" {emerald_drops} 个绿宝石被夺取！",
            f"{user_name} 正得意时，脚下突然一滑——原来 {account} 早就在他站的位置涂了黏液！{emerald_drops} 个绿宝石从破洞口袋漏个精光！",
            f'"你以为我在第一层？其实我在第五层。" {account} 从阴影走出，{user_name} 这才发现自己的陷阱早被调包，反赔 {emerald_drops} 个绿宝石！',
            f"{user_name} 的恶作剧道具突然卡壳，{account} 趁机逼近：\"玩脱了吧？\" {emerald_drops} 个绿宝石当场没收！",
            f"{user_name} 的迷烟还未散开，{account} 闭息一掌拍出：\"下三滥的手段！\" 烟散时，地上只剩求饶示好的 {emerald_drops} 个绿宝石..."
        ]

        failed_msg = random.choice(fail_messages)
        commands = [
            f'tellraw @a {{"text":{json.dumps(f"[{failed_msg}]")},"color":"gray","italic":true}}'
        ]
        for _ in range(emerald_drops):
            commands.append(
            f"""execute as {account} at @s run summon item ^ ^3 ^-5 {{Item:{{id:"minecraft:emerald",Count:1b}},Motion:[0.0,-0.25,0.2],PickupDelay:40}}""")
        
        return commands, failed_msg
    

    @staticmethod
    def get_vertigo_commands(account: str, qq_id: str) -> Tuple[List[str], str]:
        duration = 5  # 秒
        commands = [
            f'effect give {account} nausea 10 10 false',
            f'effect give {account} darkness 5 0 false',
            f'title {account} title {{"text":"你被下药了","color":"yellow"}}',
            f'title {account} subtitle {{"text":"爱来自 {qq_id}","color":"gray"}}',
            f'tellraw @a {{"text":"[{account} 喝了{qq_id} 的昏睡红茶,站不稳了!]","color":"gray","italic":true}}'
        ]
        success_msg = "成功给 {account_list} 喝了昏睡红茶!"
        return commands, success_msg

    @staticmethod
    def creeper_sound(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            # 播放苦力怕点燃音效
            f'execute at {account} run playsound minecraft:entity.creeper.primed player {account} ~ ~ ~ 1 1'
        ]

        # 10% 概率召唤苦力怕在玩家背后上方
        if random.random() < 0.1:
            commands.append(
                f'execute at {account} run summon minecraft:creeper ^ ^3 ^-5'
            )
            success_msg = f"一只苦力怕正在接近 {account} !"
        else:
            success_msg = f"成功吓唬了 {account}"

        return commands, success_msg
        
    @staticmethod
    def knockback_effect(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            f"effect give {account} levitation 1 4 true",
            f'title {account} title {{"text":"被曹飞了!","color":"red"}}',
            f'title {account} subtitle {{"text":"爱来自 {qq_id}","color":"gray"}}',
            f'tellraw @a {{"text":"[{account} 被 {qq_id} 曹飞了!]","color":"gray"}}',
            f'execute at {account} run playsound minecraft:entity.villager.hurt master {account} ~ ~ ~ 1 1']
        success_msg = "{account_list} 被曹飞了"
        return commands, success_msg

    @staticmethod
    def sleep_reminder(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            f'title {account} title {{"text":"快去碎觉!","color":"blue"}}',
            f'title {account} subtitle {{"text":"来自妈妈…哦不，是 {qq_id}","color":"light_purple"}}',
            f'tellraw @a {{"text":"[{qq_id} 提醒 {account} 该碎觉了!]","color":"gray","italic":true}}',
            f'execute at {account} run summon minecraft:phantom ~ ~3 ~']
        success_msg = "成功提醒 {account_list} 该碎觉啦 😴"
        return commands, success_msg

    @staticmethod
    def lightning_strike(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            f"execute at {account} run summon minecraft:lightning_bolt",
            f"effect give {account} glowing 30 0 true",
            f'tellraw @a {{"text":"[{account} 被 {qq_id} 劈了一道闪电!]","color":"gray","italic":true}}'
        ]
        success_msg = "成功劈了 {account_list} 一道闪电 ⚡"
        return commands, success_msg
    
    @staticmethod
    def web_trap(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            f"execute at {account} run fill ~-1 ~ ~-1 ~1 ~1 ~1 minecraft:cobweb replace minecraft:air",
            f"execute at {account} run summon area_effect_cloud ~ ~ ~ {{Age:0,Duration:100,Radius:3}}",
            f'title {account} title {{"text":"你被蜘蛛网困住了!","color":"gray"}}',
            f'title {account} subtitle {{"text":"来自 {qq_id} 的陷阱","color":"dark_gray"}}',
            f'tellraw @a {{"text":"[{account} 被 {qq_id} 设下的蜘蛛网困住了!]","color":"gray","italic":true}}'
        ]
        success_msg = "成功给 {account_list} 设置了蜘蛛网陷阱!🕸️"
        return commands, success_msg

    @staticmethod
    def freeze_effect(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            f"effect give {account} mining_fatigue 10 2 true",
            f"effect give {account} slowness 10 10 true",
            f"effect give {account} glowing 10 1 true",
            f"execute at {account} run fill ~-1 ~-1 ~-1 ~1 ~ ~1 minecraft:snow replace minecraft:air",
            f"execute at {account} run summon area_effect_cloud ~ ~ ~ {{Duration:100,Radius:3,Particle:{{type:\"minecraft:snowflake\"}}}}",
            f'title {account} title {{"text":"你被冰冻了!","color":"blue"}}',
            f'title {account} subtitle {{"text":"来自 {qq_id} 的冷冻术","color":"blue"}}',
            f'tellraw @a {{"text":"[{account} 被 {qq_id} 冰冻住了!]","color":"gray","italic":true}}'
        ]
        success_msg = "成功给 {account_list} 使用冰冻效果❄️!"
        return commands, success_msg
    @staticmethod
    def cage_effect(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            f"effect give {account} mining_fatigue 10 2 true", 
            f"execute at {account} run fill ~-1 ~-1 ~-1 ~1 ~2 ~1 minecraft:iron_bars replace minecraft:air hollow", 
            f"execute at {account} run playsound minecraft:block.anvil.place master @a ~ ~ ~",
            f"execute at {account} run fill ~ ~-1 ~ ~ ~2 ~ minecraft:obsidian replace minecraft:iron_bars",
            f'title {account} title {{"text":"你进监狱了!","color":"red"}}',
            f'title {account} subtitle {{"text":"来自 {qq_id} 的牢笼术","color":"dark_red"}}',
            
            # 广播消息
            f'tellraw @a {{"text":"[{account} 被 {qq_id} 关进了监狱!]","color":"gray","italic":true}}',
        ]
        success_msg = "成功将 {account_list} 关进了牢笼!🔒 "
        return commands, success_msg
    
    @staticmethod
    def random_teleport(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            # 播放传送音效
            f"execute at {account} run playsound minecraft:entity.enderman.teleport master @a ~ ~ ~",
            
            # 创建传送粒子效果
            f"execute at {account} run particle minecraft:portal ~ ~1 ~ 0.5 0.5 0.5 0.1 50",
            
            # 随机传送逻辑 - 在半径50格内寻找安全位置
            f"execute at {account} run spreadplayers ~ ~ 0 50 false {account}",
            
            # 检查是否安全着陆（防止玩家卡在方块中）
            f"execute as {account} at @s unless block ~ ~-0.5 ~ minecraft:air run tp @s ~ ~1 ~",
            f"execute as {account} at @s unless block ~ ~ ~ minecraft:air run tp @s ~ ~1 ~",
            f"execute as {account} at @s unless block ~ ~1 ~ minecraft:air run tp @s ~ ~2 ~",
            
            # 传送后效果
            f"execute at {account} run particle minecraft:witch ~ ~1 ~ 0.5 0.5 0.5 0.1 30",
            f"effect give {account} slow_falling 3 0 true",
            
            # 显示消息
            f'title {account} title {{"text":"随机传送!","color":"green"}}',
            f'title {account} subtitle {{"text":"你被传送到了未知位置","color":"dark_green"}}',
            f'tellraw @a {{"text":"[{account} 被 {qq_id} 随机传送到了远处!]","color":"gray","italic":true}}'
        ]
        success_msg = "成功将 {account_list} 随机传送到了远处!🌀"
        return commands, success_msg
    
    @staticmethod
    def fly_charge(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            f"cmi flightcharge add {account} 500",
            f'title {account} title {{"text":"你获得了500飞行点数!","color":"green"}}',
            f'title {account} subtitle {{"text":"来自 {qq_id} 的机票","color":"dark_green"}}',
            f'panimation circle;effect:reddust;dur:5;pitchc:5;part:10;offset:0,1,0;radius:1;yawc:5;color:rs;target:{account}',
            f'tellraw @a {{"text":"[{qq_id} 使用 机票 为 {account} 充值了500飞行点数！]","color":"gray","italic":true}}',
        ]
        success_msg = f"成功为 {account} 充值了 500 点飞行充能! ✈️"
        return commands, success_msg
    
    @staticmethod
    def hunger_effect(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            f'effect give {account} nausea 10 5 true',
            f"execute as {account} store result score @s temp run data get entity @s foodLevel",
            f"scoreboard players remove @s temp 10",
            f"execute as {account} run data modify entity @s foodLevel set from score @s temp",
            f"execute at {account} run playsound minecraft:entity.pig.saddle master @a ~ ~ ~ 1 1",
            f'title {account} title {{"text":"你快饿晕了!","color":"gold"}}',
            f'title {account} subtitle {{"text":"{qq_id}提醒你该吃饭了","color":"yellow"}}',
            
            # 广播消息
            f'tellraw @a {{"text":"[{qq_id} 提醒 {account} 该吃饭了!]","color":"gray","italic":true}}',
        ]
        success_msg = "{account_list} 感到饥肠辘辘了! 🍔"
        return commands, success_msg
    
    @staticmethod
    def jump_effect(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            f'effect give {account} jump_boost 40 6 true',
            f'panimation circle;effect:reddust;dur:40;pitchc:5;part:10;offset:0,1,0;radius:1;yawc:5;color:rs;target:{account}',
            f"execute at {account} run playsound minecraft:entity.pig.saddle master @a ~ ~ ~ 1 1",
            f'title {account} title {{"text":"地铁跑酷, 开始!","color":"gold"}}',
            f'title {account} subtitle {{"text":"{qq_id}给你装备上了弹簧鞋","color":"yellow"}}',
            
            # 广播消息
            f'tellraw @a {{"text":"[{qq_id} 给 {account} 穿上了弹簧鞋!]","color":"gray","italic":true}}',
        ]
        success_msg = "成功为 {account_list} 装备弹簧鞋！🦘"
        return commands, success_msg
    @staticmethod
    def time_slow_effect(account: str, qq_id: str) -> Tuple[List[str], str]:
        commands = [
            # 核心效果：缓降（防摔）+ 减速（时间变慢）+ 轻微跳跃（失重感）
            f"effect give {account} darkness 2 0 true",
            # 音效：幽匿感（下界传送门环境音）
            f"execute at {account} run playsound minecraft:block.conduit.ambient master @a ~ ~ ~ 1 0.8",
            # 标题提醒
            f'title {account} title {{"text":"子弹时间","color":"dark_purple"}}',
            f'title {account} subtitle {{"text":"{qq_id} 让你进入了子弹时间","color":"gray"}}',
            f"effect give {account} slow_falling 30 6 true",
            f"effect give {account} slowness 30 3 true",
            f"effect give {account} jump_boost 30 1 true",
            
            # 广播消息
            f'tellraw @a {{"text":"[{qq_id} 让 {account} 进入了子弹时间！]","color":"gray"}}'
        ]
        success_msg = f"成功让 {account} 时间流速变慢了！⏳"
        return commands, success_msg