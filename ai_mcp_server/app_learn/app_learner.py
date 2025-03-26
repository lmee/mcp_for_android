"""
应用自学习模块

允许模型自动学习Android设备上的应用操作方式
"""
import ast
import os
import json
import logging
import time
import uuid
from typing import Dict, List, Optional

from mcp.mcp_protocol import (
    Request, Response, Context, MCPActionTypes
)

# 配置日志
logger = logging.getLogger("AppLearner")


class AppLearner:
    """应用学习器类"""
    
    def __init__(self, app_data_path: str = "app_knowledge"):
        """初始化应用学习器"""
        self.app_data_path = app_data_path
        self.app_knowledge = {}
        self.learning_sessions = {}
        
        # 创建应用数据目录
        os.makedirs(app_data_path, exist_ok=True)
        
        # 加载现有应用知识
        self._load_app_knowledge()
    
    def _load_app_knowledge(self):
        """加载应用知识"""
        try:
            knowledge_file = os.path.join(self.app_data_path, "app_knowledge.json")
            if os.path.exists(knowledge_file):
                with open(knowledge_file, "r", encoding="utf-8") as f:
                    self.app_knowledge = json.load(f)
                logger.info(f"Loaded knowledge for {len(self.app_knowledge)} apps")
        except Exception as e:
            logger.error(f"Error loading app knowledge: {e}")
            self.app_knowledge = {}
    
    def _save_app_knowledge(self):
        """保存应用知识"""
        try:
            knowledge_file = os.path.join(self.app_data_path, "app_knowledge.json")
            with open(knowledge_file, "w", encoding="utf-8") as f:
                json.dump(self.app_knowledge, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved knowledge for {len(self.app_knowledge)} apps")
        except Exception as e:
            logger.error(f"Error saving app knowledge: {e}")
    
    def start_app_learning(self, device_id: str, server) -> str:
        """开始一次应用学习会话"""
        # 创建学习会话
        session_id = str(uuid.uuid4())

        self.learning_sessions[session_id] = {
            "device_id": device_id,
            "status": "starting",
            "discovered_apps": [],
            "current_app": None,
            "current_task": None,
            "actions": [],
            "start_time": time.time()
        }
        
        # 开始学习流程
        self._schedule_next_learning_step(session_id, server)
        
        return session_id
    
    def _schedule_next_learning_step(self, session_id: str, server):
        print("安排下一个学习步骤")
        """安排下一个学习步骤"""
        if session_id not in self.learning_sessions:
            logger.error(f"Learning session not found: {session_id}")
            return
        
        session = self.learning_sessions[session_id]
        print(f"Jerry-->{session['status']}")
        if session["status"] == "starting":
            # 第一步：获取已安装应用列表
            self._get_installed_apps(session_id, server)
        
        elif session["status"] == "app_discovery":
            # 应用发现完成，开始学习每个应用
            if session["discovered_apps"]:
                # 选择下一个要学习的应用
                app = session["discovered_apps"].pop(0)
                session["current_app"] = app
                session["status"] = "learning_app"
                
                # 开始学习该应用
                self._start_learning_app(session_id, app, server)
            else:
                # 所有应用都已学习完成
                session["status"] = "completed"
                logger.info(f"Learning session {session_id} completed")
                
                # 保存学习到的知识
                self._save_app_knowledge()
                
                # 清理会话
                self.learning_sessions.pop(session_id, None)
        
        elif session["status"] == "learning_app":
            # 正在学习特定应用，执行下一个学习任务
            if session["current_task"] == "explore_ui":
                # UI探索完成，开始学习常见操作
                self._learn_common_operations(session_id, server)
            elif session["current_task"] == "common_operations":
                # 常见操作学习完成，回到主屏幕
                self._return_to_home(session_id, server)
            else:
                # 应用学习完成，继续下一个应用
                session["status"] = "app_discovery"
                session["current_app"] = None
                session["current_task"] = None
                
                # 更新应用知识
                self._save_app_knowledge()
                
                # 安排下一个学习步骤
                self._schedule_next_learning_step(session_id, server)
    
    def _get_installed_apps(self, session_id: str, server):
        """获取已安装应用列表"""
        session = self.learning_sessions[session_id]
        device_id = session["device_id"]
        print(f"server.devices-->{len(server.devices)}")
        # 获取设备连接
        with server.devices_lock:
            if device_id not in server.devices:
                logger.error(f"Device not found: {device_id}")
                return

            device = server.devices[device_id]
        print("准备请求获取应用列表。。。。")
        # 创建请求
        request = Request(
            request_id=str(uuid.uuid4()),
            action_type="get_installed_apps",  # 需要在客户端实现此操作类型
            context=Context(session_id=session_id)
        )
        
        # 发送请求并设置回调
        device.send_request(request, lambda response: self._on_apps_received(
            response, session_id, server))
        
        session["status"] = "waiting_for_apps"
    
    def _on_apps_received(self, response: Response, session_id: str, server):
        """处理已安装应用的响应"""
        if session_id not in self.learning_sessions:
            return
        
        session = self.learning_sessions[session_id]
        
        if response.status != "success":
            logger.error(f"Failed to get installed apps: {response.error}")
            session["status"] = "error"
            return
        
        # 获取应用列表
        apps = ast.literal_eval(response.data.get("message", "").strip())
        logger.info(f"Received {len(apps)},app-->{type(apps)}, installed apps")
        
        # 过滤应用列表，只保留常用/感兴趣的应用
        interesting_apps = self._filter_interesting_apps(apps)
        logger.info(f"Filtered to {len(interesting_apps)} interesting apps")
        
        # 更新会话状态
        session["discovered_apps"] = interesting_apps
        session["status"] = "app_discovery"
        
        # 继续下一步
        self._schedule_next_learning_step(session_id, server)
    
    def _filter_interesting_apps(self, apps: List[Dict]) -> List[Dict]:
        """过滤出感兴趣的应用"""
        # 常见的应用包名前缀
        interesting_prefixes = [
            "com.android.",         # Android系统应用
            "com.google.android.",  # Google应用
            "com.tencent.",         # 腾讯应用(微信、QQ等)
            "com.netease.",         # 网易应用(云音乐等)
            "com.baidu.",           # 百度应用
            "com.alibaba.",         # 阿里巴巴应用
            "com.sina.",            # 新浪应用
            "com.xiaomi.",          # 小米应用
            "com.huawei.",          # 华为应用
            "tv.danmaku.bili",      # 哔哩哔哩
            "com.smile.gifmaker",   # 快手
            "com.ss.android.ugc.aweme",  # 抖音
        ]
        
        # 优先级应用(音乐、视频、社交等)
        priority_apps = [
            "com.tencent.mm",       # 微信
            "com.tencent.mobileqq", # QQ
            "com.netease.cloudmusic",  # 网易云音乐
            "com.tencent.qqmusic",  # QQ音乐
            "com.kugou.android",    # 酷狗音乐
            "com.ss.android.ugc.aweme",  # 抖音
            "tv.danmaku.bili",      # 哔哩哔哩
            "com.baidu.searchbox",  # 百度
            "com.sina.weibo",       # 微博
            "com.android.settings", # 设置
            "com.android.contacts", # 联系人
            "com.android.mms",      # 短信
            "com.android.dialer",   # 电话
        ]
        
        # 先添加高优先级应用
        filtered_apps = []
        for app in apps:
            package_name = app.get("packageName")
            if package_name in priority_apps:
                filtered_apps.append(app)
        
        # 然后添加其他感兴趣的应用
        for app in apps:
            package_name = app.get("packageName")
            if package_name not in [a.get("packageName") for a in filtered_apps]:
                if any(package_name.startswith(prefix) for prefix in interesting_prefixes):
                    filtered_apps.append(app)
        
        # 如果应用太多，只保留前20个
        if len(filtered_apps) > 20:
            filtered_apps = filtered_apps[:20]
        
        return filtered_apps
    
    def _start_learning_app(self, session_id: str, app: Dict, server):
        """开始学习特定应用"""
        if session_id not in self.learning_sessions:
            return
        
        session = self.learning_sessions[session_id]
        device_id = session["device_id"]
        package_name = app.get("packageName")
        app_name = app.get("appName", package_name)
        
        logger.info(f"Starting to learn app: {app_name} ({package_name})")
        
        # 获取设备连接
        logger.info(f"当前的设备--》{server.devices}")
        with server.devices_lock:
            if device_id not in server.devices:
                logger.error(f"Device not found: {device_id}")
                return
            
            device = server.devices[device_id]
        
        # 初始化应用知识(如果不存在)
        if package_name not in self.app_knowledge:
            self.app_knowledge[package_name] = {
                "appName": app_name,
                "packageName": package_name,
                "elements": {},
                "screens": {},
                "actions": {},
                "lastLearned": time.time()
            }
        
        # 创建启动应用的请求
        request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.LAUNCH_APP,
            parameters={"packageName": package_name},
            context=Context(session_id=session_id)
        )
        
        # 发送请求并设置回调
        device.send_request(request, lambda response: self._on_app_launched(
            response, session_id, server))
        
        session["current_task"] = "launching"
    
    def _on_app_launched(self, response: Response, session_id: str, server):
        """应用启动后回调"""
        if session_id not in self.learning_sessions:
            return
        
        session = self.learning_sessions[session_id]
        
        if response.status != "success":
            logger.error(f"Failed to launch app: {response.error}")
            # 尝试下一个应用
            session["status"] = "app_discovery"
            self._schedule_next_learning_step(session_id, server)
            return
        
        # 短暂等待应用启动
        time.sleep(4)
        
        # 开始探索UI
        self._explore_app_ui(session_id, server)
    
    def _explore_app_ui(self, session_id: str, server):
        """探索应用UI"""
        if session_id not in self.learning_sessions:
            return
        
        session = self.learning_sessions[session_id]
        device_id = session["device_id"]
        
        # 获取设备连接
        with server.devices_lock:
            if device_id not in server.devices:
                logger.error(f"Device not found: {device_id}")
                return
            
            device = server.devices[device_id]
        
        # 创建获取UI状态的请求
        request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.GET_UI_STATE,
            context=Context(session_id=session_id)
        )
        
        # 发送请求并设置回调
        device.send_request(request, lambda response: self._analyze_app_ui(
            response, session_id, server))
        
        session["current_task"] = "explore_ui"
    
    def _analyze_app_ui(self, response: Response, session_id: str, server):
        """分析应用UI结构"""
        if session_id not in self.learning_sessions:
            return
        
        session = self.learning_sessions[session_id]

        print(f"AppLearner--->_analyze_app_ui----response.status-->{response.status}")

        if response.status != "success":
            logger.error(f"Failed to get UI state: {response.error}")
            session["current_task"] = "error"
            self._schedule_next_learning_step(session_id, server)
            return
        
        # 获取当前应用信息
        package_name = session["current_app"].get("packageName")
        device_state = response.device_state
        if device_state and device_state.current_package:
            package_name = device_state.current_package
            activity_name = device_state.current_activity  # 添加获取当前Activity的代码

            # 存储应用信息
            self.app_knowledge[package_name] = self.app_knowledge.get(package_name, {})
            self.app_knowledge[package_name]["packageName"] = package_name
            self.app_knowledge[package_name]["mainActivity"] = activity_name  # 保存主Activity信息

            # 如果包含完整组件名，也保存
            if activity_name and "/" in activity_name:
                self.app_knowledge[package_name]["fullComponent"] = activity_name
            elif activity_name:
                # 构建完整组件名
                self.app_knowledge[package_name]["fullComponent"] = f"{package_name}/{activity_name}"
        # print(f"AppLearner--->_analyze_app_ui----response.device_state-->{response.device_state}---package_name--->{package_name}")
        if not device_state:
            logger.error("No device state in response")
            session["current_task"] = "error"
            self._schedule_next_learning_step(session_id, server)
            return
        
        # 分析UI，识别关键元素
        key_elements = self._identify_key_elements(device_state)
        
        # 分析屏幕类型
        screen_type = self._identify_screen_type(device_state)
        
        # 存储UI元素信息
        app_knowledge = self.app_knowledge.get(package_name, {})
        elements = app_knowledge.get("elements", {})
        
        for element_id, element_info in key_elements.items():
            elements[element_id] = element_info
        
        app_knowledge["elements"] = elements
        
        # 存储屏幕信息
        screens = app_knowledge.get("screens", {})
        if screen_type and screen_type not in screens:
            screens[screen_type] = {
                "elements": list(key_elements.keys()),
                "lastSeen": time.time()
            }
        
        app_knowledge["screens"] = screens
        self.app_knowledge[package_name] = app_knowledge
        
        # 更新探索状态
        session["current_task"] = None
        
        # 继续下一步
        self._schedule_next_learning_step(session_id, server)
    
    def _identify_key_elements(self, device_state) -> Dict[str, Dict]:
        """识别UI中的关键元素"""
        key_elements = {}

        print(f"AppLearner-->_identify_key_elements--->{device_state}")
        # 获取UI层次结构
        # 处理device_state可能是字符串的情况
        if isinstance(device_state, str):
            try:
                # 尝试解析JSON字符串
                device_state_dict = json.loads(device_state)
                ui_hierarchy = device_state_dict.get('ui_hierarchy', {})
            except json.JSONDecodeError:
                print(f"无法解析device_state JSON: {device_state}")
                return key_elements
            except Exception as e:
                print(f"处理device_state时出错: {e}")
                return key_elements
        else:
            # 如果是对象，则直接获取ui_hierarchy
            ui_hierarchy = device_state.ui_hierarchy if device_state else {}
        
        # 这里将使用更复杂的逻辑识别关键元素
        # 下面是一个简化版本
        
        # 1. 识别搜索相关元素
        search_elements = self._find_elements_by_pattern(ui_hierarchy, 
                                                       ["搜索", "查找", "search", "find"])
        for i, element in enumerate(search_elements):
            element_id = f"search_{i}"
            key_elements[element_id] = {
                "type": "search",
                "bounds": element.get("bounds", {}),
                "text": element.get("text", ""),
                "contentDescription": element.get("contentDescription", ""),
                "selector": self._create_selector_for_element(element)
            }
        
        # 2. 识别输入框
        input_elements = self._find_elements_by_class(ui_hierarchy, 
                                                    ["android.widget.EditText"])
        for i, element in enumerate(input_elements):
            element_id = f"input_{i}"
            key_elements[element_id] = {
                "type": "input",
                "bounds": element.get("bounds", {}),
                "hint": element.get("text", ""),
                "selector": self._create_selector_for_element(element)
            }
        
        # 3. 识别按钮
        button_elements = self._find_elements_by_class(ui_hierarchy, 
                                                    ["android.widget.Button"])
        for i, element in enumerate(button_elements):
            element_id = f"button_{i}"
            key_elements[element_id] = {
                "type": "button",
                "bounds": element.get("bounds", {}),
                "text": element.get("text", ""),
                "contentDescription": element.get("contentDescription", ""),
                "selector": self._create_selector_for_element(element)
            }
        
        # 4. 识别列表
        list_elements = self._find_elements_by_class(ui_hierarchy, 
                                                   ["android.widget.ListView", 
                                                   "android.widget.RecyclerView"])
        for i, element in enumerate(list_elements):
            element_id = f"list_{i}"
            key_elements[element_id] = {
                "type": "list",
                "bounds": element.get("bounds", {}),
                "selector": self._create_selector_for_element(element)
            }
        
        # 5. 识别导航按钮
        nav_elements = self._find_navigation_elements(ui_hierarchy)
        for i, element in enumerate(nav_elements):
            element_id = f"nav_{i}"
            key_elements[element_id] = {
                "type": "navigation",
                "bounds": element.get("bounds", {}),
                "text": element.get("text", ""),
                "contentDescription": element.get("contentDescription", ""),
                "selector": self._create_selector_for_element(element)
            }
        
        return key_elements
    
    def _find_elements_by_pattern(self, ui_hierarchy: Dict, patterns: List[str]) -> List[Dict]:
        """通过文本或描述模式查找元素"""
        results = []
        print(f"AppLearner-->_find_elements_by_pattern--->{json.dumps(ui_hierarchy)}")
        def search_node(node):
            text = node.get("text", "")
            content_desc = node.get("contentDescription", "")
            
            # 检查文本或内容描述是否匹配
            if text and any(pattern in text for pattern in patterns):
                results.append(node)
            elif content_desc and any(pattern in content_desc for pattern in patterns):
                results.append(node)
            
            # 递归搜索子节点
            for child in node.get("children", []):
                search_node(child)
        
        search_node(ui_hierarchy)
        return results
    
    def _find_elements_by_class(self, ui_hierarchy: Dict, class_names: List[str]) -> List[Dict]:
        """通过类名查找元素"""
        results = []
        
        def search_node(node):
            class_name = node.get("className", "")
            
            # 检查类名是否匹配
            if class_name and any(class_name == cn for cn in class_names):
                results.append(node)
            
            # 递归搜索子节点
            for child in node.get("children", []):
                search_node(child)
        
        search_node(ui_hierarchy)
        return results
    
    def _find_navigation_elements(self, ui_hierarchy: Dict) -> List[Dict]:
        """查找导航元素"""
        # 导航相关的文本模式
        nav_patterns = ["首页", "我的", "发现", "消息", "home", "me", "discover", "message"]
        
        # 首先尝试按文本查找
        results = self._find_elements_by_pattern(ui_hierarchy, nav_patterns)
        
        # 如果没有找到，尝试查找底部栏元素
        if not results:
            # 查找可能的底部导航栏
            bottom_area_nodes = []
            
            def find_bottom_nodes(node, depth=0):
                # 获取元素边界
                bounds = node.get("bounds", {})
                bottom = bounds.get("bottom", 0)
                
                # 判断是否在屏幕底部区域
                if bottom > 1800:  # 假设大多数屏幕高度在2000左右
                    bottom_area_nodes.append(node)
                
                # 递归搜索子节点(限制深度以提高效率)
                if depth < 10:
                    for child in node.get("children", []):
                        find_bottom_nodes(child, depth + 1)
            
            find_bottom_nodes(ui_hierarchy)
            
            # 从底部区域节点中查找可能的导航按钮
            for node in bottom_area_nodes:
                # 检查是否有多个子节点(可能是导航栏)
                children = node.get("children", [])
                if 3 <= len(children) <= 5:  # 通常导航栏有3-5个按钮
                    results.extend(children)
        
        return results
    
    def _create_selector_for_element(self, element: Dict) -> Dict:
        """为元素创建选择器"""
        selector = {}
        
        # 尝试不同的选择器策略
        if element.get("viewIdResourceName"):
            selector["id"] = element["viewIdResourceName"]
        
        if element.get("text"):
            selector["text"] = element["text"]
        
        if element.get("contentDescription"):
            selector["desc"] = element["contentDescription"]
        
        if element.get("className"):
            selector["class"] = element["className"]
        
        return selector
    
    def _identify_screen_type(self, device_state) -> Optional[str]:
        """识别当前屏幕类型"""
        # 获取当前包名和活动名称
        # 处理device_state可能是字符串的情况
        print(f"AppLearner-->_identify_screen_type--->{device_state}")
        if isinstance(device_state, str):
            try:
                # 尝试解析JSON字符串
                device_state_dict = json.loads(device_state)
                package_name = device_state_dict.get('current_package')
                activity = device_state_dict.get('current_activity')
                ui_hierarchy = device_state_dict.get('ui_hierarchy', {})
            except json.JSONDecodeError:
                print(f"无法解析device_state JSON: {device_state}")
                return None
            except Exception as e:
                print(f"处理device_state时出错: {e}")
                return None
        else:
            # 如果是对象，则直接获取属性
            package_name = device_state.current_package if device_state else None
            activity = device_state.current_activity if device_state else None
            ui_hierarchy = device_state.ui_hierarchy if device_state else {}

        if not package_name:
            return None
        
        if not package_name:
            return None
        
        # 查找标题元素
        title_elements = self._find_elements_by_pattern(ui_hierarchy, ["标题", "title"])
        title_text = title_elements[0].get("text", "") if title_elements else ""
        
        # 根据UI特征识别屏幕类型
        if title_text:
            return f"{title_text}_screen"
        elif "搜索" in str(ui_hierarchy):
            return "search_screen"
        elif "播放" in str(ui_hierarchy) or "play" in str(ui_hierarchy).lower():
            return "player_screen"
        elif "设置" in str(ui_hierarchy) or "settings" in str(ui_hierarchy).lower():
            return "settings_screen"
        elif "列表" in str(ui_hierarchy) or "list" in str(ui_hierarchy).lower():
            return "list_screen"
        elif activity:
            # 使用活动名称作为回退
            return activity.split(".")[-1]
        
        return "main_screen"  # 默认屏幕类型
    
    def _learn_common_operations(self, session_id: str, server):
        """学习应用中的常见操作"""
        if session_id not in self.learning_sessions:
            return
        
        session = self.learning_sessions[session_id]
        package_name = session["current_app"].get("packageName")
        
        # 获取当前应用知识
        app_knowledge = self.app_knowledge.get(package_name, {})
        elements = app_knowledge.get("elements", {})
        
        # 定义要学习的常见操作
        common_operations = []
        
        # 1. 搜索操作
        search_elements = [e for e in elements.values() if e.get("type") == "search"]
        if search_elements:
            search_element = search_elements[0]
            common_operations.append({
                "name": "search",
                "steps": [
                    {"action": MCPActionTypes.CLICK, "selector": search_element["selector"]},
                    {"action": MCPActionTypes.TYPE_TEXT, "selector": {"type": "input"}, "text": "{query}"}
                ]
            })
        
        # 2. 播放操作(针对音乐或视频应用)
        if any(kw in package_name for kw in ["music", "video", "player", "tv"]):
            common_operations.append({
                "name": "play_content",
                "steps": [
                    {"action": MCPActionTypes.FIND_ELEMENT, "selector": {"text": "{content}"}},
                    {"action": MCPActionTypes.CLICK, "selector": {"text": "{content}"}}
                ]
            })
        
        # 3. 返回操作
        common_operations.append({
            "name": "go_back",
            "steps": [
                {"action": MCPActionTypes.PRESS_BACK}
            ]
        })
        
        # 保存学习到的操作
        actions = app_knowledge.get("actions", {})
        for operation in common_operations:
            actions[operation["name"]] = {
                "steps": operation["steps"],
                "lastUsed": time.time()
            }
        
        app_knowledge["actions"] = actions
        app_knowledge["lastLearned"] = time.time()
        
        self.app_knowledge[package_name] = app_knowledge
        
        # 更新学习状态
        session["current_task"] = "common_operations"
        
        # 继续下一步
        self._schedule_next_learning_step(session_id, server)
    
    def _return_to_home(self, session_id: str, server):
        """返回主屏幕"""
        if session_id not in self.learning_sessions:
            return
        
        session = self.learning_sessions[session_id]
        device_id = session["device_id"]
        
        # 获取设备连接
        with server.devices_lock:
            if device_id not in server.devices:
                logger.error(f"Device not found: {device_id}")
                return
            
            device = server.devices[device_id]
        
        # 创建返回主屏幕的请求
        request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.PRESS_HOME,
            context=Context(session_id=session_id)
        )
        
        # 发送请求并设置回调
        device.send_request(request, lambda response: self._on_returned_home(
            response, session_id, server))
    
    def _on_returned_home(self, response: Response, session_id: str, server):
        """返回主屏幕后回调"""
        if session_id not in self.learning_sessions:
            return
        
        session = self.learning_sessions[session_id]
        
        # 短暂延迟
        time.sleep(0.5)
        
        # 更新学习状态
        session["current_task"] = None
        
        # 继续下一步(学习下一个应用)
        self._schedule_next_learning_step(session_id, server)
    
    def get_app_info(self, package_name: str) -> Optional[Dict]:
        """获取应用信息"""
        return self.app_knowledge.get(package_name)
    
    def find_app_by_name(self, app_name: str) -> Optional[str]:
        """通过名称查找应用包名"""
        app_name_lower = app_name.lower()
        
        # 常见应用名称映射
        common_apps = {
            "微信": "com.tencent.mm",
            "qq": "com.tencent.mobileqq",
            "qq音乐": "com.tencent.qqmusic",
            "网易云音乐": "com.netease.cloudmusic",
            "网易云": "com.netease.cloudmusic",
            "云音乐": "com.netease.cloudmusic",
            "哔哩哔哩": "tv.danmaku.bili",
            "b站": "tv.danmaku.bili",
            "bili": "tv.danmaku.bili",
            "bilibili": "tv.danmaku.bili",
            "抖音": "com.ss.android.ugc.aweme",
            "设置": "com.android.settings",
            "短信": "com.android.mms",
            "信息": "com.android.mms",
            "电话": "com.android.dialer",
            "联系人": "com.android.contacts",
        }
        
        # 先检查常见应用映射
        if app_name_lower in common_apps:
            return common_apps[app_name_lower]
        
        # 然后搜索已知应用
        for package_name, app_info in self.app_knowledge.items():
            app_info_name = app_info.get("appName", "").lower()
            if app_name_lower in app_info_name or app_info_name in app_name_lower:
                return package_name
        
        return None

    def get_app_knowledge(self, package_name: str) -> Optional[Dict]:
        """获取应用知识，作为 get_app_info 的别名"""
        return self.get_app_info(package_name)

    def get_operation_steps(self, package_name: str, operation_name: str, 
                         parameters: Dict = None) -> Optional[List[Dict]]:
        """获取操作步骤"""
        app_info = self.app_knowledge.get(package_name)
        if not app_info:
            return None
        
        actions = app_info.get("actions", {})
        operation = actions.get(operation_name)
        if not operation:
            return None
        
        steps = operation.get("steps", [])
        
        # 如果有参数，替换步骤中的占位符
        if parameters and steps:
            updated_steps = []
            for step in steps:
                updated_step = dict(step)  # 创建副本
                
                # 替换文本中的占位符
                if "text" in updated_step:
                    text = updated_step["text"]
                    for key, value in parameters.items():
                        placeholder = "{" + key + "}"
                        if placeholder in text:
                            text = text.replace(placeholder, str(value))
                    updated_step["text"] = text
                
                # 替换选择器中的占位符
                if "selector" in updated_step and isinstance(updated_step["selector"], dict):
                    selector = dict(updated_step["selector"])
                    for selector_key, selector_value in selector.items():
                        if isinstance(selector_value, str):
                            for key, value in parameters.items():
                                placeholder = "{" + key + "}"
                                if placeholder in selector_value:
                                    selector[selector_key] = selector_value.replace(
                                        placeholder, str(value))
                    updated_step["selector"] = selector
                
                updated_steps.append(updated_step)
            
            steps = updated_steps
        
        # 更新最后使用时间
        operation["lastUsed"] = time.time()
        
        return steps