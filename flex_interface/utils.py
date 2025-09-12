import logging
import json
from typing import Dict, Any, Optional
import threading
import os
from pathlib import Path
import re
import shutil
import hashlib

logger = logging.getLogger("utils")

class Config:
    def __init__(self, debug=False):
        self.debug = debug
        self.default_config_path = Path("plugins") / "flex_interface" / "flex_interface" / "config.json"
        self.user_config_dir = Path("config") /"flex_interface"
        self.user_config_path = self.user_config_dir / "config.json"
        self.data = self.load_config()
    def load_config(self):
        try:
            if self.debug:
                logger.info(f"debug中, 加载默认用户配置文件: {self.default_config_path}")
                with open(self.default_config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.validate_config(config)
                    return config
            else:
                if self.user_config_path.exists():  # TODO 还原回去另一个文件夹的config加载
                    logger.info(f"加载用户配置文件: {self.user_config_path}")
                    with open(self.user_config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                        self.validate_config(config)
                        return config
                else:
                    logger.info("用户配置文件不存在，加载默认配置并写入一份到用户目录")
                    os.makedirs(self.user_config_dir, exist_ok=True)

                    if self.default_config_path.exists():
                        shutil.copyfile(self.default_config_path, self.user_config_path)
                        with open(self.user_config_path, "r", encoding="utf-8") as f:
                            config = json.load(f)
                            self.validate_config(config)
                            return config
                    else:
                        logger.error("默认配置文件不存在")
                        raise FileNotFoundError("默认配置文件不存在")
        except json.JSONDecodeError:
            logger.error("配置文件格式错误")
            return {}
        except Exception as e:
            logger.error(f"加载配置文件时出错: {e}")
            return {}

    def validate_config(self, config):
        # 添加验证逻辑
        pass

    def reload(self):
        """手动重新加载配置"""
        self.data = self.load_config()

def _build_base_payload(group_id, message):
    """
    构建发送消息的基础 payload 结构
    :param group_id: 群组ID
    :param message: 要发送的消息内容
    :return: 构建的基础 payload
    """
    if isinstance(message, list):
        message = ''.join(message)  # ⬅ 拼接成一个完整的字符串

    return {
        "action": "send_group_msg",
        "params": {
            "group_id": group_id,
            "message": message
        }
    }

def _build_record_payload(group_id, message, character):

    if isinstance(message, list):
        message = ''.join(message)  # ⬅ 拼接成一个完整的字符串

    return {
        "action": "send_group_ai_record",
        "params": {
        "character": character,
        "group_id": group_id,
        "text": message,
        "chat_type": 1
        }
    }


def build_group_list_payload(action):
    """
    构建带有 echo 标记的获取群组列表的 payload 结构
    :return: 带有 echo 标记的获取群组列表的 payload
    """
    return {
        "action": action,
        "params": {},
        "echo": action  # 使用标识符来标记这个请求，通常是为了标识请求
    }


def build_payload(type, *args):
    """
    根据 type 类型和 args 参数构建 payload。

    :param type: 类型（default: 直接发送群消息, reply: 回复某条消息, image: 发送图片）
    :param args: 参数列表(group_id, message, message_id, user_id)
    :return: 构建的 payload 列表（可能是多个payload）
    """
    # 提取 group_id 并确保是列表形式
    if args:
        group_ids = args[0]
        if not isinstance(group_ids, (list, tuple)):
            group_ids = [group_ids]
    
    # 准备其他参数
    other_args = args[1:] if len(args) > 1 else ()
    
    results = []
    
    if type == "default":
        message = other_args[0]
        for group_id in group_ids:
            results.append(_build_base_payload(group_id, message))

    elif type == "reply":
        message, message_id = other_args[:2]
        for group_id in group_ids:
            cq_message = f"[CQ:reply,id={message_id}]{message}"
            results.append(_build_base_payload(group_id, cq_message))

    elif type == "at":
        message, message_id, user_id = other_args[:3]
        for group_id in group_ids:
            cq_at = f"[CQ:at,qq={user_id}] "
            results.append(_build_base_payload(group_id, [cq_at, message]))
    elif type == "record":
        message = other_args[0]
        for group_id in group_ids:
            results.append(_build_record_payload(group_id, message, character="lucy-voice-suxinjiejie"))
    elif type == "get_group_list":
        return [build_group_list_payload(type)]
    return results

def parse_text(text):
    # 按空格拆分字符串
    parts = text.split()
    
    # 保存第一个元素为 command_from_qq
    command_from_qq = parts[0] if parts else None
    
    # 判断是否有剩余元素
    if len(parts) > 1:
        args = parts[1:]  # 将剩余元素存储到 args
    else:
        args = []  # 如果没有剩余元素，args 为 []
    
    return command_from_qq, args

def build_message_from_qq(group_id, nickname, user_id, reply, text_content, at_target=None, group_name=None):
    if group_name:
        group_id = group_name

    # 根据是否回复设置不同的前缀
    if reply:
        if at_target:
            prefix = f"[§a{group_id}§r] <§b{nickname}({user_id})§r> [回复]§b{at_target}§r: "
        else:
            prefix = f"[§a{group_id}§r] <§b{nickname}({user_id})§r> [回复]: "
    elif at_target:
        prefix = f"[§a{group_id}§r] <§b{nickname}({user_id})§r> §6{at_target}§r: "
    else:
        prefix = f"[§a{group_id}§r] <§b{nickname}({user_id})§r>: "

    # 匹配 [图片:xxx]、[视频:xxx]、[语音:xxx] 和 [链接:xxx]
    pattern = r"\[(图片|视频|语音|链接):(https?://[^\]]+)\]"

    # 初始化消息列表
    message_parts = [{"text": prefix}]

    # 分割内容
    parts = re.split(pattern, text_content)

    i = 0
    while i < len(parts):
        if i + 2 < len(parts) and parts[i + 1] in ["图片", "视频", "语音", "链接"]:
            # 添加前面的普通文本（如果有）
            if parts[i]:
                message_parts.append({"text": parts[i]})
            
            # 添加媒体链接部分
            label = parts[i + 1]
            url = parts[i + 2]
            message_parts.append({
                "text": f"[{label}]",
                "color": "gray",
                "click_event": {
                    "action": "open_url",
                    "url": url  # 使用 url 而不是 value
                },
                "hover_event": {
                    "action": "show_text",
                    "value": f"点击查看{label}"  # 使用 value 而不是 contents
                }
            })
            i += 3
        else:
            if parts[i]:
                message_parts.append({"text": parts[i]})
            i += 1

    # 合并连续的文本部分
    merged_parts = []
    current_text = ""
    for part in message_parts:
        if "text" in part and len(part) == 1:  # 只有text字段
            current_text += part["text"]
        else:
            if current_text:
                merged_parts.append({"text": current_text})
                current_text = ""
            merged_parts.append(part)
    
    if current_text:
        merged_parts.append({"text": current_text})

    return json.dumps(merged_parts, ensure_ascii=False)


def has_permission(config, user_id, permission):
    if permission == "default":
        return True  # 默认允许所有人
    elif permission == "admin":
        return user_id in config.get("admin", [])
    else:
        return False  # 如果没有匹配的权限类型，则默认不允许
    
def check_text_length(text: str, max_length: int) -> bool:
    """检查文本长度是否超过限制"""
    if text is None:  # 处理空值
        return False
    return 1 < len(text) <= max_length

def send_gray_italic_message(server, text: str) -> None:
    """
    发送灰色斜体消息（直接使用传入的完整文本）
    
    参数:
        server: 需有 execute() 方法的服务器对象
        text: 完整的消息内容（如 "[苦力仆] Yakult02在密谋..."）
    """
    tellraw_json = {
        "text": text,  # 直接使用传入的完整文本
        "color": "gray",
        "italic": True
    }
    server.execute(f'tellraw @a {json.dumps(tellraw_json, ensure_ascii=False)}')

def get_date_factor():
    import datetime
    """
    获取动态价格系数 (0.8~1.2)
    :param lucky_number: 用户的幸运数字（0-100）
    :return: 保留2位小数的系数
    """
    # 1. 基于日期的基准系数
    today = datetime.date.today()
    date_str = today.strftime("%Y-%m-%d")
    hash_int = int(hashlib.md5(date_str.encode()).hexdigest(), 16)
    date_factor = 0.7 + (hash_int % 10000) / 10000 * 0.7  # 0.7-1.4
    return date_factor