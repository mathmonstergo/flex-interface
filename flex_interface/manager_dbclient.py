import mysql.connector
from mysql.connector import pooling, Error
from mcdreforged.api.all import *

class MySQLManager:
    def __init__(self, server: PluginServerInterface, config: dict, use_pool: bool = True, pool_size: int = 5):
        self.server = server
        self.config = config.get("config", {})
        self.extra_config = config.get("extra_config", {})
        self.use_pool = use_pool
        self.pool_size = pool_size
        self.pool = None
        self.connection = None
        self.cmi_connection = None

        # 初始化连接池或单连接
        if self.use_pool :
            try:
                self.pool = pooling.MySQLConnectionPool(
                    pool_name="mcpool",
                    pool_size=self.pool_size,
                    pool_reset_session=True,
                    **self.config
                )
                self.server.logger.info("MySQL 主库连接池初始化成功")
            except Error as e:
                self.server.logger.critical(f"MySQL 连接池初始化失败: {str(e)}")
                raise
        else:
            self.connection = self._create_connection(single=True)

        # 初始化 CMI 库单连接
        if self.extra_config.get("enable_cmi"):
            self.cmi_connection = self._create_connection(single=True, cmi=True)
            self.server.logger.info("CMI 数据库连接成功")
        else:
            self.server.logger.info("未启用 CMI 数据库连接")

    # -------------------- 连接管理 --------------------
    def _create_connection(self, single=False, cmi=False):
        """创建一个单连接或从池中获取连接"""
        try:
            if self.use_pool and not single and not cmi:
                conn = self.pool.get_connection()
            else:
                db = self.extra_config.get("cmi_database") if cmi else self.config["database"]
                conn = mysql.connector.connect(
                    host=self.config["host"],
                    port=self.config["port"],
                    user=self.config["user"],
                    password=self.config["password"],
                    database=db,
                    autocommit=True
                )
            conn.set_charset_collation(charset="utf8mb4")
            return conn
        except Error as e:
            self.server.logger.critical(f"MySQL 连接失败: {str(e)}")
            raise

    def _ensure_connection(self, cmi=False):
        """确保连接有效，否则自动重连"""
        conn = self.cmi_connection if cmi else self.connection
        try:
            if conn is None or not conn.is_connected():
                self.server.logger.warning("检测到 MySQL 连接不可用，正在重连...")
                if self.use_pool and not cmi:
                    conn = self.pool.get_connection()
                    self.connection = conn
                else:
                    conn = self._create_connection(single=True, cmi=cmi)
                    if cmi:
                        self.cmi_connection = conn
                    else:
                        self.connection = conn
            else:
                conn.ping(reconnect=True, attempts=3, delay=2)
            return conn
        except Error as e:
            self.server.logger.error(f"MySQL 自动重连失败: {str(e)}")
            conn = self._create_connection(single=True, cmi=cmi)
            if cmi:
                self.cmi_connection = conn
            else:
                self.connection = conn
            return conn

    # -------------------- SQL 执行 --------------------
    def safe_query(self, sql: str, args=None):
        """主库同步执行 SQL，自动重连"""
        conn = self._ensure_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, args)
                if sql.strip().lower().startswith("select"):
                    return cursor.fetchall()
                return cursor.rowcount
        except Error as e:
            self.server.logger.error(f"执行 SQL 出错，尝试重连: {e}")
            conn = self._ensure_connection()
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, args)
                if sql.strip().lower().startswith("select"):
                    return cursor.fetchall()
                return cursor.rowcount

    def safe_query_cmi(self, sql: str, args=None):
        """CMI 库同步执行 SQL"""
        if not self.extra_config.get("enable_cmi"):
            raise RuntimeError("CMI 数据库未启用或未连接")
        conn = self._ensure_connection(cmi=True)
        try:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, args)
                if sql.strip().lower().startswith("select"):
                    return cursor.fetchall()
                return cursor.rowcount
        except Error as e:
            self.server.logger.error(f"CMI SQL 执行出错，尝试重连: {e}")
            conn = self._ensure_connection(cmi=True)
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(sql, args)
                if sql.strip().lower().startswith("select"):
                    return cursor.fetchall()
                return cursor.rowcount

    def query_one(self, sql: str, args=None):
        conn = self._ensure_connection()
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(sql, args)
            return cursor.fetchone()

    def query_all(self, sql: str, args=None):
        conn = self._ensure_connection()
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(sql, args)
            if sql.strip().lower().startswith("select"):
                return cursor.fetchall()
            return None

    def test_connection(self):
        conn = self._ensure_connection()
        try:
            return conn.is_connected()
        except Error as e:
            self.server.logger.error(f"MySQL 连接测试失败: {str(e)}")
            return False

    # -------------------- 表初始化 --------------------
    def init_sync(self):
        """初始化表结构"""
        self._init_tables()

    def _init_tables(self):
        table_definitions = {
            'player_bindings': """
                CREATE TABLE IF NOT EXISTS player_bindings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    account1 VARCHAR(16),
                    account2 VARCHAR(16),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY (user_id),
                    INDEX (account1),
                    INDEX (account2)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            'player_daily_sign': """
                CREATE TABLE IF NOT EXISTS player_daily_sign (
                    user_id VARCHAR(64) PRIMARY KEY,
                    card VARCHAR(255),
                    lucky_number INT NOT NULL,
                    last_sign_date DATE NOT NULL,
                    streak_days INT DEFAULT 1,
                    emerald_drops INT DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    cached_balance INT DEFAULT 0,
                    INDEX idx_user_sign_date (user_id, last_sign_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            'sign_reward_logs': """
                CREATE TABLE IF NOT EXISTS sign_reward_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    reward_name VARCHAR(32) NOT NULL,
                    final_amount INT NOT NULL,
                    multiplier INT DEFAULT 1,
                    lucky_number INT NOT NULL,
                    sign_date DATE NOT NULL,
                    category VARCHAR(16) DEFAULT 'generic',
                    is_used TINYINT DEFAULT 0,
                    used_time DATETIME,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_id (user_id),
                    INDEX idx_sign_date (sign_date),
                    INDEX idx_is_used (is_used),
                    INDEX idx_reward_name (reward_name),
                    INDEX idx_user_sign_date (user_id, sign_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            'item_usage_logs': """
                CREATE TABLE IF NOT EXISTS item_usage_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    target_user_id VARCHAR(64),
                    reward_name VARCHAR(32) NOT NULL,
                    source_log_id INT,
                    usage_time DATETIME NOT NULL,
                    effect_result VARCHAR(255),
                    account VARCHAR(64) NOT NULL,
                    quantity INT NOT NULL DEFAULT 1,
                    FOREIGN KEY (source_log_id) REFERENCES sign_reward_logs(id),
                    INDEX idx_user_id (user_id),
                    INDEX idx_target_user (target_user_id),
                    INDEX idx_usage_time (usage_time),
                    INDEX idx_reward_name (reward_name),
                    INDEX idx_account (account)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        }

        for ddl in table_definitions.values():
            try:
                self.safe_query(ddl)
                self.server.logger.info("数据库表初始化成功")
            except Exception as e:
                self.server.logger.critical(f"初始化表失败: {str(e)}")
                raise

    # -------------------- 关闭与事务 --------------------
    def close(self):
        """关闭数据库连接"""
        if not self.use_pool:
            if self.connection:
                try:
                    self.connection.close()
                except Exception as e:
                    self.server.logger.warning(f"关闭单连接时出错: {e}")
            if self.cmi_connection:
                try:
                    self.cmi_connection.close()
                except Exception as e:
                    self.server.logger.warning(f"关闭 CMI 连接时出错: {e}")
        else:
            # 连接池模式，不手动关闭池内连接
            self.pool = None
            self.server.logger.info("MySQL 连接池引用已清理，GC 会回收")

    def transaction(self, cmi=False):
        """
        返回一个事务上下文管理器
        usage:
        with mysql_mgr.transaction() as trx:
            trx.cursor.execute(...)
        """
        conn = self._ensure_connection(cmi=cmi)
        return MySQLTransaction(conn)
    
class MySQLTransaction:
    def __init__(self, connection):
        self.connection = connection
        self.cursor = None

    def __enter__(self):
        self.cursor = self.connection.cursor(dictionary=True)
        # 如果当前连接没有事务，才开始新事务
        if not self.connection.in_transaction:
            self.connection.start_transaction()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            if self.connection.in_transaction:
                self.connection.commit()
        else:
            if self.connection.in_transaction:
                self.connection.rollback()
        if self.cursor:
            self.cursor.close()