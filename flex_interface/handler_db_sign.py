import random
import logging
from datetime import date, timedelta
import datetime
import time
class PlayerSignManager:
    def __init__(self, server, mysql_mgr, binding_mgr, prize_config):
        self.server = server
        self.mysql_mgr = mysql_mgr
        self.binding_mgr = binding_mgr
        self.prize_config = prize_config
        self.logger = logging.getLogger("player_sign")
        self.max_streak_days = 999  # 最大连续签到天数

    def _get_eligible_prizes(self, current_streak):
        """获取符合条件的奖品列表（稀有度上限7）"""
        max_rarity = min(current_streak, 7)  # 稀有度上限为7
        return [p for p in self.prize_config["prizes"] if p["rarity"] <= max_rarity]

    def _calculate_weights(self, eligible_prizes, streak_days):
        # 目标概率
        target_prob = {
            1: 0.10,  # 1星10%
            2: 0.20,  # 2星20%
            3: 0.25,  # 3星25%
            4: 0.20,  # 4星20%
            5: 0.15,  # 5星15%
            6: 0.10,   # 6星10%
            7: 0.10  # 7星10%
        }
        # 动态调整：高稀有度随天数增加概率
        streak_factor = min(streak_days / 31, 1.0)  # 归一化到[0,1]
        for rarity in [3, 4, 5, 6]:
            target_prob[rarity] *= (1 + streak_factor)  # 最高翻倍
        # 反推权重（假设1星权重=10）
        base_weight = 10
        weights = []
        for p in eligible_prizes:
            rarity = p["rarity"]
            weight = base_weight * (target_prob[rarity] / target_prob[1])
            weights.append(weight)
        return weights
    
    def _get_base_amount(self, reward_name):
        """通过奖励名称获取基础数量"""
        for prize in self.prize_config["prizes"]:
            if prize["name"] == reward_name:
                return prize.get("base_amount", 1)
        self.logger.warning(f"未找到奖励配置: {reward_name}")
        return 1  # 默认保底值

    def _determine_multiplier(self, lucky_number):
        for str_key, range_dict in self.prize_config["multiplier_ranges"].items():
            if range_dict["min"] <= lucky_number <= range_dict["max"]:
                return int(str_key)  # 将字符串键转整数
        return 1

    def _generate_reward(self, user_id, streak_days):
        """生成奖励逻辑"""
        # 筛选可用奖励
        eligible_prizes = self._get_eligible_prizes(streak_days)
        if not eligible_prizes:
            raise ValueError("没有可用的奖励配置")

        # 动态权重选择
        weights = self._calculate_weights(eligible_prizes, streak_days)
        selected_prize = random.choices(eligible_prizes, weights=weights, k=1)[0]

        # 生成/读取幸运数字
        today = date.today()
        lucky_number = self.query_lucky_number(user_id, today)
        if not lucky_number:
            lucky_number = random.randint(1, 100)
        multiplier = self._determine_multiplier(lucky_number)

        # 计算最终数量
        base_amount = self._get_base_amount(selected_prize["name"])
        final_amount = base_amount * multiplier

        return {
            "name": selected_prize["name"],
            "category": selected_prize["category"],
            "final_amount": final_amount,
            "multiplier": multiplier,
            "lucky_number": lucky_number
        }
    
    def _update_sign_record(self, user_id, card, today, new_streak, lucky_number):
        """更新签到记录，包括今日幸运值"""
        if self.mysql_mgr.query_one(
            "SELECT user_id FROM player_daily_sign WHERE user_id = %s",
            (user_id,)
        ):
            # 已有记录，更新
            self.mysql_mgr.safe_query(
                """
                UPDATE player_daily_sign
                SET last_sign_date=%s, streak_days=%s, card=%s, lucky_number=%s
                WHERE user_id=%s
                """,
                (today, new_streak, card, lucky_number, user_id)
            )
        else:
            # 没有记录，插入
            self.mysql_mgr.safe_query(
                """
                INSERT INTO player_daily_sign (user_id, last_sign_date, streak_days, card, lucky_number)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, today, new_streak, card, lucky_number)
            )
    def  querry_today_sign(self, user_id):
        try:
            today = date.today()
            
            # 获取用户当前状态
            record = self.mysql_mgr.query_one(
                "SELECT last_sign_date, lucky_number FROM player_daily_sign WHERE user_id = %s",
                (user_id,)
            )

            # 检查今日是否已签到, 如果签到了就返回幸运数字
            if record and record["last_sign_date"] == today:
                return record["lucky_number"]
            else:
                return '未签到'
        except Exception as e:
            self.server.logger.error(f"查询用户今日签到信息失败: {str(e)}", exc_info=True)
            return '未签到'
        
    def sign_in(self, user_id, card):
        """签到入口方法"""
        try:
            today = date.today()
            
            # 获取用户当前状态
            record = self.mysql_mgr.query_one(
                "SELECT last_sign_date, streak_days FROM player_daily_sign WHERE user_id = %s",
                (user_id,)
            )

            # 检查今日是否已签到
            if record and record["last_sign_date"] == today:
                return "今日已签到, 请明天再来哦~", None

            sign_record_date = self.mysql_mgr.query_one("SELECT COUNT(*) as count FROM player_daily_sign WHERE last_sign_date = %s", (today,))
            today_sign_count = sign_record_date['count'] if sign_record_date else 0
            
            sign_order = today_sign_count + 1 # 已签到人数＋1 为当前签到人次序
            # 计算连续天数
            current_streak = record["streak_days"] if record else 0
            if record and record["last_sign_date"] == today - timedelta(days=1):
                new_streak = min(current_streak + 1, self.max_streak_days)
            else:
                new_streak = 1

            # 生成奖励
            reward = self._generate_reward(user_id, new_streak)


            # 数据库事务
            with self.mysql_mgr.transaction():
                # 更新签到记录
                self._update_sign_record(user_id, card, today, new_streak, reward['lucky_number'])

                # 记录奖励日志
                self.mysql_mgr.safe_query(
                    """INSERT INTO sign_reward_logs 
                    (user_id, reward_name, final_amount, multiplier, 
                     lucky_number, sign_date, category)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (user_id, reward["name"], reward["final_amount"],
                     reward["multiplier"], reward["lucky_number"], 
                     today, reward["category"])
                )

            message = (
                "║ 🎉🎉 签到成功！🎉🎉\n"
                "║═══════════\n"
                f"║✨ 今日幸运数字：{reward['lucky_number']} ✨\n"
                f"║🔮 幸运倍数：{reward['multiplier']} 🔮\n"
                f"║🏆 获得道具：{reward['name']}*{reward['final_amount']} 🏆\n"
                f"║🌟 连续签到天数：{new_streak} 🌟\n"
                "║═══════════\n"
                f"║你是今天第 {sign_order} 个签到的用户\n"
                "║赶紧用道具干翻群友吧！\n"
                "║@群友并选中,输入道具名称,发送！"
            )
            bot_name = self.server.config.get('bot_name')
            message_to_mc = f"[{bot_name}] {card} 今日第{sign_order}个签到，获得幸运数字 {reward['lucky_number']}，触发 {reward['multiplier']} 倍奖励，得到 {reward['name']} {reward['final_amount']} 个，当前已连续签到 {new_streak} 天。"
            
            print(message_to_mc)
            return message, message_to_mc
        except Exception as e:
            self.server.logger.error(f"签到失败: {str(e)}", exc_info=True)
            return "签到失败", None
        

    def open_box(self, user_id, nick_name):
        try:
            # 根据已签到的幸运值, 连续签到天数 获取盲盒奖励
            today = date.today()
            
            # 获取用户当前状态
            record = self.mysql_mgr.query_one(
                "SELECT last_sign_date, streak_days FROM player_daily_sign WHERE user_id = %s",
                (user_id,)
            )
            if not record:
                return f"请QQ{user_id}签到后再试~", None
            # 检查今日是否已签到
            if record["last_sign_date"] != today:
                return f"请QQ{user_id}签到后再试~", None

            # 计算连续天数
            current_streak = record["streak_days"]

            # 生成奖励
            reward = self._generate_reward(user_id, current_streak)

            # 数据库事务
            with self.mysql_mgr.transaction():
                # 记录奖励日志
                self.mysql_mgr.safe_query(
                    """INSERT INTO sign_reward_logs 
                    (user_id, reward_name, final_amount, multiplier, 
                     lucky_number, sign_date, category)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (user_id, reward["name"], reward["final_amount"],
                     reward["multiplier"], reward["lucky_number"], 
                     today, "QQ_extra")  # category="QQ_extra" 区分签到获取的道具
                )

            message = (
                f"成功为QQ {user_id} 开启盲盒\n"
                f"获得道具：{reward['name']}*{reward['final_amount']}"
            )
            bot_name = self.server.config.get('bot_name')
            message_to_mc = f"[{bot_name}] {nick_name} 为QQ {user_id} 开启了盲盒，得到 {reward['name']} {reward['final_amount']} 个"
            print(message_to_mc)
            return message, message_to_mc
        except Exception as e:
            self.logger.error(f"盲盒开启失败: {str(e)}", exc_info=True)
            return "道具使用出错了,请稍后再试", None
        
    def check_item_stock(self, user_id: str, effect_type: str) -> int:
        """检查道具库存"""
        item_count = self.mysql_mgr.query_one(
            """SELECT SUM(final_amount) AS amount
            FROM sign_reward_logs
            WHERE user_id = %s AND reward_name = %s
            AND is_used = 0""",
            (user_id, effect_type)
        )
        return item_count["amount"] if item_count and item_count["amount"] is not None else 0  # 防止 None 错误
        
    def get_oldest_items(self, user_id: str, effect_type: str, number: int):
        """获取多个最早获得的道具（FIFO消耗）"""
        return self.mysql_mgr.query_all(
            """SELECT id, final_amount 
            FROM sign_reward_logs 
            WHERE user_id = %s AND reward_name = %s
            AND is_used = 0  # 排除已使用的道具
            ORDER BY sign_date ASC LIMIT %s""",
            (user_id, effect_type, number)
        )
    
    def update_emerald_drops(self, user_id: str, emerald_drops: int):
        """仅更新玩家的绿宝石数量"""
        try:
            user_id = str(user_id)
            # 更新玩家绿宝石数量
            update_query = """
                UPDATE player_daily_sign
                SET emerald_drops = emerald_drops + %s
                WHERE user_id = %s
            """
            rows_affected = self.mysql_mgr.safe_query(update_query, (emerald_drops, user_id))

            # 如果更新成功，记录日志
            if rows_affected is not None:
                if rows_affected > 0:
                    self.logger.info(f"玩家 {user_id} 的绿宝石已更新，增加 {emerald_drops} 个。")
                else:
                    self.logger.info(f"玩家 {user_id} 不存在，无法更新绿宝石。")
            else:
                self.logger.error(f"查询执行失败，未返回有效的行数。")
        except Exception as e:
            self.logger.error(f"更新绿宝石失败: {str(e)}", exc_info=True)
        
    def consume_items_fifo(self, user_id: str, effect_type: str, number: int):
        """消耗道具并返回消耗日志，同时记录额外消耗的 drops"""
        consumed_logs = []
        
        # 获取多个最早的道具
        oldest_items = self.get_oldest_items(user_id, effect_type, number)
        
        # 计算实际可用数量（考虑final_amount）
        available_amount = sum(item['final_amount'] for item in oldest_items)
        if available_amount < number:
            raise ValueError(f"没有足够的[{effect_type}]道具（需要{number}个，仅有{available_amount}个）")
        
        remaining_consumption = number  # 跟踪还需要消耗的数量
        
        # 遍历并处理消耗的道具
        for item in oldest_items:
            if remaining_consumption <= 0:
                break  # 如果已经消耗完所需数量，退出循环
                
            final_amount = item["final_amount"]
            
            # 计算本次要消耗的数量（不能超过剩余需要消耗的数量或当前道具的数量）
            consume_amount = min(final_amount, remaining_consumption)
            
            # 记录本次消耗（使用要求的元组格式）
            consumed_logs.append((item['id'], consume_amount))
            
            remaining_consumption -= consume_amount  # 减少剩余需要消耗的数量
            
            # 更新数据库
            if final_amount - consume_amount <= 0:
                # 如果剩余数量为 0 或负数，标记为已使用
                self.mysql_mgr.safe_query(
                    """UPDATE sign_reward_logs 
                    SET final_amount = 0, 
                        is_used = 1, 
                        used_time = NOW() 
                    WHERE id = %s""",
                    (item["id"],)
                )
            else:
                # 否则，只减少数量，不标记为已使用
                self.mysql_mgr.safe_query(
                    """UPDATE sign_reward_logs 
                    SET final_amount = %s 
                    WHERE id = %s""",
                    (final_amount - consume_amount, item["id"])
                )
        
        return consumed_logs

    def insert_usage_log(self, user_id: str, reward_name: str, online_accounts: list, qq_id: str, consumed_logs: list):
        """插入道具使用日志，同时处理 drops 记录，并更新 player_daily_sign 表中的绿宝石数量"""
        try:
            usage_time = datetime.datetime.now()
            
            for account in online_accounts:
                for consumed_log in consumed_logs:
                    if not isinstance(consumed_log, tuple) or len(consumed_log) != 2:
                        raise ValueError(f"consumed_log should be a tuple with (id, quantity), got {type(consumed_log)}")

                    source_log_id, quantity = consumed_log
                    
                    # 如果是 drops 记录，reward_name 设为 "emerald_drops"
                    current_reward_name = "emerald_drops" if source_log_id == -1 else reward_name
                    
                    # 插入道具使用日志
                    args = (user_id, qq_id, current_reward_name, source_log_id, usage_time, account, quantity)
                    self.mysql_mgr.safe_query(""" 
                        INSERT INTO item_usage_logs (user_id, target_user_id, reward_name, source_log_id, usage_time, account, quantity)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, args)

            return True
        except Exception as e:
            self.logger.error(f"插入道具使用日志失败: {str(e)}", exc_info=True)
            return False


    def query_user_sign_info(self, user_id: str, nick_name: str):
        """查询用户签到信息，包括道具数量、连续签到天数、幸运数字等"""
        try:
            today = date.today()
            today_start = datetime.datetime.combine(today, datetime.datetime.min.time())  # 今天的00:00:00
            today_end = today_start.replace(hour=23, minute=59, second=59)  # 今天的23:59:59

            # 查询用户签到信息、道具信息、幸运数字等
            base_info = self.query_base_sign_info(user_id, today)
            if base_info:
                rewards = self.query_rewards(user_id)
                lucky_number = self.query_lucky_number(user_id, today)
                usage_info_today = self.query_usage_info(user_id, today_start, today_end)
                usage_info_total = self.query_usage_info_total(user_id)
                target_info = self.query_target_info(user_id)
                as_target_info = self.query_as_target_info(user_id)
                emerald = self.query_emerald(user_id)  # 返回的是元组， drop , cache
                # 构造返回的消息
                message = self.format_message(nick_name, base_info, lucky_number, usage_info_today, usage_info_total, target_info, rewards, as_target_info, emerald)
            else:
                message = "请签到后再试哦,指令示例：签到", None
            return message
        except Exception as e:
            self.logger.error(f"查询用户签到信息失败: {str(e)}", exc_info=True)
            return "查询失败，请稍后再试。", None

    def query_base_sign_info(self, user_id: str, today: date):
        """查询用户签到基础信息"""
        base_query = """
            SELECT streak_days, last_sign_date AS sign_date
            FROM player_daily_sign
            WHERE user_id = %s AND DATE(last_sign_date) = %s
            LIMIT 1
        """
        return self.mysql_mgr.query_one(base_query, (user_id, today))

    def query_rewards(self, user_id: str):
        """查询道具信息"""
        reward_query = """
            SELECT reward_name, SUM(final_amount) AS total_amount
            FROM sign_reward_logs
            WHERE user_id = %s
            GROUP BY reward_name
            HAVING total_amount > 0
        """
        return self.mysql_mgr.query_all(reward_query, (user_id,))

    def query_lucky_number(self, user_id: str,today: date = None):
        today = date.today()
        try:
            lucky_query = """
                SELECT
                    MAX(CASE WHEN DATE(sign_date) = %s THEN lucky_number ELSE NULL END) AS today_lucky_number
                FROM
                    sign_reward_logs
                WHERE
                    user_id = %s
                    AND category = 'QQ'
                LIMIT 1
            """
            result = self.mysql_mgr.query_one(lucky_query, (today, user_id))
            if result and result["today_lucky_number"] is not None:
                return result["today_lucky_number"]
            return None  # 无幸运数字
        except Exception as e:
            self.logger.error(f"查询幸运数字失败: {str(e)}", exc_info=True)
            return None
        
    def query_today_lucky_ranking(self, limit: int = 10):
        """
        查询今日幸运值排行榜
        """
        today = date.today()
        lucky_ranking_query = """
            SELECT 
                p.user_id,
                p.card,
                p.streak_days,
                p.lucky_number
            FROM player_daily_sign p
            WHERE p.last_sign_date = %s
            ORDER BY p.lucky_number DESC
            LIMIT %s
        """
        return self.mysql_mgr.query_all(lucky_ranking_query, (today, limit))
    
    def query_usage_info(self, user_id: str, today_start: datetime, today_end: datetime):
        """查询今天使用的道具信息"""
        usage_query_today = """
            SELECT reward_name, COUNT(*) AS items_used_today
            FROM item_usage_logs
            WHERE user_id = %s 
            AND usage_time >= %s 
            AND usage_time < %s
            AND account NOT IN ('出售', '无')  -- 新增过滤条件
            GROUP BY reward_name
        """
        return self.mysql_mgr.query_all(usage_query_today, (user_id, today_start, today_end))

    def query_usage_info_total(self, user_id: str):
        """查询历史使用的道具信息"""
        usage_query_total = """
            SELECT reward_name, COUNT(*) AS total_items_used
            FROM item_usage_logs
            WHERE user_id = %s
            AND account NOT IN ('出售', '无')  -- 新增过滤条件
            GROUP BY reward_name
        """
        return self.mysql_mgr.query_all(usage_query_total, (user_id,))

    def query_target_info(self, user_id: str):
        """查询最常互动的玩家（排除'出售'账号）"""
        target_info_query = """
            SELECT i.account, COUNT(DISTINCT i.id) AS usage_count
            FROM item_usage_logs i
            WHERE i.user_id = %s
            AND i.account NOT IN ('出售', '无')  -- 新增过滤条件(出售,无)
            GROUP BY i.account
            ORDER BY usage_count DESC
            LIMIT 1
        """
        return self.mysql_mgr.query_one(target_info_query, (user_id,))

    def query_as_target_info(self, user_id: str):
        """查询作为目标的用户互动信息"""
        as_target_info_query = """
            SELECT COUNT(*) AS total_usage_count, COALESCE(SUM(quantity), 0) AS total_quantity
            FROM item_usage_logs
            WHERE target_user_id = %s
        """
        return self.mysql_mgr.query_one(as_target_info_query, (user_id,))
    
    def query_emerald(self, user_id: str):
        """查询玩家的绿宝石数量和缓存余额"""
        emerald_query = """
            SELECT emerald_drops, cached_balance
            FROM player_daily_sign
            WHERE user_id = %s
            LIMIT 1
        """
        result = self.mysql_mgr.query_one(emerald_query, (user_id,))
        if result:
            return result['emerald_drops'], result['cached_balance']
        else:
            return 0, 0  # 如果没有记录，默认都返回 0


    def format_message(self, nick_name, base_info, lucky_number, usage_info_today, usage_info_total, target_info, rewards, as_target_info, emerald):
        """格式化最终返回的消息"""
        message = f"║🧾 {nick_name}\n"
        message += "║═══════════\n"

        # 添加签到基础信息
        if base_info:
            message += f"║ 🌟 连续签到: {base_info['streak_days']} 天\n"
            message += f"║ 🔮 今日幸运数字: {lucky_number if lucky_number else '无'}\n"
        else:
            message += "║ 🌟 今天你还没签到哦~\n"
            message += "║ 🔮 今日幸运数字: 无\n"

        message += "║═══════════\n"

        # 今日道具使用情况
        if usage_info_today:
            today_rewards = [f"{r['reward_name']} * {r['items_used_today']}" for r in usage_info_today]
            message += f"║ 🛠️ 今日互动次数: {', '.join(today_rewards)}\n"
        else:
            message += "║ ❌ 今天还没有使用过道具哦~\n"

        # 历史道具使用情况
        if usage_info_total:
            history_rewards = [f"{r['reward_name']} * {r['total_items_used']}" for r in usage_info_total]
            message += f"║ 🏹 历史互动次数: {', '.join(history_rewards)}\n"
        else:
            message += "║ ❌ 你还没有使用过道具\n"

        # 最爱玩家
        if target_info:
            message += f"║ ❤️ 最爱玩家: {target_info['account']}({target_info['usage_count']}次)\n"

        message += "║═══════════\n"
        bot_name = self.server.config.get('bot_name')
        message_to_mc = f"[{bot_name}] {nick_name}查询了他的个人信息"
        # 道具信息
        if rewards:
            reward_list = [f"{r['reward_name']} * {r['total_amount']}" for r in rewards]
            message += f"║ 🎁 我的道具: {', '.join(reward_list)}\n"
            message_to_mc += f"，有道具：{', '.join(reward_list)}"
        else:
            message += "║ 🎁 我的道具: 无\n"
            message_to_mc += ",一个道具都没有"

        emerald_drops, cached_balance = emerald
        
        message += "║═══════════\n"
        message += f"║ 💰 我的绿宝石: {cached_balance}\n"
        message += f"║ 📥 待入账数量: {emerald_drops}\n"
        message += "║═══════════\n"

        # 被互动次数
        if as_target_info:
            message += f"║ 🎯 被互动次数: {as_target_info['total_usage_count']}\n"
            # message += f"║ 🎯 被互动道具数: {as_target_info['total_quantity']}\n"

        message += "║═══════════"
        message_to_mc += (
            (
                f"，有 {cached_balance} 个绿宝石，待入账绿宝石 {emerald_drops} 个"
            ) +
            (f"，最爱捉弄的玩家是{target_info['account']}" if target_info else ",还没有捉弄过玩家") +
            "。"
        )
        return message, message_to_mc
    
    def format_lucky_ranking(self, limit: int = 10):
        ranking = self.query_today_lucky_ranking(limit)
        if not ranking:
            return "今天还没有人签到呢 ~"

        message = "🎲 今日幸运排行榜 🎲\n"
        for idx, row in enumerate(ranking, start=1):
            message += (
                f"{idx}. {row['card'] or row['user_id']}({row['lucky_number']}) - 连续签到 {row['streak_days']} 天\n"
            )

        # 今日最幸运的人
        top = ranking[0]
        message += (
            f"\n🍀 今日最幸运的是 {top['card'] or top['user_id']}，"
            f"幸运值高达 {top['lucky_number']}！"
        )
        message_to_mc = (
            f"今日最幸运的是 {top['card'] or top['user_id']}，幸运值高达 {top['lucky_number']}！"
        )
        return message, message_to_mc

    def query_players_binded(self):
        try:
            # 查询所有绑定账号的用户
            query = """
                SELECT pds.user_id, pds.emerald_drops, pb.account1
                FROM player_daily_sign pds
                JOIN player_bindings pb ON pds.user_id = pb.user_id
                WHERE pb.account1 IS NOT NULL
            """
            players = self.mysql_mgr.query_all(query)

            return players
        
        except Exception as e:
            self.logger.error(f"查询QQ绑定名称时出错: {str(e)}", exc_info=True)

    def apply_emerald_to_player_on_join(self, username: str):
        """
        根据 emerald_drops 发放经济（使用 CMI 指令），同步最新余额至 cached_balance，并清空 emerald_drops。
        仅当玩家名为 account1 时执行。
        """
        if not self.mysql_mgr.config.get("enable_cmi", False):
            self.logger.warning("未启用 CMI，同步跳过。")
            return

        try:
            # 检查是否为 account1 绑定
            binding = self.binding_mgr.get_bindings_by_account1(username)
            if not binding:
                self.logger.info(f"玩家 {username} 不是主绑定账号（account1），跳过绿宝石同步。")
                return

            user_id = binding['user_id']

            # 查询 emerald_drops
            result = self.mysql_mgr.safe_query(
                """
                SELECT emerald_drops 
                FROM player_daily_sign 
                WHERE user_id = %s
                """,
                (user_id,)
            )

            if not result:
                self.logger.info(f"未找到用户 {user_id} 的签到数据，跳过。")
                return

            emerald_delta = int(result[0]['emerald_drops'])
            if emerald_delta == 0:
                self.logger.info(f"用户 {username} 的 emerald_drops 为 0，无需处理。")
                return

            # 发放经济 + 显示标题
            cmds = [
                f'cmi money {"give" if emerald_delta > 0 else "take"} {username} {abs(emerald_delta)}',
                f'title {username} title {{"text":"绿宝石已同步!","color":"green"}}',
                f'title {username} subtitle {{"text":"你的余额 {emerald_delta:+}","color":"dark_green"}}',
                f'cmi sound entity.player.levelup {username}',  # 增加经验音效
            ]
            for cmd in cmds:
                self.server.execute(cmd)

            # 清空 emerald_drops
            self.mysql_mgr.safe_query(
                """
                UPDATE player_daily_sign 
                SET emerald_drops = 0 
                WHERE user_id = %s
                """,
                (user_id,)
            )
            # 同步最新余额至 cached_balance
            balance_result = self.mysql_mgr.safe_query_cmi(
                "SELECT Balance FROM cmi_users WHERE username = %s",
                (username,)
            )
            if balance_result:
                new_balance = balance_result[0]['Balance'] + emerald_delta
                self.mysql_mgr.safe_query(
                    """
                    UPDATE player_daily_sign 
                    SET cached_balance = %s 
                    WHERE user_id = %s
                    """,
                    (new_balance, user_id)
                )
                self.logger.info(
                    f"玩家 {username} ({user_id}) 同步绿宝石 {emerald_delta:+}，当前余额: {new_balance}"
                )
            else:
                self.logger.warning(f"CMI 中未找到 {username} 的余额记录，跳过 cached_balance 同步。")

        except Exception as e:
            self.logger.error(f"处理玩家 {username} 的绿宝石同步出错: {e}", exc_info=True)


    def sync_balance_from_cmi(self):
        # 定时批量同步余额
        if not self.mysql_mgr.config.get("enable_cmi", False):
            self.server.logger.warning("未启用 CMI，同步跳过。")
            return

        try:
            # 查询所有绑定了游戏账号的玩家
            records = self.query_players_binded()
            if not records:
                self.server.logger.info("没有绑定账号的用户，跳过同步。")
                return

            for row in records:
                user_id = row['user_id']
                username = row['account1']  # 使用 account1 作为 username

                if not username:
                    self.server.logger.warning(f"用户 {user_id} 未绑定游戏账号，跳过。")
                    continue

                try:
                    with self.mysql_mgr.transaction() as trx:
                        # 查询 CMI 当前余额
                        current_result = self.mysql_mgr.safe_query_cmi(
                            "SELECT Balance FROM cmi_users WHERE username = %s", (username,)
                        )
                        if not current_result:
                            self.server.logger.warning(f"找不到 CMI 用户名：{username}，跳过。")
                            continue

                        current_balance = current_result[0]['Balance']

                        # 更新 player_daily_sign 表中的 cached_balance 字段
                        update_flex = """
                            UPDATE player_daily_sign
                            SET cached_balance = %s
                            WHERE user_id = %s
                        """
                        self.mysql_mgr.safe_query(update_flex, (current_balance, user_id))

                        self.server.logger.info(
                            f"用户 {username} ({user_id}) 当前余额已同步: {current_balance}"
                        )
                except Exception as e:
                    self.server.logger.error(f"同步用户 {user_id} 时出错: {e}", exc_info=True)

        except Exception as e:
            self.server.logger.error(f"执行同步操作失败: {e}", exc_info=True)