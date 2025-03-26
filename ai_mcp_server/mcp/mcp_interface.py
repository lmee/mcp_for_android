import json
import logging
import re
import socket
import threading
import time
import uuid
from typing import Dict, List, Any, Optional

from mcp.mcp_protocol import (
    Request, Response, Context, DeviceState,
    MCPActionTypes, SessionContext
)

# 导入自学习模块
from app_learn.app_learner import AppLearner

# 配置详细日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DeviceConnection:
    def __init__(self, device_id: str, capabilities: List[str] = None):
        self.device_id = device_id
        self.capabilities = capabilities or []
        self.last_seen = time.time()
        self.connected = True
        self.socket = None
        self.pending_requests = {}

    def send_request(self, request: Request, callback=None):
        """发送请求到设备并设置回调"""
        if not self.connected or not self.socket:
            logger.error(f"设备 {self.device_id} 未连接")
            if callback:
                # 如果有回调，创建一个失败的响应
                error_response = Response(
                    request_id=request.request_id,
                    status="error",
                    error="Device not connected"
                )
                callback(error_response)
            return

        try:
            # 构造完整的请求消息
            request_message = {
                "type": "request",
                "requestId": request.request_id,
                "actionType": request.action_type,
                "parameters": request.parameters,
                "timestamp": time.time()
            }

            # 如果有上下文，添加会话ID
            if request.context and request.context.session_id:
                request_message["sessionId"] = request.context.session_id

            # 序列化消息
            message_str = json.dumps(request_message) + '\n'
            message_bytes = message_str.encode('utf-8')

            # 如果消息很大，考虑分块发送
            if len(message_bytes) > 1024 * 1024:  # 超过1MB
                logger.info(f"发送大型消息 ({len(message_bytes) / 1024:.2f} KB)")

            # 发送消息
            self.socket.sendall(message_bytes)

            # 如果提供了回调，存储在挂起请求中
            if callback:
                self.pending_requests[request.request_id] = {
                    "request": request,
                    "callback": callback
                }

                # 设置超时机制
                def timeout_handler():
                    time.sleep(60)  # 增加到60秒超时
                    if request.request_id in self.pending_requests:
                        # 移除挂起的请求
                        request_info = self.pending_requests.pop(request.request_id, None)
                        if request_info and request_info["callback"]:
                            # 创建超时响应
                            timeout_response = Response(
                                request_id=request.request_id,
                                status="error",
                                error="Request timed out"
                            )
                            request_info["callback"](timeout_response)

                # 启动超时线程
                timeout_thread = threading.Thread(target=timeout_handler)
                timeout_thread.daemon = True
                timeout_thread.start()

            logger.info(f"向设备 {self.device_id} 发送请求: {request.action_type}")

        except Exception as e:
            logger.error(f"发送请求时出错: {e}")

            # 如果有回调，创建一个失败的响应
            if callback:
                error_response = Response(
                    request_id=request.request_id,
                    status="error",
                    error=str(e)
                )
                callback(error_response)


# 模型上下文协议（MCP）实现
class MCPContext:
    def __init__(self, app_learner=None):
        self.mcp_server = None
        self.device_capabilities = {}  # 设备能力映射
        self.action_history = []  # 历史动作记录
        self.known_patterns = {}  # 已知指令模式
        self.learning_database = {}  # 学习数据库
        self.app_learner = app_learner  # 添加app_learner属性

    def register_device(self, device_id: str, capabilities: List[str]) -> None:
        """注册设备及其能力"""
        self.device_capabilities[device_id] = capabilities
        logger.info(f"设备 {device_id} 已注册，能力: {capabilities}")

    def learn_pattern(self, command_template: str, action_sequence: List[Dict[str, Any]],
                      variable_patterns: Dict[str, str] = None) -> None:
        """
        学习新的指令模式

        Args:
            command_template: 命令模板
            action_sequence: 动作序列
            variable_patterns: 变量提取模式，如 {"app_name": "(?:打开|启动)\\s*([^\\s,，。.]+)"}
        """
        # 提取关键词
        keywords = self._extract_keywords(command_template)
        pattern_id = "_".join(keywords)
        # 添加变量提取规则
        if not variable_patterns:
            # 自动生成变量提取规则
            variable_patterns = self._generate_variable_patterns(command_template)
        self.known_patterns[pattern_id] = {
            "command_template": command_template,
            "keywords": keywords,
            "action_sequence": action_sequence,
            "variable_patterns": variable_patterns
        }

        # 更新学习数据库
        for keyword in keywords:
            if keyword not in self.learning_database:
                self.learning_database[keyword] = []
            if pattern_id not in self.learning_database[keyword]:
                self.learning_database[keyword].append(pattern_id)

        logger.info(f"学习了新模式: {pattern_id}")

    def _generate_variable_patterns(self, command_template: str) -> Dict[str, str]:
        """根据命令模板自动生成变量提取规则"""
        variable_patterns = {}

        # 查找所有变量占位符 {{variable}}
        var_matches = re.findall(r'{{(\w+)}}', command_template)

        for var_name in var_matches:
            # 根据变量名生成合适的提取规则
            if "app" in var_name.lower():
                # 应用相关变量
                variable_patterns[var_name] = r'(?:打开|启动|运行)\s*([^\s,，。.]+)'
            elif "search" in var_name.lower() or "term" in var_name.lower():
                # 搜索相关变量
                variable_patterns[var_name] = r'(?:搜索|查找|听|播放)\s*([^\s,，。.]+)'
            else:
                # 默认变量提取规则
                variable_patterns[var_name] = r'(\w+)'

        return variable_patterns

    def learn_app(self, device_id: str, package_name: str = None):
        """学习特定应用或所有应用"""
        if package_name:
            logger.info(f"开始学习特定应用: {package_name}")
            return self._learn_specific_app(device_id, package_name)
        else:
            logger.info(f"开始学习设备上的所有应用")
            return self.app_learner.start_app_learning(device_id, self)

    def _learn_specific_app(self, device_id: str, package_name: str):
        """学习特定应用"""
        # 创建临时会话
        session_id = str(uuid.uuid4())

        # 创建启动应用的请求
        request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.LAUNCH_APP,
            parameters={"packageName": package_name},
            context=Context(session_id=session_id)
        )

        # TODO: 发送请求给设备并处理响应
        # 简化实现，实际需要向设备发送请求并等待响应

        return session_id

    def _extract_keywords(self, text: str) -> List[str]:
        """改进的关键词提取"""
        words = re.findall(r'\b\w+\b', text.lower())
        stopwords = {'的', '了', '来', '在', '和', '是', '让', '通过'}
        return [w for w in words if w not in stopwords and len(w) > 1]

    def find_matching_pattern(self, command: str) -> Optional[Dict[str, Any]]:
        """查找匹配指令的模式"""
        command_keywords = self._extract_keywords(command)

        # 计算每个已知模式的匹配分数
        pattern_scores = {}
        pattern_variables = {}  # 存储每个模式提取的变量

        for pattern_id, pattern_info in self.known_patterns.items():
            pattern_keywords = pattern_info["keywords"]

            # 先尝试提取变量
            variables = self._extract_variables(command, pattern_info.get("variable_patterns", {}))

            # 如果成功提取了变量，这是一个强信号表明这可能是匹配的模式
            if variables:
                # 基础分数 - 为每个成功提取的变量加分
                score = len(variables) * 0.5

                # 额外加上关键词匹配分
                matches = sum(1 for kw in command_keywords if kw in pattern_keywords)
                keyword_score = matches / max(len(command_keywords), 1)
                score += keyword_score * 0.5

                pattern_scores[pattern_id] = score
                pattern_variables[pattern_id] = variables
            else:
                # 如果没有提取出变量，仅依靠关键词匹配
                matches = sum(1 for kw in command_keywords if kw in pattern_keywords)

                # 对于没有变量的模式，需要更高的关键词匹配度
                if matches > 0:
                    score = matches / max(len(command_keywords), 1)
                    if score >= 0.5:  # 至少50%的关键词匹配
                        pattern_scores[pattern_id] = score
                        pattern_variables[pattern_id] = {}

        # 找出最高分数的模式
        if pattern_scores:
            best_pattern_id = max(pattern_scores.items(), key=lambda x: x[1])[0]
            if pattern_scores[best_pattern_id] >= 0.3:  # 降低阈值以提高匹配率
                # 返回模式和提取的变量
                result = dict(self.known_patterns[best_pattern_id])
                result["extracted_variables"] = pattern_variables[best_pattern_id]
                return result

        # 特殊处理：检查是否是"打开+应用名"模式
        if "打开" in command or "启动" in command:
            # 尝试提取应用名称
            app_name_match = re.search(r"(?:打开|启动|运行)\s*([^\s,，。.]+)", command)
            if app_name_match:
                app_name = app_name_match.group(1)
                # 查找打开应用的模式
                for pattern_id, pattern_info in self.known_patterns.items():
                    if "打开" in pattern_info["command_template"] and "app_name" in str(pattern_info):
                        result = dict(pattern_info)
                        result["extracted_variables"] = {"app_name": app_name}
                        return result

        return None

    def _extract_variables(self, command: str, variable_patterns: Dict[str, str]) -> Dict[str, str]:
        """从命令中提取变量值"""
        extracted_variables = {}

        for var_name, pattern in variable_patterns.items():
            match = re.search(pattern, command)
            if match and match.groups():
                extracted_variables[var_name] = match.group(1)

        return extracted_variables

    def execute_command(self, device_id: str, command: str) -> Dict[str, Any]:
        """执行指令并返回响应"""
        if device_id not in self.device_capabilities:
            return {"status": "error", "message": "设备未注册"}

        pattern = self.find_matching_pattern(command)
        if pattern:
            # 提取变量值
            variables = pattern.get("extracted_variables", {})
            # 定制动作序列，替换变量
            actions = self._customize_actions(pattern["action_sequence"], variables)

            # 记录历史
            self.action_history.append({
                "device_id": device_id,
                "command": command,
                "actions": actions
            })

            return {
                "status": "success",
                "actions": actions,
                "message": f"执行动作序列: {pattern['command_template']}"
            }
        else:
            # 尝试使用自学习模块找到匹配的应用和操作
            app_name = self._extract_app_name(command)
            if app_name:
                package_name = self.app_learner.find_app_by_name(app_name)
                if package_name:
                    # 提取操作意图
                    operation, parameters = self._extract_operation_intent(command, app_name)
                    if operation:
                        # 获取操作步骤
                        steps = self.app_learner.get_operation_steps(package_name, operation, parameters)
                        if steps:
                            # 记录历史
                            self.action_history.append({
                                "device_id": device_id,
                                "command": command,
                                "actions": steps
                            })

                            return {
                                "status": "success",
                                "actions": steps,
                                "message": f"执行应用操作: {app_name} - {operation}"
                            }

            return {
                "status": "unknown_command",
                "message": "未找到匹配的指令模式"
            }

    def _extract_app_name(self, command: str) -> Optional[str]:
        """从指令中提取应用名称"""
        # 应用名称关键词匹配模式
        app_patterns = [
            r"(打开|启动|运行|使用)\s*([^的\s]+)(的应用)?",
            r"(在|用|通过)\s*([^的\s]+)(听|看|读|播放|搜索)",
            r"(听|看)([^的\s]+)的(歌|音乐|视频)"
        ]

        for pattern in app_patterns:
            matches = re.search(pattern, command)
            if matches and len(matches.groups()) >= 2:
                return matches.group(2)

        # 常见应用名称直接匹配
        common_apps = ["微信", "QQ", "支付宝", "淘宝", "抖音", "快手", "微博", "百度",
                       "网易云音乐", "QQ音乐", "酷狗", "爱奇艺", "腾讯视频", "哔哩哔哩", "B站",
                       "计算器", "相机", "时钟", "日历", "地图"]

        for app in common_apps:
            if app in command:
                return app

        return None

    def _extract_operation_intent(self, command: str, app_name: str) -> tuple:
        """从指令中提取操作意图和参数"""
        # 移除应用名称，专注于操作部分
        command_without_app = command.replace(app_name, "")

        # 搜索意图
        search_match = re.search(r"(搜索|查找|找)\s*([^\s,.，。]+)", command_without_app)
        if search_match:
            return "search", {"query": search_match.group(2)}

        # 播放意图
        play_match = re.search(r"(播放|听|观看|看)\s*([^\s,.，。]+)", command_without_app)
        if play_match:
            return "play_content", {"content": play_match.group(2)}

        # 返回意图
        if "返回" in command_without_app or "后退" in command_without_app:
            return "go_back", {}

        # 默认为打开应用
        return "open", {}

    def _customize_actions(self, action_template: List[Dict[str, Any]],
                           variables: Dict[str, str]) -> List[Dict[str, Any]]:
        """根据提取的变量定制动作序列

        Args:
            action_template: 动作模板序列
            variables: 已提取的变量字典

        Returns:
            定制化的动作序列
        """
        actions = json.loads(json.dumps(action_template))  # 深拷贝

        # 处理APP名称到包名的转换
        if "app_name" in variables and self.app_learner:
            app_name = variables["app_name"]
            package_name = self.app_learner.find_app_by_name(app_name)
            if package_name:
                variables["app_name"] = package_name

        # 替换动作中的所有变量占位符
        for action in actions:
            if "params" in action:
                for key, value in action["params"].items():
                    if isinstance(value, str):
                        for var_name, var_value in variables.items():
                            placeholder = "{{" + var_name + "}}"
                            if placeholder in value:
                                action["params"][key] = value.replace(placeholder, var_value)

        return actions

    def _build_user_context(self, device_id: str) -> Dict[str, Any]:
        """构建用户上下文信息"""
        # 初始化空上下文
        context = {
            "previous_queries": [],
            "previous_intents": [],
            "recent_apps": [],
            "preferences": {},
            "session_entities": {}  # 当前会话中提到的实体
        }

        # 从历史记录中获取信息
        history = self.action_history

        # 如果有历史记录，提取相关信息
        if history:
            # 获取与当前设备相关的最近5条历史记录
            device_history = [h for h in history if h["device_id"] == device_id][-5:]

            # 提取查询和意图
            for entry in device_history:
                if "command" in entry:
                    context["previous_queries"].append(entry["command"])
                if "intent" in entry:
                    context["previous_intents"].append(entry["intent"])
                if "app" in entry:
                    context["recent_apps"].append(entry["app"])

            # 提取会话实体（如歌手名称、电影名称等）
            for intent in context["previous_intents"]:
                if "entities" in intent:
                    for entity_type, entity_value in intent["entities"].items():
                        if entity_type not in context["session_entities"]:
                            context["session_entities"][entity_type] = []
                        if entity_value not in context["session_entities"][entity_type]:
                            context["session_entities"][entity_type].append(entity_value)

        # 加载用户偏好
        context["preferences"] = self._load_user_preferences(device_id)

        return context

    def _load_user_preferences(self, device_id: str) -> Dict[str, Any]:
        """
            加载用户偏好设置
            
            Args:
                device_id: 设备ID
                
            Returns:
                用户偏好设置字典
            """
        # 初始化默认偏好
        default_preferences = {
            "language": "zh_CN",
            "theme": "default",
            "notification_enabled": True,
            "favorite_apps": [],
            "recent_searches": []
        }

        # 尝试从存储中加载用户偏好
        try:
            # 这里可以实现从文件、数据库或其他存储加载用户偏好
            # 当前实现返回默认偏好

            # 示例：从文件加载
            import os
            import json

            preferences_dir = os.path.join(os.path.dirname(__file__), "..", "data", "preferences")
            os.makedirs(preferences_dir, exist_ok=True)

            preferences_file = os.path.join(preferences_dir, f"{device_id}.json")

            if os.path.exists(preferences_file):
                with open(preferences_file, "r", encoding="utf-8") as f:
                    stored_preferences = json.load(f)
                    # 合并默认偏好和存储的偏好
                    return {**default_preferences, **stored_preferences}

        except Exception as e:
            logger.error(f"加载用户偏好时出错: {e}")

        return default_preferences

    def _get_current_device_state(self, device_id: str):
        """获取设备当前状态"""
        # 如果设备未连接，返回None
        if device_id not in self.device_capabilities:
            return None

        # 创建请求获取当前UI状态
        request_id = str(uuid.uuid4())
        response = None

        # 创建一个事件用于同步
        event = threading.Event()

        def callback(resp):
            nonlocal response
            response = resp
            event.set()

        # 创建获取UI状态的请求
        request = Request(
            request_id=request_id,
            action_type=MCPActionTypes.GET_UI_STATE,
            context=Context()
        )

        # 发送请求
        # 这里需要访问设备连接对象
        with self.mcp_server.devices_lock:
            if device_id in self.mcp_server.devices:
                device = self.mcp_server.devices[device_id]
                device.send_request(request, callback)

        # 等待响应，最多5秒
        event.wait(5)

        # 返回设备状态
        if response and response.device_state:
            return response.device_state
        return None


# 创建服务器类，集成客户端连接和模型交互
class MCPServer:
    def __init__(self, host: str = '0.0.0.0', port: int = 8080, mcp_context: MCPContext = None):
        """初始化服务器"""
        self.host = host
        self.port = port
        self.running = False
        self.server_socket = None

        # 连接的设备管理
        self.devices = {}
        self.devices_lock = threading.Lock()

        # 会话管理
        self.sessions = {}
        self.sessions_lock = threading.Lock()

        # 任务管理
        self.tasks = {}
        self.tasks_lock = threading.Lock()

        # 应用学习器
        self.app_learner = AppLearner()

        # MCP上下文
        self.mcp_context = mcp_context

        # 线程池
        self.threads = []

    def start(self):
        """启动服务器"""
        if self.running:
            logger.warning("服务器已在运行")
            return

        self.running = True

        # 启动TCP监听线程
        tcp_thread = threading.Thread(target=self._start_tcp_server)
        tcp_thread.daemon = True
        tcp_thread.start()
        self.threads.append(tcp_thread)

        logger.info(f"MCP服务器已启动，监听 {self.host}:{self.port}")

    def _start_tcp_server(self):
        """启动TCP服务器以处理设备连接"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 打印具体的绑定信息
            logger.info(f"尝试绑定到 {self.host}:{self.port}")
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)

            logger.info(f"TCP服务器已启动，监听 {self.host}:{self.port}")

            while self.running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    logger.info(f"新连接来自: {addr}")

                    # 启动客户端处理线程
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, addr)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    self.threads.append(client_thread)

                except Exception as e:
                    if self.running:
                        logger.error(f"接受连接时出错: {e}")

        except Exception as e:
            logger.error(f"启动TCP服务器时出错: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None

    def _handle_client(self, client_socket, addr):
        """处理客户端连接"""
        device_id = None  # 初始化设备ID变量
        try:
            # 处理握手
            device_id = self._handle_handshake(client_socket)
            if not device_id:
                logger.warning(f"来自 {addr} 的握手失败")
                client_socket.close()
                return

            logger.info(f"设备连接成功: {device_id} from {addr}")
            # 创建设备连接对象
            device = DeviceConnection(device_id)
            device.socket = client_socket

            # 注册设备
            with self.devices_lock:
                self.devices[device_id] = device

            # 发送欢迎消息
            welcome_msg = {
                "type": "welcome",
                "message": "欢迎连接MCP服务器",
                "device_id": device_id,
                "timestamp": time.time()
            }
            client_socket.sendall((json.dumps(welcome_msg) + '\n').encode('utf-8'))

            # 创建二进制缓冲区
            buffer_bytes = bytearray()

            # 持续处理消息
            while self.running:
                try:
                    # 增加接收缓冲区大小
                    chunk = client_socket.recv(8192)  # 从4096增加到8192
                    if not chunk:
                        logger.info(f"客户端断开连接: {device_id}")
                        break

                    # 将收到的字节追加到缓冲区
                    buffer_bytes.extend(chunk)

                    # 处理包含完整消息的缓冲区（以'\n'为分隔符）
                    self._process_message_buffer(buffer_bytes, device_id)

                except socket.timeout:
                    # 处理超时
                    continue
                except Exception as e:
                    logger.error(f"接收或处理消息时出错: {e}")
                    # 继续监听连接，不要中断

        except Exception as e:
            logger.error(f"处理客户端时出错: {e}")
        finally:
            # 清理设备连接
            if device_id:  # 确保device_id已定义
                with self.devices_lock:
                    if device_id in self.devices:
                        self.devices[device_id].connected = False
                        self.devices.pop(device_id, None)
                        logger.info(f"设备 {device_id} 连接已清理")
            # 清理设备连接
            with self.devices_lock:
                if device_id in self.devices:
                    self.devices[device_id].connected = False
                    self.devices.pop(device_id, None)

            try:
                client_socket.close()
            except:
                pass

    def _process_message_buffer(self, buffer_bytes, device_id):
        """处理消息缓冲区，提取完整的消息并处理"""
        # 查找消息分隔符位置
        while b'\n' in buffer_bytes:
            # 分割出一条完整消息
            pos = buffer_bytes.find(b'\n')
            message_bytes = buffer_bytes[:pos]
            # 从缓冲区移除这条消息(包括\n)
            del buffer_bytes[:pos + 1]

            if not message_bytes:
                continue  # 跳过空消息

            # 尝试解码消息
            try:
                message_str = message_bytes.decode('utf-8')
            except UnicodeDecodeError:
                logger.error("无法以UTF-8解码消息，尝试其他编码...")
                try:
                    # 尝试latin1编码（可以解码任何字节序列）
                    message_str = message_bytes.decode('latin1')
                    logger.info("使用latin1成功解码消息")
                except Exception as e:
                    logger.error(f"解码消息失败: {e}")
                    continue

            # 解析JSON消息
            try:
                message = json.loads(message_str)
                self._handle_client_message(device_id, message)
            except json.JSONDecodeError as e:
                logger.error(f"解析JSON消息失败: {e}, 消息长度: {len(message_str)}")
                # 如果是非常大的消息，记录一部分用于调试
                if len(message_str) > 1000:
                    logger.debug(f"消息开始部分: {message_str[:500]}")
                    logger.debug(f"消息结束部分: {message_str[-500:]}")

    def _handle_handshake(self, client_socket) -> str:
        """处理握手协议，返回设备ID"""
        try:
            # 设置接收超时
            client_socket.settimeout(10.0)  # 10秒超时

            # 创建缓冲区接收握手消息
            buffer_bytes = bytearray()
            while b'\n' not in buffer_bytes:
                chunk = client_socket.recv(4096)
                if not chunk:
                    return None
                buffer_bytes.extend(chunk)

            # 提取完整消息
            pos = buffer_bytes.find(b'\n')
            message_bytes = buffer_bytes[:pos]

            try:
                message_str = message_bytes.decode('utf-8')
                message = json.loads(message_str)
            except Exception as e:
                logger.error(f"解析握手消息失败: {e}")
                return None

            if message.get("type") != "handshake":
                logger.warning(f"预期握手消息，但收到: {message.get('type')}")
                return None

            device_id = message.get("deviceId")
            if not device_id:
                logger.warning("握手消息中没有设备ID")
                return None

            # 设备信息
            device_info = message.get("deviceInfo", {})
            logger.info(f"设备信息: {device_info}")

            # 发送握手响应
            response = {
                "type": "handshake_response",
                "status": "ok",
                "timestamp": time.time()
            }
            client_socket.sendall((json.dumps(response) + '\n').encode('utf-8'))

            # 重置为无阻塞模式
            client_socket.settimeout(None)

            return device_id

        except Exception as e:
            logger.error(f"握手错误: {e}")
            return None

    def _handle_client_message(self, device_id, message):
        """处理来自客户端的消息"""
        message_type = message.get("type")

        if message_type == "heartbeat":
            # 心跳消息，更新设备最后活动时间
            with self.devices_lock:
                if device_id in self.devices:
                    self.devices[device_id].last_seen = time.time()

            # 发送心跳响应
            response = {
                "type": "heartbeat_response",
                "timestamp": time.time()
            }

            with self.devices_lock:
                if device_id in self.devices and self.devices[device_id].socket:
                    try:
                        self.devices[device_id].socket.sendall(
                            (json.dumps(response) + '\n').encode('utf-8'))
                    except:
                        pass

        elif message_type == "response":
            # 响应消息，处理挂起的请求
            request_id = message.get("requestId")
            logger.info(f"收到设备 {device_id} 的响应: {request_id}")

            with self.devices_lock:
                if device_id in self.devices:
                    device = self.devices[device_id]
                    if request_id in device.pending_requests:
                        # 获取请求信息
                        request_info = device.pending_requests.pop(request_id, None)
                        if request_info:
                            original_request = request_info.get("request")
                            callback = request_info.get("callback")

                            if callback:
                                # 检查是否包含 device_state 数据
                                response_data = message.get("data", {})
                                status = response_data.get("status")
                                error = response_data.get("error")
                                device_state = None

                                if original_request and original_request.action_type == MCPActionTypes.GET_UI_STATE:
                                    # 处理UI状态响应
                                    device_state_str = response_data.get("message")
                                    if device_state_str and isinstance(device_state_str, str):
                                        try:
                                            # 尝试将JSON字符串转换为字典
                                            device_state_dict = json.loads(device_state_str)

                                            # 创建DeviceState对象
                                            device_state = DeviceState()
                                            device_state.current_package = device_state_dict.get("current_package")
                                            device_state.current_activity = device_state_dict.get("current_activity")
                                            device_state.screen_state = device_state_dict.get("screen_state")
                                            device_state.ui_hierarchy = device_state_dict.get("ui_hierarchy", {})
                                            device_state.visible_text = device_state_dict.get("visible_text", [])
                                            device_state.device_info = device_state_dict.get("device_info", {})
                                        except json.JSONDecodeError as e:
                                            logger.error(f"解析设备状态JSON失败: {e}")
                                            # 记录部分状态数据便于调试
                                            if device_state_str and len(device_state_str) > 1000:
                                                logger.debug(f"状态数据开始部分: {device_state_str[:500]}")
                                                logger.debug(f"状态数据结束部分: {device_state_str[-500:]}")
                                            # 如果无法解析JSON，保留原始字符串
                                            device_state = device_state_str
                                        except Exception as e:
                                            logger.error(f"处理device_state时出错: {e}")
                                            device_state = device_state_str

                                # 构造响应对象
                                response = Response(
                                    request_id=request_id,
                                    status=status,
                                    data=response_data,
                                    error=error,
                                    device_state=device_state
                                )

                                # 异步执行回调
                                threading.Thread(target=callback, args=(response,)).start()

        elif message_type == "event":
            # 事件消息
            event_type = message.get("eventType")
            session_id = message.get("sessionId")

            if session_id:
                with self.sessions_lock:
                    if session_id in self.sessions:
                        session = self.sessions[session_id]
                        # 更新会话状态
                        session.last_updated = time.time()

            logger.info(f"收到设备事件: {event_type} from {device_id}")

        else:
            logger.warning(f"未知消息类型: {message_type} from {device_id}")

    def stop(self):
        """停止服务器"""
        self.running = False

        # 关闭所有设备连接
        with self.devices_lock:
            for device_id, device in self.devices.items():
                try:
                    if device.socket:
                        device.socket.close()
                except:
                    pass
            print("准备清理了devices")
            self.devices.clear()

        # 关闭服务器socket
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None

        logger.info("MCP服务器已停止")

    def learn_apps(self, device_id: str):
        """学习设备上的应用，支持深度学习模式"""
        with self.devices_lock:
            if device_id not in self.devices:
                logger.error(f"设备未找到: {device_id}")
                return None

        logger.info(f"开始学习设备上的应用: {device_id}")

        # 如果有AppDeepExplorer，使用它进行批量深度学习
        if hasattr(self, 'app_deep_explorer') and self.app_deep_explorer:
            try:
                # 首先获取已安装的应用列表
                session_id = str(uuid.uuid4())

                # 在会话管理中注册临时会话
                with self.sessions_lock:
                    self.sessions[session_id] = SessionContext(
                        session_id=session_id,
                        device_id=device_id,
                        user_instruction=f"批量深度学习设备应用"
                    )

                device = self.devices[device_id]

                # 创建获取已安装应用的请求
                request = Request(
                    request_id=str(uuid.uuid4()),
                    action_type="get_installed_apps",
                    context=Context(session_id=session_id)
                )

                # 发送请求并设置回调，回调中会启动深度学习流程
                device.send_request(
                    request,
                    lambda response: self._on_apps_received_for_deep_learning(response, session_id)
                )

                logger.info(f"批量深度学习会话已启动: {session_id}")
                return session_id

            except Exception as e:
                logger.error(f"启动批量深度学习失败: {e}")
                # 如果失败，回退到传统方式

        # 如果没有深度探索器或深度探索启动失败，使用传统方式
        session_id = self.app_learner.start_app_learning(device_id, self)
        logger.info(f"传统学习会话已启动: {session_id}")
        return session_id

    def learn_apps(self, device_id: str):
        """学习设备上的应用，支持深度学习模式"""
        with self.devices_lock:
            if device_id not in self.devices:
                logger.error(f"设备未找到: {device_id}")
                return None

        logger.info(f"开始学习设备上的应用: {device_id}")

        # 如果有AppDeepExplorer，使用它进行批量深度学习
        if hasattr(self, 'app_deep_explorer') and self.app_deep_explorer:
            try:
                # 首先获取已安装的应用列表
                session_id = str(uuid.uuid4())

                # 在会话管理中注册临时会话
                with self.sessions_lock:
                    self.sessions[session_id] = SessionContext(
                        session_id=session_id,
                        device_id=device_id,
                        user_instruction=f"批量深度学习设备应用"
                    )

                device = self.devices[device_id]

                # 创建获取已安装应用的请求
                request = Request(
                    request_id=str(uuid.uuid4()),
                    action_type="get_installed_apps",
                    context=Context(session_id=session_id)
                )

                # 发送请求并设置回调，回调中会启动深度学习流程
                device.send_request(
                    request,
                    lambda response: self._on_apps_received_for_deep_learning(response, session_id)
                )

                logger.info(f"批量深度学习会话已启动: {session_id}")
                return session_id

            except Exception as e:
                logger.error(f"启动批量深度学习失败: {e}")
                # 如果失败，回退到传统方式

        # 如果没有深度探索器或深度探索启动失败，使用传统方式
        session_id = self.app_learner.start_app_learning(device_id, self)
        logger.info(f"传统学习会话已启动: {session_id}")
        return session_id

    def _on_apps_received_for_deep_learning(self, response: Response, session_id: str):
        """处理已安装应用列表并启动深度学习"""
        if response.status != "success":
            logger.error(f"获取已安装应用失败: {response.error}")
            return

        try:
            with self.sessions_lock:
                if session_id not in self.sessions:
                    logger.error(f"会话 {session_id} 不存在")
                    return

                device_id = self.sessions[session_id].device_id

            # 解析应用列表
            import ast
            apps = ast.literal_eval(response.data.get("message", "").strip())
            logger.info(f"收到 {len(apps)} 个已安装应用")

            # 过滤出需要学习的应用（可以使用app_deep_explorer的筛选逻辑）
            if hasattr(self, 'app_deep_explorer') and self.app_deep_explorer:
                interesting_apps = self.app_deep_explorer._filter_interesting_apps(apps)
                logger.info(f"过滤后将学习 {len(interesting_apps)} 个应用")

                # 创建学习队列
                learning_queue = []
                for app in interesting_apps:
                    package_name = app.get("packageName")
                    if package_name:
                        learning_queue.append(package_name)

                # 存储学习队列到会话
                with self.sessions_lock:
                    if session_id in self.sessions:
                        self.sessions[session_id].learning_queue = learning_queue
                        self.sessions[session_id].current_learning_index = 0

                # 开始学习第一个应用
                self._learn_next_app_deeply(session_id)

        except Exception as e:
            logger.error(f"处理应用列表并启动深度学习时出错: {e}")

    def _learn_next_app_deeply(self, session_id: str):
        """学习队列中的下一个应用"""
        try:
            with self.sessions_lock:
                if session_id not in self.sessions:
                    logger.error(f"会话 {session_id} 不存在")
                    return

                session = self.sessions[session_id]
                if not hasattr(session, 'learning_queue') or not hasattr(session, 'current_learning_index'):
                    logger.error(f"会话 {session_id} 缺少学习队列或索引")
                    return

                # 检查是否已完成所有应用的学习
                if session.current_learning_index >= len(session.learning_queue):
                    logger.info(f"会话 {session_id} 已完成所有应用的学习")
                    return

                device_id = session.device_id
                package_name = session.learning_queue[session.current_learning_index]

                # 更新索引为下一个应用
                session.current_learning_index += 1

            # 启动当前应用的深度学习
            logger.info(
                f"开始深度学习应用 [{session.current_learning_index}/{len(session.learning_queue)}]: {package_name}")

            # 使用app_deep_explorer进行深度学习
            if hasattr(self, 'app_deep_explorer') and self.app_deep_explorer:
                # 启动应用探索，并指定学习完成后的回调
                exploration_session_id = self.app_deep_explorer.start_app_exploration(
                    device_id, package_name, self)

                # 在app_deep_explorer中注册学习完成的回调
                self.app_deep_explorer.exploration_sessions[exploration_session_id]["on_completed"] = \
                    lambda: self._on_app_learning_completed(session_id)

                logger.info(f"应用 {package_name} 的深度学习已启动，探索会话ID: {exploration_session_id}")

        except Exception as e:
            logger.error(f"启动下一个应用的深度学习时出错: {e}")
            # 尝试继续学习下一个应用
            self._on_app_learning_completed(session_id)

    def _on_app_learning_completed(self, session_id: str):
        """单个应用学习完成后的回调处理"""
        try:
            with self.sessions_lock:
                if session_id not in self.sessions:
                    logger.error(f"会话 {session_id} 不存在")
                    return

                session = self.sessions[session_id]
                total = len(session.learning_queue) if hasattr(session, 'learning_queue') else 0
                current = session.current_learning_index if hasattr(session, 'current_learning_index') else 0

            logger.info(f"应用学习完成 [{current}/{total}]")

            # 短暂等待以避免过快启动下一个应用
            time.sleep(2)

            # 继续学习下一个应用
            self._learn_next_app_deeply(session_id)

        except Exception as e:
            logger.error(f"处理应用学习完成回调时出错: {e}")

    def learn_app(self, device_id: str, package_name: str):
        """学习特定应用"""
        with self.devices_lock:
            if device_id not in self.devices:
                logger.error(f"设备未找到: {device_id}")
                return None

            device = self.devices[device_id]

        logger.info(f"开始学习应用: {package_name}")

        # 创建一个临时会话
        session_id = str(uuid.uuid4())

        # 在会话管理中注册临时会话
        with self.sessions_lock:
            self.sessions[session_id] = SessionContext(
                session_id=session_id,
                device_id=device_id,
                user_instruction=f"学习应用: {package_name}"
            )

        # 启动应用
        request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.LAUNCH_APP,
            parameters={"packageName": package_name},
            context=Context(session_id=session_id)
        )

        # 发送请求
        device.send_request(request, lambda response: self._on_specific_app_launched(
            response, session_id, package_name))

        return session_id

    def _on_specific_app_launched(self, response: Response, session_id: str, package_name: str):
        """特定应用启动后回调"""
        if response.status != "success":
            logger.error(f"启动应用失败: {response.error}")
            return

        with self.sessions_lock:
            if session_id not in self.sessions:
                return

            session = self.sessions[session_id]
            device_id = session.device_id

        with self.devices_lock:
            if device_id not in self.devices:
                return

            device = self.devices[device_id]

        # 等待应用启动
        time.sleep(3)

        # 获取应用UI状态
        ui_request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.GET_UI_STATE,
            context=Context(session_id=session_id)
        )

        device.send_request(ui_request, lambda response: self._analyze_specific_app(
            response, session_id, package_name))

    def _analyze_specific_app(self, response: Response, session_id: str, package_name: str):
        """分析特定应用"""
        if response.status != "success":
            logger.error(f"获取UI状态失败: {response.error}")
            return

        with self.sessions_lock:
            if session_id not in self.sessions:
                return

        # 分析应用UI
        device_state = response.device_state
        if device_state:
            logger.info(f"正在分析应用UI: {package_name}")

            # 使用应用学习器分析UI
            app_info = {
                "packageName": package_name,
                "appName": package_name.split(".")[-1]
            }

            # 创建一个模拟的学习会话
            learning_session = {
                "device_id": self.sessions[session_id].device_id,
                "status": "learning_app",
                "current_app": app_info,
                "current_task": "explore_ui",
                "actions": [],
                "start_time": time.time()
            }

            # 临时添加到学习会话
            temp_session_id = str(uuid.uuid4())
            self.app_learner.learning_sessions[temp_session_id] = learning_session

            # 分析UI
            self.app_learner._analyze_app_ui(response, temp_session_id, self)

            # 清理临时会话
            self.app_learner.learning_sessions.pop(temp_session_id, None)

            logger.info(f"应用学习完成: {package_name}")
            logger.info("已识别关键元素:")

            app_knowledge = self.app_learner.app_knowledge.get(package_name, {})
            elements = app_knowledge.get("elements", {})

            for element_id, element_info in elements.items():
                element_type = element_info.get("type", "unknown")
                element_text = element_info.get("text", "")
                logger.info(f"  - {element_id}: {element_type} - {element_text}")

            # 保存应用知识
            self.app_learner._save_app_knowledge()
        else:
            logger.error("没有可用的设备状态")

        # 返回主屏幕
        home_request = Request(
            request_id=str(uuid.uuid4()),
            action_type=MCPActionTypes.PRESS_HOME,
            context=Context(session_id=session_id)
        )

        with self.devices_lock:
            device = self.devices.get(self.sessions[session_id].device_id)
            if device:
                device.send_request(home_request, lambda r: self._cleanup_learning_session(r, session_id))

    def _cleanup_learning_session(self, response: Response, session_id: str):
        """清理学习会话"""
        # 移除临时会话
        with self.sessions_lock:
            if session_id in self.sessions:
                self.sessions.pop(session_id)

        logger.info("学习会话已完成")

    def execute_command(self, device_id: str, command: str, session_id: str):
        """执行指令"""
        with self.devices_lock:
            if device_id not in self.devices:
                return {"status": "error", "message": "设备未找到"}

            device = self.devices[device_id]

        # 创建会话
        if not session_id:
            session_id = str(uuid.uuid4())

        with self.sessions_lock:
            self.sessions[session_id] = SessionContext(
                session_id=session_id,
                device_id=device_id,
                user_instruction=command
            )

        # 使用MCP上下文解析命令
        result = self.mcp_context.execute_command(device_id, command)

        if result["status"] == "success":
            actions = result.get("actions", [])

            # 执行动作序列
            self._execute_actions(device, session_id, actions)

        return result

    def _execute_actions(self, device, session_id, actions):
        """执行动作序列"""
        for i, action in enumerate(actions):
            action_type = action.get("action")
            params = action.get("params", {})

            # 特殊处理LAUNCH_APP操作
            if action_type == MCPActionTypes.LAUNCH_APP:
                # 检查是否有完整组件名
                if "fullComponent" in params:
                    # 使用完整组件名启动
                    request = Request(
                        request_id=str(uuid.uuid4()),
                        action_type=action_type,
                        parameters={"component": params["fullComponent"]},
                        context=Context(session_id=session_id)
                    )
                elif "packageName" in params and "activityName" in params:
                    # 构建完整组件名
                    full_component = f"{params['packageName']}/{params['activityName']}"
                    request = Request(
                        request_id=str(uuid.uuid4()),
                        action_type=action_type,
                        parameters={"component": full_component},
                        context=Context(session_id=session_id)
                    )
                else:
                    # 只使用包名启动
                    request = Request(
                        request_id=str(uuid.uuid4()),
                        action_type=action_type,
                        parameters=params,
                        context=Context(session_id=session_id)
                    )
            else:
                # 其他操作的处理
                request = Request(
                    request_id=str(uuid.uuid4()),
                    action_type=action_type,
                    parameters=params,
                    context=Context(session_id=session_id)
                )

            # 发送请求
            device.send_request(request, lambda response: self._on_action_response(
                response, session_id, i, len(actions)))

            # 如果有等待时间，则等待
            if action_type == "wait" and "milliseconds" in params:
                time.sleep(params["milliseconds"] / 1000)

    def _on_action_response(self, response, session_id, action_index, total_actions):
        """动作响应回调"""
        if response.status != "success":
            logger.error(f"动作执行失败 ({action_index + 1}/{total_actions}): {response.error}")
        else:
            logger.info(f"动作执行成功 ({action_index + 1}/{total_actions})")

        # 如果是最后一个动作，清理会话
        if action_index == total_actions - 1:
            with self.sessions_lock:
                if session_id in self.sessions:
                    self.sessions[session_id].active = False

    def create_or_get_session(self, device_id, user_id=None):
        """创建或获取用户会话"""
        # 生成会话ID
        session_id = str(uuid.uuid4())

        # 创建新会话
        with self.sessions_lock:
            session = SessionContext(
                session_id=session_id,
                device_id=device_id
            )
            self.sessions[session_id] = session

        return session_id

    def update_session_context(self, session_id, new_data):
        """更新会话上下文"""
        with self.sessions_lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                # 更新会话数据
                for key, value in new_data.items():
                    if hasattr(session, key):
                        setattr(session, key, value)
                # 更新最后活动时间
                session.last_updated = time.time()
                return True
        return False
