import mysql.connector
from mysql.connector import Error
from mcdreforged.api.all import *

class MySQLManager:
    def __init__(self, server: PluginServerInterface, config: dict):
        self.server = server
        self.config = config
        self.connection = None
        self.cmi_connection = None  # 新增：CMI库连接

    def init_sync(self):
        """同步初始化数据库连接池和表结构"""
        self._init_connection()
        self._init_tables()

    def _init_connection(self):
        """初始化数据库连接（可选连接 CMI）"""
        try:
            # 主库连接（flex）
            self.connection = mysql.connector.connect(
                host=self.config['host'],
                port=self.config['port'],
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['database'],
                autocommit=True
            )
            self.connection.set_charset_collation(charset='utf8mb4')
            self.server.logger.info("MySQL 主库连接成功")

            # ✅ 如果启用 CMI 才连接
            if self.config.get('enable_cmi'):
                self.cmi_connection = mysql.connector.connect(
                    host=self.config['host'],
                    port=self.config['port'],
                    user=self.config['user'],
                    password=self.config['password'],
                    database=self.config['cmi_database'],
                    autocommit=True
                )
                self.cmi_connection.set_charset_collation(charset='utf8mb4')
                self.server.logger.info("CMI 数据库连接成功")
            else:
                self.server.logger.info("未启用 CMI 数据库连接")

        except Error as e:
            self.server.logger.critical(f"MySQL 连接初始化失败: {str(e)}")
            raise

    def _init_tables(self):
        """创建必要的表结构"""
        table_definitions = {
        'player_bindings': """
            CREATE TABLE IF NOT EXISTS player_bindings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
                account1 VARCHAR(16) COMMENT '绑定的第一个游戏账号',
                account2 VARCHAR(16) COMMENT '绑定的第二个游戏账号',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY (user_id),
                INDEX (account1),
                INDEX (account2)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        'player_daily_sign': """
            CREATE TABLE IF NOT EXISTS player_daily_sign (
                user_id VARCHAR(64) PRIMARY KEY COMMENT '用户ID',
                card VARCHAR(255) COMMENT '群昵称',  -- 新增字段
                lucky_number INT NOT NULL COMMENT '幸运数字(1-100)',
                last_sign_date DATE NOT NULL COMMENT '上次签到日期',
                streak_days INT DEFAULT 1 COMMENT '连续签到天数',
                emerald_drops INT DEFAULT 0 COMMENT '玩家拥有的绿宝石数量',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
                cached_balance INT DEFAULT 0 COMMENT '缓存的玩家余额',  -- 新增列
                INDEX idx_user_sign_date (user_id, last_sign_date)  -- 添加复合索引
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='玩家每日签到记录'
        """,
        'sign_reward_logs': """
            CREATE TABLE IF NOT EXISTS sign_reward_logs (
                id INT AUTO_INCREMENT PRIMARY KEY COMMENT '记录ID',
                user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
                reward_name VARCHAR(32) NOT NULL COMMENT '奖励名称',
                final_amount INT NOT NULL COMMENT '实际获得数量',
                multiplier INT DEFAULT 1 COMMENT '幸运倍数(1-4)', 
                lucky_number INT NOT NULL COMMENT '幸运数字(1-100)',
                sign_date DATE NOT NULL COMMENT '获得日期',
                category VARCHAR(16) DEFAULT 'generic' COMMENT '奖励类别',
                is_used TINYINT DEFAULT 0 COMMENT '是否已使用(0=未用,1=已用)',
                used_time DATETIME COMMENT '使用时间',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_user_id (user_id),
                INDEX idx_sign_date (sign_date),
                INDEX idx_is_used (is_used),
                INDEX idx_reward_name (reward_name),
                INDEX idx_user_sign_date (user_id, sign_date)  -- 添加复合索引
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='签到奖励获得记录'
        """,
        'item_usage_logs': """
            CREATE TABLE IF NOT EXISTS item_usage_logs (
                id INT AUTO_INCREMENT PRIMARY KEY COMMENT '日志ID',
                user_id VARCHAR(64) NOT NULL COMMENT '使用者ID',
                target_user_id VARCHAR(64) COMMENT '目标用户ID',
                reward_name VARCHAR(32) NOT NULL COMMENT '使用道具名称',
                source_log_id INT COMMENT '关联的签到记录ID',
                usage_time DATETIME NOT NULL COMMENT '使用时间',
                effect_result VARCHAR(255) COMMENT '效果执行结果',
                account VARCHAR(64) NOT NULL COMMENT '被执行道具的账号',  -- 实际被执行的游戏id
                quantity INT NOT NULL DEFAULT 1 COMMENT '使用的道具数量',  -- 新增字段，记录每次使用的道具数量
                FOREIGN KEY (source_log_id) REFERENCES sign_reward_logs(id),
                INDEX idx_user_id (user_id),
                INDEX idx_target_user (target_user_id),
                INDEX idx_usage_time (usage_time),
                INDEX idx_reward_name (reward_name),
                INDEX idx_account (account)  -- 实际被执行的游戏id
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='道具使用日志记录';
        """}

        for ddl in table_definitions.values():
            try:
                self.safe_query(ddl)
                self.server.logger.info("数据库初始化成功")
            except Exception as e:
                self.server.logger.critical(f"初始化表失败: {str(e)}")
                raise
            
    def safe_query_cmi(self, sql: str, args=None):
        """对 CMI 数据库执行 SQL 操作"""
        if not self.cmi_connection:
            raise RuntimeError("CMI 数据库未启用或未连接，无法执行操作。")
        try:
            with self.cmi_connection.cursor(dictionary=True) as cursor:
                cursor.execute(sql, args)
                if sql.strip().lower().startswith("select"):
                    return cursor.fetchall()
                return cursor.rowcount
        except Error as e:
            self.server.logger.error(f"CMI SQL 执行出错: {e}")
            raise

    def safe_query(self, sql: str, args=None):
        """同步执行 SQL，支持查询和写入"""
        try:
            with self.connection.cursor(dictionary=True) as cursor:
                cursor.execute(sql, args)
                if sql.strip().lower().startswith("select"):
                    return cursor.fetchall()
                return cursor.rowcount  # ✅ 返回影响行数
        except Error as e:
            self.server.logger.error(f"执行 SQL 出错: {e}")
            raise

    def query_one(self, sql: str, args=None):
        """查询一条记录"""
        try:
            with self.connection.cursor(dictionary=True) as cursor:
                cursor.execute(sql, args)
                return cursor.fetchone()  # 返回第一行数据
        except Error as e:
            self.server.logger.error(f"执行 SQL 出错: {e}")
            raise
    
    def query_all(self, sql: str, args: tuple = None):
        """查询并返回所有记录"""
        try:
            with self.connection.cursor(dictionary=True) as cursor:
                cursor.execute(sql, args)
                # 如果是 SELECT 查询，返回所有结果
                if sql.strip().lower().startswith("select"):
                    return cursor.fetchall()
                # 否则不返回数据
                return None
        except Exception as e:
            self.server.logger.error(f"执行 SQL 查询出错: {e}")
            raise
    def test_connection(self):
        """同步测试数据库连接"""
        try:
            return self.connection.is_connected()
        except Error as e:
            self.server.logger.error(f"MySQL 连接测试失败: {str(e)}")
            return False

    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.server.logger.info("MySQL 连接已关闭")

    def transaction(self):
        """返回一个上下文管理器来处理事务"""
        return MySQLTransaction(self.connection)

class MySQLTransaction:
    def __init__(self, connection):
        self.connection = connection
        self.cursor = None

    def __enter__(self):
        """开启事务"""
        self.cursor = self.connection.cursor(dictionary=True)
        self.connection.start_transaction()  # 开始事务
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """提交事务或回滚"""
        if exc_type is None:
            self.connection.commit()  # 提交事务
        else:
            self.connection.rollback()  # 回滚事务
        if self.cursor:
            self.cursor.close()