import logging
import threading
import time
from .utils import build_payload
logger = logging.getLogger("manager_bind")

class PlayerBindingManager:
    def __init__(self, mysql_mgr):
        self.mysql_mgr = mysql_mgr
        self.logger = logger
        self.table_name = "player_bindings"

    def _execute_query(self, query, params=None):
        """执行SQL查询的辅助方法"""
        try:
            return self.mysql_mgr.safe_query(query, params)
        except Exception as e:
            self.logger.error(f"数据库查询失败: {str(e)}")
            raise

    def bind_account(self, user_id: str, player_name: str) -> str:
        """
        绑定玩家账号
        :return: 操作结果消息
        """
        # 检查是否已绑定两个账号
        current = self.get_bindings(user_id)
        if current and current.get('account1') and current.get('account2'):
            return "已绑定两个账号，无法继续绑定"

        # 检查玩家名是否已被绑定
        if self.is_player_bound(player_name):
            bound_user = self.get_user_by_player(player_name)  # 获取绑定该玩家名的用户
            return f"玩家名 {player_name} 已被其他用户 ({bound_user}) 绑定"
        
        # 执行绑定
        if not current:
            # 新用户首次绑定
            self._execute_query(
                f"INSERT INTO {self.table_name} (user_id, account1) VALUES (%s, %s)",
                (user_id, player_name)
            )
            return f"✅ 绑定 账号1: {player_name} 成功"
        else:
            # 已有绑定记录
            field = 'account2' if current.get('account1') else 'account1'
            self._execute_query(
                f"UPDATE {self.table_name} SET {field} = %s WHERE user_id = %s",
                (player_name, user_id)
            )
            return f"✅ 绑定 {field}: {player_name} 成功"

    def unbind_account(self, user_id: str, player_name: str) -> str:
        """
        解绑玩家账号
        :return: 操作结果消息
        """
        current = self.get_bindings(user_id)
        if not current:
            return "未绑定任何账号"

        if player_name not in [ (current.get('account1') or ""), (current.get('account2') or "")]:
            return f"未绑定过账号: {player_name}"

        # 确定解绑字段
        field = 'account1' if current.get('account1') == player_name else 'account2'

        # 更新对应字段为NULL
        self._execute_query(
            f"UPDATE {self.table_name} SET {field} = NULL WHERE user_id = %s",
            (user_id,)
        )

        # 检查是否全部解绑
        current = self.get_bindings(user_id)
        if not current.get('account1') and not current.get('account2'):
            self._execute_query(
                f"DELETE FROM {self.table_name} WHERE user_id = %s",
                (user_id,)
            )
        field_dict = {
            'account1': '账号1',
            'account2': '账号2'
        }
        return f"✅ 取消绑定 {field_dict[field]}: {player_name} 成功"

    def get_bindings(self, user_id: str) -> dict:
        """获取用户绑定信息"""
        result = self._execute_query(
            f"SELECT account1, account2 FROM {self.table_name} WHERE user_id = %s",
            (user_id,)
        )
        return result[0] if result else {}

    def get_account1_by_user_id(self, user_id: str) -> str | None:
        """根据 user_id 获取绑定的 Minecraft 账户名（account1）"""
        binding = self.get_bindings(user_id)
        return binding.get("account1") if binding else None

    def is_player_bound(self, player_name: str) -> bool:
        """检查玩家名是否已被绑定"""
        result = self._execute_query(
            f"SELECT 1 FROM {self.table_name} WHERE account1 = %s OR account2 = %s LIMIT 1",
            (player_name, player_name)
        )
        return bool(result)

    def get_user_by_player(self, player_name: str) -> str:
        """获取绑定某个玩家账号的用户ID"""
        result = self._execute_query(
            f"SELECT user_id FROM {self.table_name} WHERE account1 = %s OR account2 = %s LIMIT 1",
            (player_name, player_name)
        )
        return result[0]['user_id'] if result else "未知用户"

    def get_user_bindings(self, user_id: str) -> str:
        """获取用户绑定情况描述"""
        bindings = self.get_bindings(user_id)
        if not bindings:
            return "你还未绑定过账号"
        
        account1 = bindings.get('account1', '无')
        account2 = bindings.get('account2', '无')
        return f"你的绑定情况: 账号1: {account1}, 账号2: {account2}"
    
    def get_bindings_by_account1(self, account1: str) -> dict:
        """根据主账号名（account1）查询绑定信息"""
        result = self._execute_query(
            f"SELECT user_id, account1, account2 FROM {self.table_name} WHERE account1 = %s",
            (account1,)
        )
        return result[0] if result else {}

    def get_game_account_by_qq(self, qq_id: str) -> list[str]:
        """根据QQ号获取绑定的所有游戏账号，返回列表"""
        result = self._execute_query(
            f"SELECT account1, account2 FROM {self.table_name} WHERE user_id = %s",
            (qq_id,)
        )
        if result:
            account1 = result[0].get('account1')
            account2 = result[0].get('account2')
            return [a for a in [account1, account2] if a]
        return []
    
import time
import threading

class SimplePendingBindManager:
    def __init__(self, timeout_seconds=30):
        self.pending = {}  # player_name.lower() -> (qq_id, timestamp)
        self.lock = threading.Lock()
        self.timeout = timeout_seconds

    def create_pending(self, qq_id: str, player_name: str):
        with self.lock:
            self.pending[player_name] = (qq_id, time.time())

    def consume_pending(self, player_name: str) -> str | None:
        with self.lock:
            key = player_name.lower()
            if key not in self.pending:
                return None

            qq_id, timestamp = self.pending[key]
            if time.time() - timestamp > self.timeout:
                del self.pending[key]
                return None

            del self.pending[key]
            return qq_id
