import json
from mcdreforged.api.event import MCDRPluginEvents
from mcdreforged.api.types import PluginServerInterface, Info
from mcdreforged.api.all import *
from .manager_wsclient import WebSocketClient
from .manager_autochat import AutoChat
import minecraft_data_api as api
import logging
import threading
from .utils import *
from .main import flexInterface
from .manager_config import config
import time


# 配置日志
logging.basicConfig(
    level=logging.INFO,  # 设置日志级别为 DEBUG
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("debug.log"),  # 将日志输出到文件
        logging.StreamHandler()  # 将日志输出到控制台
    ]
)

logger = logging.getLogger("init")
    
# 全局变量
mysql_mgr = None
manager_wsclient = None
plugin_instance = None
manager_autochat = None

def on_load(server: PluginServerInterface, old):
    if not config:
        server.logger.error("配置文件加载失败")
        return
    server.config = config
    server.mc_api = api
    server.xpboost_status = False  # mcmmo插件双倍经验初始状态
    # 初始化插件,wsclient,获取群组信息
    initialize_plugin_thread(server)

    # 3. 注册事件与命令
    register_event_listeners(server)
    register_commands(server)

    server.logger.info("插件加载完毕 ✅")

def on_unload(server: PluginServerInterface):
    server.plugin.close()
    server.wscl.stop()
    server.plugin.mysql_mgr.close()
    server.chat.close()
def initialize_plugin_thread(server: PluginServerInterface):
    """初始化插件的线程"""
    try:
        plugin_instance = flexInterface(server)
        plugin_instance.initialize(config.get("mysql_config"))
        server.plugin = plugin_instance  # 挂载到server
        server.logger.info("flex_interface已挂载到server")
        initialize_websocket(server)       # 确保 WebSocket 初始化完成
        initialize_autochat(server)
        initialize_group_info(server)   
    except Exception as e:
        server.logger.critical(f"插件启动失败: {str(e)}")
        return

def initialize_websocket(server: PluginServerInterface):
    """初始化WebSocket连接"""
    global manager_wsclient
    manager_wsclient = WebSocketClient(
        config.get("ws_url"),
        server.plugin.on_websocket_data,
        server.plugin.on_ws_status_change
    )
    server.wscl = manager_wsclient  # 挂载到 server
    manager_wsclient.start()

def initialize_autochat(server: PluginServerInterface):
    """初始化autochat实例"""
    global manager_autochat
    manager_autochat = AutoChat(server)
    server.chat = manager_autochat  # 挂载到 server

def initialize_group_info(server: PluginServerInterface):
    """初始化群组信息"""
    def _init():
        time.sleep(5)  # 等待服务启动
        payload = build_payload(type="get_group_list")
        manager_wsclient.send_group_message(payload)
        server.logger.info("群组初始化请求已发送")
    threading.Thread(target=_init, daemon=True).start()

def register_event_listeners(server: PluginServerInterface):
    """注册所有事件监听器"""
    listeners = {
        MCDRPluginEvents.GENERAL_INFO: server.plugin.on_info,
        MCDRPluginEvents.PLAYER_JOINED: server.plugin.on_player_joined,
        MCDRPluginEvents.PLAYER_LEFT: server.plugin.on_player_left,
        MCDRPluginEvents.SERVER_STARTUP: server.plugin.on_server_start,
        MCDRPluginEvents.SERVER_STOP: server.plugin.on_server_stop,
        "PlayerDeathEvent": server.plugin.on_player_death,
        "PlayerAdvancementEvent": server.plugin.on_player_advancement
    }
    
    for event, callback in listeners.items():
        server.register_event_listener(event, callback)

def register_commands(server: PluginServerInterface):
    """注册所有命令"""
    server.register_command(Literal('!!flex_check').runs(check_db_status))
    server.register_command(Literal('!!get_group_list').runs(
        lambda src: get_group_list_by_command(src, server)
    ))

def get_group_list_by_command(src: CommandSource, server: PluginServerInterface):
    """处理获取群列表命令"""
    payload = build_payload(type="get_group_list")
    manager_wsclient.send_group_message(payload)
    src.reply('正在更新群列表...')

def check_db_status(source: CommandSource):
    """检查数据库状态"""
    if mysql_mgr and mysql_mgr.test_connection():
        source.reply("§a数据库连接正常")
    else:
        source.reply("§c数据库连接异常")
