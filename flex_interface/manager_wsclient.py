
import json
import logging
import websocket
import threading
import time
logger = logging.getLogger("websocket")

class WebSocketClient:
    def __init__(self, ws_url, on_message_callback, on_status_callback=None):
        self.ws_url = ws_url
        self.on_message_callback = on_message_callback
        self.ws = None
        self._stop_flag = False
        self._ws_thread = None
        self._reconnect_delay = 5  # 秒
        self._reconnect_thread = None
        self.on_status_callback = on_status_callback
        self._lock = threading.Lock() 
        self.logger = logger
    def on_message(self, ws, message):
        """处理 WebSocket 消息"""
        try:
            data = json.loads(message)
            # logger.debug(f"接收到消息: {data}")
            self.on_message_callback(data)
        except Exception as e:
            logger.error(f"处理 WebSocket 消息时出错: {e}")

    def on_error(self, ws, error):
        logger.error(f"WebSocket 错误: {error}")
        self._reconnect()

    def on_close(self, ws, close_status_code, close_msg):
        logger.warning("WebSocket 连接已关闭")
        if self.on_status_callback:
            self.on_status_callback(connected=False)

    def _reconnect(self):
        if self._stop_flag:
            logger.info("WebSocket 已标记为停止，不进行重连")
            return

        if getattr(self, '_reconnecting', False):
            logger.info("重连已在进行中，跳过")
            return

        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.warning(f"关闭旧 ws 失败: {e}")

        self._reconnecting = True

        def delayed_reconnect():
            logger.info(f"{self._reconnect_delay}秒后尝试重新连接 WebSocket...")
            time.sleep(self._reconnect_delay)
            if not self._stop_flag:
                logger.info("开始重新连接 WebSocket...")
                self.start()
            self._reconnecting = False

        threading.Thread(target=delayed_reconnect, daemon=True).start()

    def reconnect(self):
        """公共调用"""
        self.stop()
        self._reconnect()

    def on_open(self, ws):
        """处理 WebSocket 连接成功"""
        logger.info("WebSocket 连接成功")
        if self.on_status_callback:
            self.on_status_callback(connected=True)

    def start(self):
        """启动 WebSocket 客户端"""
        with self._lock:
            if self._ws_thread and self._ws_thread.is_alive():
                logger.info("已有 WebSocket 线程在运行，跳过启动")
                return

            logger.info("启动新的 WebSocket 连接线程")
            self._stop_flag = False
            self._ws_thread = threading.Thread(target=self._run, name="ws_thread", daemon=True)
            self._ws_thread.start()

    def _run(self):
        """运行 WebSocket"""
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.ws.run_forever()

    def stop(self):
        """停止 WebSocket 客户端"""
        if self.ws:
            self.ws.close()
            logger.info("WebSocket Client已关闭")

    def send_group_message(self, payload):
        """发送群消息，支持单个或多个群号"""
        if not isinstance(payload, list):
            payload = [payload]
        
        for p in payload:
            try:
                message_json = json.dumps(p)
                if self.ws and self.ws.sock and self.ws.sock.connected:
                    self.ws.send(message_json)
                else:
                    logger.warning("WebSocket 未连接或已断开，尝试重连？")
            except Exception as e:
                logger.exception(f"发送消息失败: {e}, 消息内容: {p}")