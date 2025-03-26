"""
应用深度探索模块

在app_learner基础上提供更深入的应用UI探索和元素检测功能
支持等待应用完全加载并检测更多类型的UI元素
"""
import logging
import time
import uuid
from typing import Dict, List, Optional

from mcp.mcp_protocol import (
    Request, Response, Context, MCPActionTypes, DeviceState
)

# 配置日志
logger = logging.getLogger("AppExplorer")


class AppExplorer:
    """应用深度探索类"""

    def __init__(self, app_learner):
        """初始化应用探索器
        
        Args:
            app_learner: AppLearner实例，用于共享应用知识库
        """
        self.app_learner = app_learner
        self.exploration_sessions = {}
        self.visited_screens = {}  # 记录已访问的屏幕
        self.element_types = {
            "text": ["android.widget.TextView"],
            "button": ["android.widget.Button", "android.widget.ImageButton"],
            "image": ["android.widget.ImageView"],
            "input": ["android.widget.EditText"],
            "password": ["android.widget.EditText"],  # 通过属性区分
            "list": ["android.widget.ListView", "android.widget.RecyclerView"],
            "scroll": ["android.widget.ScrollView", "android.widget.HorizontalScrollView"],
            "checkbox": ["android.widget.CheckBox"],
            "radio": ["android.widget.RadioButton"],
            "switch": ["android.widget.Switch", "android.widget.ToggleButton"],
            "spinner": ["android.widget.Spinner"],
            "seekbar": ["android.widget.SeekBar"],
            "webview": ["android.webkit.WebView"],
            "tab": ["android.widget.TabWidget", "com.google.android.material.tabs.TabLayout"],
            "drawer": ["androidx.drawerlayout.widget.DrawerLayout"],
            "navigation": ["com.google.android.material.navigation.NavigationView",
                           "com.google.android.material.bottomnavigation.BottomNavigationView"]
        }
        self.MAX_EXPLORE_DEPTH = 5  # 最大探索深度
        self.MAX_EXPLORE_SCREENS = 15  # 最大探索屏幕数
        self.WAIT_TIMEOUT = 10  # 最大等待时间（秒）

    def start_app_exploration(self, device_id: str, package_name: str, server) -> str:
        """开始一次应用深度探索会话
        
        Args:
            device_id: 设备ID
            package_name: 应用包名
            server: 服务器实例
            
        Returns:
            session_id: 会话ID
        """
        # 创建探索会话
        session_id = str(uuid.uuid4())

        # 获取应用信息
        app_info = self.app_learner.get_app_info(package_name)
        app_name = app_info.get("appName", package_name) if app_info else package_name

        logger.info(f"开始深度探索应用: {app_name} ({package_name})")

        self.exploration_sessions[session_id] = {
            "device_id": device_id,
            "package_name": package_name,
            "app_name": app_name,
            "status": "starting",
            "current_screen": None,
            "discovered_elements": {},
            "discovered_screens": {},
            "exploration_queue": [],  # 待探索队列
            "visited_paths": set(),  # 已访问路径
            "current_depth": 0,
            "start_time": time.time(),
            "waits": 0  # 等待次数计数
        }

        # 重置此应用的访问记录
        self.visited_screens[package_name] = set()

        # 开始探索流程
        self._launch_app(session_id, server)

        return session_id

    def _launch_app(self, session_id: str, server):
        """启动应用"""
        session = self.exploration_sessions[session_id]
        device_id = session["device_id"]
        package_name = session["package_name"]

        logger.info(f"正在启动应用: {package_name}")

        # 获取设备连接
        with server.devices_lock:
            if device_id not in server.devices:
                logger.error(f"设备未找到: {device_id}")
                self._end_exploration(session_id, "设备未找到")
                return

            device = server.devices[device_id]

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

        session["status"] = "launching"

    def _on_app_launched(self, response: Response, session_id: str, server):
        """应用启动后回调"""
        if session_id not in self.exploration_sessions:
            logger.error(f"会话 {session_id} 不存在")
            return

        session = self.exploration_sessions[session_id]

        if response.status != "success":
            logger.error(f"启动应用失败: {response.error}")
            self._end_exploration(session_id, f"启动应用失败: {response.error}")
            return

        # 确保日志记录完整
        logger.info(f"应用 {session['package_name']} 启动成功，开始等待应用加载...")

        # 更新会话状态
        session["status"] = "waiting_for_load"

        # 等待应用完全加载
        self._wait_for_app_load(session_id, server)

    def _wait_for_app_load(self, session_id: str, server):
        """等待应用完全加载"""
        if session_id not in self.exploration_sessions:
            return

        session = self.exploration_sessions[session_id]
        device_id = session["device_id"]
        package_name = session["package_name"]
        logger.info(f"等待应用 {package_name} 加载，等待次数: {session['waits']}")
        # 获取设备连接
        with server.devices_lock:
            if device_id not in server.devices:
                logger.error(f"设备未找到: {device_id}")
                self._end_exploration(session_id, "设备未找到")
                return

            device = server.devices[device_id]

        # 检查等待次数是否超过阈值
        if session["waits"] >= 5:  # 最多等待5次
            logger.info("已达到最大等待次数，假定应用已加载完成")
            session["status"] = "ready_to_explore"
            self._start_screen_exploration(session_id, server)
            return

        # 创建获取UI状态的请求
        request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.GET_UI_STATE,
            context=Context(session_id=session_id)
        )

        # 发送请求并设置回调
        device.send_request(request, lambda response: self._check_app_loaded(
            response, session_id, server))

        # 增加等待计数
        session["waits"] += 1

    def _check_app_loaded(self, response: Response, session_id: str, server):
        """检查应用是否已加载完成"""
        if session_id not in self.exploration_sessions:
            return

        session = self.exploration_sessions[session_id]

        if response.status != "success":
            logger.error(f"获取UI状态失败: {response.error}")
            # 继续等待，可能是应用正在启动中
            time.sleep(1)
            self._wait_for_app_load(session_id, server)
            return

        # 获取并解析UI状态
        device_state = self._parse_device_state(response.device_state)

        if not device_state:
            logger.warning("无法获取设备状态，继续等待")
            time.sleep(1)
            self._wait_for_app_load(session_id, server)
            return

        # 检查当前包名是否符合预期
        current_package = device_state.get("current_package")
        expected_package = session["package_name"]

        if current_package != expected_package:
            logger.warning(f"当前包名 {current_package} 与预期包名 {expected_package} 不一致，继续等待")
            time.sleep(1)
            self._wait_for_app_load(session_id, server)
            return

        # 检查UI是否包含元素（简单判断是否加载完成）
        ui_hierarchy = device_state.get("ui_hierarchy", {})
        elements_count = self._count_elements(ui_hierarchy)

        logger.info(f"当前UI元素数量: {elements_count}")

        if elements_count < 5:
            logger.warning("UI元素较少，可能应用尚未完全加载，继续等待")
            time.sleep(1.5)  # 稍微等长一点
            self._wait_for_app_load(session_id, server)
            return

        # 等待一小段时间，确保应用完全加载
        logger.info("应用已加载完成，开始探索")
        session["status"] = "ready_to_explore"

        # 开始探索当前屏幕
        self._start_screen_exploration(session_id, server)

    def _count_elements(self, node: Dict) -> int:
        """统计UI树中的元素数量"""
        if not node:
            return 0

        count = 1  # 当前节点

        # 递归统计子节点
        for child in node.get("children", []):
            count += self._count_elements(child)

        return count

    def _start_screen_exploration(self, session_id: str, server):
        """开始探索当前屏幕"""
        if session_id not in self.exploration_sessions:
            return

        session = self.exploration_sessions[session_id]
        device_id = session["device_id"]

        # 获取设备连接
        with server.devices_lock:
            if device_id not in server.devices:
                logger.error(f"设备未找到: {device_id}")
                self._end_exploration(session_id, "设备未找到")
                return

            device = server.devices[device_id]

        # 创建获取UI状态的请求
        request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.GET_UI_STATE,
            context=Context(session_id=session_id)
        )

        # 发送请求并设置回调
        device.send_request(request, lambda response: self._analyze_current_screen(
            response, session_id, server))

        session["status"] = "exploring"

    def _analyze_current_screen(self, response: Response, session_id: str, server):
        """分析当前屏幕"""
        if session_id not in self.exploration_sessions:
            return

        session = self.exploration_sessions[session_id]
        package_name = session["package_name"]

        if response.status != "success":
            logger.error(f"获取UI状态失败: {response.error}")
            # 尝试返回并继续探索
            self._go_back_and_continue(session_id, server)
            return

        # 获取并解析UI状态
        device_state = self._parse_device_state(response.device_state)

        if not device_state:
            logger.warning("无法获取设备状态，尝试继续探索")
            self._go_back_and_continue(session_id, server)
            return

        # 检查当前包名是否符合预期
        current_package = device_state.get("current_package")

        if current_package != package_name:
            logger.warning(f"当前包名 {current_package} 与预期包名 {package_name} 不一致，返回上一级")
            self._go_back_and_continue(session_id, server)
            return

        # 识别当前屏幕
        current_activity = device_state.get("current_activity", "")
        ui_hierarchy = device_state.get("ui_hierarchy", {})

        # 生成屏幕标识
        screen_signature = self._generate_screen_signature(ui_hierarchy)
        screen_id = f"{current_activity}_{screen_signature}"

        # 检查是否已访问过此屏幕
        if screen_id in self.visited_screens.get(package_name, set()):
            logger.info(f"已经访问过该屏幕 {screen_id}，准备探索下一个屏幕")
            self._explore_next_element(session_id, server)
            return

        # 标记当前屏幕为已访问
        if package_name not in self.visited_screens:
            self.visited_screens[package_name] = set()
        self.visited_screens[package_name].add(screen_id)

        logger.info(f"正在分析屏幕: {screen_id}")

        # 识别屏幕类型
        screen_type = self._identify_screen_type(device_state)

        # 识别屏幕上的所有元素
        elements = self._identify_all_elements(ui_hierarchy)

        # 存储屏幕信息
        session["current_screen"] = {
            "id": screen_id,
            "type": screen_type,
            "activity": current_activity,
            "elements": elements
        }

        # 更新应用知识库中的屏幕信息
        app_knowledge = self.app_learner.app_knowledge.get(package_name, {})
        screens = app_knowledge.get("screens", {})

        screens[screen_id] = {
            "type": screen_type,
            "activity": current_activity,
            "elements": [elem_id for elem_id in elements.keys()],
            "lastSeen": time.time()
        }

        # 更新应用知识库中的元素信息
        app_elements = app_knowledge.get("elements", {})
        for elem_id, elem_info in elements.items():
            app_elements[elem_id] = elem_info

        # 保存到应用知识库
        app_knowledge["screens"] = screens
        app_knowledge["elements"] = app_elements
        app_knowledge["lastExplored"] = time.time()
        self.app_learner.app_knowledge[package_name] = app_knowledge

        # 更新本次会话的发现信息
        session["discovered_screens"][screen_id] = {
            "type": screen_type,
            "activity": current_activity
        }
        session["discovered_elements"].update(elements)

        # 将可点击元素添加到探索队列
        clickable_elements = self._find_clickable_elements(elements)
        for elem_id, elem_info in clickable_elements.items():
            path = (screen_id, elem_id)
            if path not in session["visited_paths"] and len(session["exploration_queue"]) < self.MAX_EXPLORE_SCREENS:
                session["exploration_queue"].append({
                    "screen_id": screen_id,
                    "element_id": elem_id,
                    "depth": session["current_depth"] + 1
                })

        # 继续探索
        self._explore_next_element(session_id, server)

    def _generate_screen_signature(self, ui_hierarchy: Dict) -> str:
        """生成屏幕标识（基于UI结构的哈希）"""
        if not ui_hierarchy:
            return "empty"

        # 提取屏幕上的主要文本元素作为标识
        texts = []

        def extract_texts(node, depth=0, max_depth=3):
            if depth > max_depth:
                return

            # 提取文本
            text = node.get("text", "")
            if text and len(text) > 1:
                texts.append(text)

            # 处理子节点
            for child in node.get("children", [])[:5]:  # 只处理前5个子节点，避免标识过于复杂
                extract_texts(child, depth + 1, max_depth)

        extract_texts(ui_hierarchy)

        # 如果没有提取到文本，使用元素类名
        if not texts:
            def extract_class_names(node, depth=0, max_depth=2):
                if depth > max_depth:
                    return

                # 提取类名
                class_name = node.get("className", "")
                if class_name:
                    texts.append(class_name.split(".")[-1])

                # 处理子节点
                for child in node.get("children", [])[:3]:
                    extract_class_names(child, depth + 1, max_depth)

            extract_class_names(ui_hierarchy)

        # 生成简短标识
        if texts:
            text_sig = "_".join(texts[:3])  # 只使用前3个文本
            # 限制长度并移除特殊字符
            text_sig = "".join(c for c in text_sig if c.isalnum() or c == "_")
            if len(text_sig) > 30:
                text_sig = text_sig[:30]
            return text_sig
        else:
            # 无法生成有意义的标识，使用随机字符串
            return f"screen_{time.time() % 10000:.0f}"

    def _identify_all_elements(self, ui_hierarchy: Dict) -> Dict[str, Dict]:
        """识别屏幕上的所有元素

        Returns:
            Dict[str, Dict]: 元素ID到元素信息的映射
        """
        elements = {}

        def traverse_node(node, parent_path="", index=0, parent=None):
            # 生成元素ID
            node_id = f"{parent_path}/{index}" if parent_path else f"{index}"

            # 设置父节点信息（用于选择器）
            if parent:
                node["parent"] = {"className": parent.get("className", "")}

            # 设置索引信息（用于选择器）
            node["index"] = index

            # 获取元素基本信息
            class_name = node.get("className", "")
            text = node.get("text", "")
            content_desc = node.get("contentDescription", "")
            resource_id = node.get("viewIdResourceName", "")

            # 确定元素类型
            element_type = "unknown"
            for type_name, class_list in self.element_types.items():
                if any(cls in class_name for cls in class_list):
                    element_type = type_name
                    break

            # 特殊处理密码输入框
            if element_type == "input" and node.get("isPassword", False):
                element_type = "password"

            # 检查是否可点击
            clickable = node.get("clickable", False)

            # 验证边界框是否有效
            bounds = node.get("bounds", {})
            if bounds:
                if not (bounds.get("right", 0) > bounds.get("left", 0) and
                        bounds.get("bottom", 0) > bounds.get("top", 0)):
                    # 如果边界框无效，尝试修复或设置默认值
                    logger.warning(f"发现无效边界框: {bounds}")

                    # 设置一个小的默认边界框，避免高度或宽度为0
                    if bounds.get("right", 0) <= bounds.get("left", 0):
                        bounds["right"] = bounds.get("left", 0) + 10
                    if bounds.get("bottom", 0) <= bounds.get("top", 0):
                        bounds["bottom"] = bounds.get("top", 0) + 10

            # 如果元素有文本、描述、资源ID或可点击，则记录该元素
            if text or content_desc or resource_id or clickable:
                element_id = f"element_{node_id}"
                elements[element_id] = {
                    "type": element_type,
                    "className": class_name,
                    "text": text,
                    "contentDescription": content_desc,
                    "resourceId": resource_id,
                    "bounds": bounds,
                    "clickable": clickable,
                    "longClickable": node.get("longClickable", False),
                    "checkable": node.get("checkable", False),
                    "checked": node.get("checked", False),
                    "selected": node.get("selected", False),
                    "enabled": node.get("enabled", True),
                    "focusable": node.get("focusable", False),
                    "focused": node.get("focused", False),
                    "scrollable": node.get("scrollable", False),
                    "selector": self._create_selector_for_element(node)
                }

            # 递归处理子节点
            for i, child in enumerate(node.get("children", [])):
                traverse_node(child, node_id, i, node)

        traverse_node(ui_hierarchy)
        return elements

    def _find_clickable_elements(self, elements: Dict[str, Dict]) -> Dict[str, Dict]:
        """查找可点击的元素"""
        clickable_elements = {}

        for elem_id, elem_info in elements.items():
            # 直接标记为可点击的元素
            if elem_info.get("clickable", False):
                clickable_elements[elem_id] = elem_info
                continue

            # 特定类型的元素通常是可点击的
            clickable_types = ["button", "checkbox", "radio", "switch", "spinner", "tab"]
            if elem_info.get("type") in clickable_types:
                clickable_elements[elem_id] = elem_info
                continue

            # 列表项通常是可点击的
            if "item" in elem_info.get("className", "").lower():
                clickable_elements[elem_id] = elem_info
                continue

            # 有些文本元素也是可点击的（如链接）
            if elem_info.get("type") == "text" and (
                    "登录" in elem_info.get("text", "") or
                    "注册" in elem_info.get("text", "") or
                    "link" in elem_info.get("className", "").lower()
            ):
                clickable_elements[elem_id] = elem_info

        return clickable_elements

    def _explore_next_element(self, session_id: str, server):
        """探索下一个元素"""
        if session_id not in self.exploration_sessions:
            return

        session = self.exploration_sessions[session_id]

        # 检查是否已达到探索上限
        if len(session["discovered_screens"]) >= self.MAX_EXPLORE_SCREENS:
            logger.info(f"已达到最大探索屏幕数 {self.MAX_EXPLORE_SCREENS}，结束探索")
            self._end_exploration(session_id, "已完成最大探索量")
            return

        # 检查探索队列是否为空
        if not session["exploration_queue"]:
            logger.info("探索队列为空，探索完成")
            self._end_exploration(session_id, "探索完成")
            return

        # 取出下一个要探索的元素
        next_item = session["exploration_queue"].pop(0)
        screen_id = next_item["screen_id"]
        element_id = next_item["element_id"]
        depth = next_item["depth"]

        # 检查深度是否超过限制
        if depth > self.MAX_EXPLORE_DEPTH:
            logger.info(f"已达到最大探索深度 {self.MAX_EXPLORE_DEPTH}，跳过此元素")
            self._explore_next_element(session_id, server)
            return

        # 检查路径是否已被访问
        path = (screen_id, element_id)
        if path in session["visited_paths"]:
            logger.info(f"路径 {path} 已被访问，跳过")
            self._explore_next_element(session_id, server)
            return

        # 标记路径为已访问
        session["visited_paths"].add(path)

        # 更新当前深度
        session["current_depth"] = depth

        # 尝试点击元素
        self._click_element(session_id, element_id, server)

    def _click_element(self, session_id: str, element_id: str, server):
        """点击元素"""
        if session_id not in self.exploration_sessions:
            return

        session = self.exploration_sessions[session_id]
        device_id = session["device_id"]

        # 获取元素信息
        element_info = session["discovered_elements"].get(element_id)
        if not element_info:
            logger.warning(f"元素 {element_id} 未找到，跳过")
            self._explore_next_element(session_id, server)
            return

        # 详细日志记录元素信息，便于调试
        logger.info(f"尝试点击元素: {element_info.get('text', '')} ({element_id})")
        logger.info(f"元素类型: {element_info.get('type')}, 类名: {element_info.get('className')}")
        logger.info(f"元素边界框: {element_info.get('bounds')}")
        logger.info(f"使用选择器: {element_info.get('selector', {})}")

        # 获取设备连接
        with server.devices_lock:
            if device_id not in server.devices:
                logger.error(f"设备未找到: {device_id}")
                self._end_exploration(session_id, "设备未找到")
                return

            device = server.devices[device_id]

        # 创建点击请求
        selector = element_info.get("selector", {})
        if not selector:
            logger.warning(f"元素 {element_id} 没有有效的选择器，跳过")
            self._explore_next_element(session_id, server)
            return

        # 优先使用resourceId或text作为选择器，这些通常更可靠
        improved_selector = {}
        if "resourceId" in selector and selector["resourceId"]:
            improved_selector["resourceId"] = selector["resourceId"]
        elif "text" in selector and selector["text"]:
            improved_selector["text"] = selector["text"]
        elif "contentDescription" in selector and selector["contentDescription"]:
            improved_selector["contentDescription"] = selector["contentDescription"]
        else:
            # 使用原始选择器，但确保边界框是有效的
            improved_selector = selector

            # 如果有边界框，确保它是有效的
            if "bounds" in improved_selector:
                bounds = improved_selector["bounds"]
                if not (bounds.get("right", 0) > bounds.get("left", 0) and
                        bounds.get("bottom", 0) > bounds.get("top", 0)):
                    # 移除无效的边界框
                    logger.warning(f"移除无效边界框: {bounds}")
                    improved_selector.pop("bounds", None)

        logger.info(f"改进后的选择器: {improved_selector}")

        request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.CLICK,
            parameters={"selector": improved_selector},
            context=Context(session_id=session_id)
        )

        # 发送请求并设置回调
        device.send_request(request, lambda response: self._on_element_clicked(
            response, session_id, server))

    def _on_element_clicked(self, response: Response, session_id: str, server):
        """元素点击后回调"""
        if session_id not in self.exploration_sessions:
            return

        session = self.exploration_sessions[session_id]

        if response.status != "success":
            logger.warning(f"点击元素失败: {response.error}")
            # 失败也继续探索下一个元素
            self._explore_next_element(session_id, server)
            return

        # 等待一小段时间，让UI响应
        time.sleep(1.5)

        # 分析点击后的屏幕
        self._start_screen_exploration(session_id, server)

    def _go_back_and_continue(self, session_id: str, server):
        """返回上一级并继续探索"""
        if session_id not in self.exploration_sessions:
            return

        session = self.exploration_sessions[session_id]
        device_id = session["device_id"]

        # 获取设备连接
        with server.devices_lock:
            if device_id not in server.devices:
                logger.error(f"设备未找到: {device_id}")
                self._end_exploration(session_id, "设备未找到")
                return

            device = server.devices[device_id]

        # 创建返回请求
        request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.PRESS_BACK,
            context=Context(session_id=session_id)
        )

        # 发送请求并设置回调
        device.send_request(request, lambda response: self._on_back_pressed(
            response, session_id, server))

    def _on_back_pressed(self, response: Response, session_id: str, server):
        """返回键按下后回调"""
        if session_id not in self.exploration_sessions:
            return

        # 等待一小段时间
        time.sleep(1)

        # 继续探索下一个元素
        self._explore_next_element(session_id, server)

    def _end_exploration(self, session_id: str, reason: str = ""):
        """结束探索会话"""
        if session_id not in self.exploration_sessions:
            return

        session = self.exploration_sessions[session_id]
        package_name = session["package_name"]

        # 记录探索结果
        elapsed_time = time.time() - session["start_time"]
        screens_count = len(session["discovered_screens"])
        elements_count = len(session["discovered_elements"])

        logger.info(f"结束应用探索 - 原因: {reason}")
        logger.info(f"探索统计: 耗时 {elapsed_time:.1f}秒, 发现 {screens_count} 个屏幕, {elements_count} 个元素")

        # 保存应用知识
        self.app_learner._save_app_knowledge()

        # 学习应用操作
        if "discovered_elements" in session and "discovered_screens" in session:
            self._learn_app_operations(
                package_name,
                session["discovered_elements"],
                session["discovered_screens"]
            )

        # 调用完成回调（如果存在）
        if "on_completed" in session and callable(session["on_completed"]):
            try:
                session["on_completed"]()
            except Exception as e:
                logger.error(f"调用探索完成回调时出错: {e}")

        # 移除会话
        self.exploration_sessions.pop(session_id, None)

    def _identify_screen_type(self, device_state: Dict) -> str:
        """识别屏幕类型"""
        # 获取当前包名和活动名称
        current_package = device_state.get("current_package", "")
        current_activity = device_state.get("current_activity", "")
        ui_hierarchy = device_state.get("ui_hierarchy", {})

        # 提取UI中的文本内容
        screen_text = self._extract_screen_text(ui_hierarchy)

        # 分析屏幕特征
        if "登录" in screen_text or "login" in screen_text.lower():
            return "login_screen"
        elif "注册" in screen_text or "register" in screen_text.lower() or "sign up" in screen_text.lower():
            return "register_screen"
        elif "设置" in screen_text or "setting" in screen_text.lower():
            return "settings_screen"
        elif "搜索" in screen_text or "search" in screen_text.lower():
            return "search_screen"
        elif "详情" in screen_text or "detail" in screen_text.lower() or "info" in screen_text.lower():
            return "detail_screen"
        elif "列表" in screen_text or "list" in screen_text.lower():
            return "list_screen"
        elif "播放" in screen_text or "play" in screen_text.lower():
            return "player_screen"
        elif "消息" in screen_text or "message" in screen_text.lower() or "聊天" in screen_text:
            return "message_screen"
        elif "个人" in screen_text or "我的" in screen_text or "profile" in screen_text.lower() or "my" in screen_text.lower():
            return "profile_screen"
        elif "首页" in screen_text or "home" in screen_text.lower() or "main" in screen_text.lower():
            return "main_screen"

        # 根据活动名称推断
        if current_activity:
            activity_name = current_activity.split(".")[-1].lower()
            if "main" in activity_name:
                return "main_screen"
            elif "login" in activity_name:
                return "login_screen"
            elif "setting" in activity_name:
                return "settings_screen"
            elif "detail" in activity_name:
                return "detail_screen"
            elif "list" in activity_name:
                return "list_screen"
            elif "search" in activity_name:
                return "search_screen"
            elif "player" in activity_name or "play" in activity_name:
                return "player_screen"
            else:
                return f"{activity_name}_screen"

        # 默认类型
        return "unknown_screen"

    def _parse_device_state(self, device_state: 'DeviceState') -> Dict:
        """解析设备状态信息

        Args:
            device_state: DeviceState 类型的设备状态对象

        Returns:
            解析后的设备状态信息
        """
        if not device_state:
            logger.warning("接收到空的设备状态")
            return {}

        try:
            # 假设 DeviceState 有以下属性
            parsed_state = {
                "current_package": device_state.current_package or "",
                "current_activity": device_state.current_activity or "",
                "ui_hierarchy": device_state.ui_hierarchy or {}
            }

            # 额外的安全检查
            if not parsed_state["current_package"]:
                logger.warning("未能获取当前包名")

            if not parsed_state["ui_hierarchy"]:
                logger.warning("UI层级为空")

            return parsed_state
        except Exception as e:
            logger.error(f"解析设备状态时发生错误: {e}")
            return {}

    def _create_selector_for_element(self, node: Dict) -> Dict:
        """为元素创建选择器

        Args:
            node: UI节点信息

        Returns:
            可用于定位元素的选择器字典
        """
        selector = {}

        # 1. 优先使用资源ID（最可靠的标识符）
        resource_id = node.get("viewIdResourceName", "")
        if resource_id:
            selector["resourceId"] = resource_id

        # 2. 使用文本内容（第二可靠）
        text = node.get("text", "")
        if text and len(text) > 0:
            selector["text"] = text

        # 3. 使用内容描述（第三可靠）
        content_desc = node.get("contentDescription", "")
        if content_desc and len(content_desc) > 0:
            selector["contentDescription"] = content_desc

        # 4. 使用类名
        class_name = node.get("className", "")
        if class_name:
            selector["className"] = class_name

        # 5. 验证边界框并添加
        bounds = node.get("bounds", {})
        if bounds and isinstance(bounds, dict):
            # 确保边界框是有效的（宽高大于0）
            if (bounds.get("right", 0) > bounds.get("left", 0) and
                    bounds.get("bottom", 0) > bounds.get("top", 0)):
                selector["bounds"] = bounds

        # 即使有了其他属性，也确保这些基本属性添加到选择器中
        for key in ["clickable", "enabled", "selected", "focusable", "scrollable"]:
            if key in node:
                selector[key] = node[key]

        # 确保选择器不为空
        if not selector:
            selector["fallback"] = "true"

        return selector

    def _extract_screen_text(self, ui_hierarchy: Dict) -> str:
        """从UI层级中提取所有文本

        Args:
            ui_hierarchy: UI层级字典

        Returns:
            屏幕上的所有文本组成的字符串
        """
        screen_texts = []

        def extract_texts(node):
            # 提取当前节点的文本
            text = node.get("text", "")
            content_desc = node.get("contentDescription", "")

            # 收集文本
            if text:
                screen_texts.append(text)
            if content_desc:
                screen_texts.append(content_desc)

            # 递归处理子节点
            for child in node.get("children", []):
                extract_texts(child)

        # 开始提取
        if ui_hierarchy:
            extract_texts(ui_hierarchy)

        # 合并所有文本
        return " ".join(screen_texts)

    def _store_exploration_results(self, package_name, discovered_screens, discovered_elements):
        """将探索结果保存到应用知识库"""
        app_knowledge = self.app_learner.app_knowledge.get(package_name, {})

        # 合并屏幕信息
        screens = app_knowledge.get("screens", {})
        for screen_id, screen_info in discovered_screens.items():
            screens[screen_id] = screen_info

        # 合并元素信息
        elements = app_knowledge.get("elements", {})
        for elem_id, elem_info in discovered_elements.items():
            elements[elem_id] = elem_info

        # 更新应用知识
        app_knowledge["screens"] = screens
        app_knowledge["elements"] = elements
        app_knowledge["lastExplored"] = time.time()

        # 保存到 app_learner
        self.app_learner.app_knowledge[package_name] = app_knowledge
        self.app_learner._save_app_knowledge()

    def _learn_app_operations(self, package_name, elements, screens):
        """从探索结果中学习应用常见操作"""
        app_knowledge = self.app_learner.app_knowledge.get(package_name, {})
        actions = app_knowledge.get("actions", {})

        # 识别搜索操作
        search_elements = [e for e in elements.values() if e.get("type") in ["search", "input"]]
        if search_elements:
            actions["search"] = {
                "steps": [
                    {"action": "click", "params": {"selector": search_elements[0].get("selector", {})}},
                    {"action": "type_text", "params": {"text": "{query}"}}
                ],
                "lastUsed": time.time()
            }

        # 识别播放操作
        if any(kw in package_name for kw in ["music", "video", "player", "tv"]):
            actions["play_content"] = {
                "steps": [
                    {"action": "find_element", "params": {"selector": {"text": "{content}"}}},
                    {"action": "click", "params": {"selector": {"text": "{content}"}}}
                ],
                "lastUsed": time.time()
            }

        # 更新应用知识
        app_knowledge["actions"] = actions
        self.app_learner.app_knowledge[package_name] = app_knowledge

    def learn_app_deeply(self, device_id, package_name, server):
        """深度学习特定应用 - 提供给外部模块调用的接口"""
        logger.info(f"开始深度学习应用: {package_name}")
        session_id = self.start_app_exploration(device_id, package_name, server)

        return {
            "status": "started",
            "session_id": session_id,
            "message": f"开始深度学习应用: {package_name}"
        }

    def _filter_interesting_apps(self, apps: List[Dict]) -> List[Dict]:
        """过滤出感兴趣的应用"""
        # 常见的应用包名前缀
        interesting_prefixes = [
            "com.android.",  # Android系统应用
            "com.google.android.",  # Google应用
            "com.tencent.",  # 腾讯应用(微信、QQ等)
            "com.netease.",  # 网易应用(云音乐等)
            "com.baidu.",  # 百度应用
            "com.alibaba.",  # 阿里巴巴应用
            "com.sina.",  # 新浪应用
            "com.xiaomi.",  # 小米应用
            "com.huawei.",  # 华为应用
            "tv.danmaku.bili",  # 哔哩哔哩
            "com.smile.gifmaker",  # 快手
            "com.ss.android.ugc.aweme",  # 抖音
        ]

        # 优先级应用(音乐、视频、社交等)
        priority_apps = [
            "com.tencent.mm",  # 微信
            "com.tencent.mobileqq",  # QQ
            "com.netease.cloudmusic",  # 网易云音乐
            "com.tencent.qqmusic",  # QQ音乐
            "com.kugou.android",  # 酷狗音乐
            "com.ss.android.ugc.aweme",  # 抖音
            "tv.danmaku.bili",  # 哔哩哔哩
            "com.baidu.searchbox",  # 百度
            "com.sina.weibo",  # 微博
            "com.android.settings",  # 设置
            "com.android.contacts",  # 联系人
            "com.android.mms",  # 短信
            "com.android.dialer",  # 电话
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
        if len(filtered_apps) > 3:
            filtered_apps = filtered_apps[:3]

        return filtered_apps
