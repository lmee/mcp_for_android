"""
MCP (模型上下文协议) 协议定义

定义MCP协议中使用的基本数据结构和常量
"""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# 协议动作类型
class MCPActionTypes:
    """MCP协议支持的操作类型"""
    CLICK = "click"
    LONG_CLICK = "long_click"
    SWIPE = "swipe"
    TYPE_TEXT = "type_text"
    SCROLL = "scroll"
    LAUNCH_APP = "launch_app"
    PRESS_BACK = "press_back"
    PRESS_HOME = "press_home"
    PRESS_RECENTS = "press_recents"
    FIND_ELEMENT = "find_element"
    GET_TEXT = "get_text"
    GET_UI_STATE = "get_ui_state"
    GET_INSTALLED_APPS = "get_installed_apps"
    EXECUTE_TASK = "execute_task"


# 协议事件类型
class MCPEventTypes:
    """MCP协议支持的事件类型"""
    UI_CHANGED = "ui_changed"
    APP_LAUNCHED = "app_launched"
    TEXT_CHANGED = "text_changed"
    SCREEN_ON = "screen_on"
    SCREEN_OFF = "screen_off"

@dataclass
# 请求和响应类
class Request:
    def __init__(self, request_id: str, action_type: str, parameters: Dict = None, context: Any = None):
        self.request_id = request_id
        self.action_type = action_type
        self.parameters = parameters or {}
        self.context = context
        self.user_instruction = None

@dataclass
class Response:
    def __init__(self, request_id: str, status: str, data: Dict = None, error: str = None, device_state=None):
        self.request_id = request_id
        self.status = status
        self.data = data or {}
        self.error = error
        self.device_state = device_state

@dataclass
class Context:
    def __init__(self, session_id: str = None):
        self.session_id = session_id
        self.history = []
        self.memory = {}

@dataclass
class DeviceState:
    def __init__(self):
        self.current_package = None
        self.current_activity = None
        self.screen_state = None
        self.ui_hierarchy = {}
        self.visible_text = []
        self.device_info = {}


@dataclass
class SessionContext:
    def __init__(self, session_id: str, device_id: str, user_instruction: str = None):
        self.session_id = session_id
        self.device_id = device_id
        self.user_instruction = user_instruction
        self.active = True
        self.created_at = time.time()
        self.last_updated = time.time()


@dataclass
class TaskContext:
    def __init__(self, task_id: str, task_type: str, parameters: Dict = None):
        self.task_id = task_id
        self.task_type = task_type
        self.parameters = parameters or {}
        self.status = "pending"
        self.created_at = time.time()
        self.completed_at = None
