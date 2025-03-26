import logging
import time

from flask import request, jsonify

logger = logging.getLogger(__name__)


class RouteHandler:
    """路由处理类，封装所有API路由的处理逻辑"""

    def __init__(self, app, mcp_context, mcp_server, model_interface):
        """
        初始化路由处理器

        Args:
            app: Flask应用实例
            mcp_context: MCP上下文
            mcp_server: MCP服务器
            model_interface: 模型接口
        """
        self.app = app
        self.mcp_context = mcp_context
        self.mcp_server = mcp_server
        self.model_interface = model_interface  # 保存模型接口引用

        # 注册所有路由
        self._register_routes()

    def _register_routes(self):
        """注册所有API路由"""
        # 设备注册路由
        self.app.route('/register_device', methods=['POST'])(self.register_device)

        # 指令执行路由
        self.app.route('/execute', methods=['POST'])(self.execute_command)

        # 学习指令路由
        self.app.route('/learn', methods=['POST'])(self.learn_command)

        # 学习应用路由
        self.app.route('/learn_app', methods=['POST'])(self.learn_app)

        # 获取设备状态路由
        self.app.route('/status', methods=['GET'])(self.get_status)
        
        # 添加新的自然语言理解路由
        self.app.route('/analyze', methods=['POST'])(self.analyze_text)

    # Flask路由实现
    def register_device(self):
        """注册设备API"""
        data = request.json
        device_id = data.get('device_id')
        capabilities = data.get('capabilities', [])

        if not device_id:
            return jsonify({"status": "error", "message": "缺少设备ID"}), 400

        self.mcp_context.register_device(device_id, capabilities)
        return jsonify({"status": "success", "message": f"设备 {device_id} 已注册"})

    def execute_command(self):
        """执行指令API"""
        data = request.json
        device_id = data.get('device_id')
        command = data.get('command')
        session_id = data.get('session_id')  # 可选，如已有会话

        if not device_id or not command:
            return jsonify({"status": "error", "message": "缺少设备ID或指令"}), 400

        # 获取或创建会话
        if not session_id:
            session_id = self.mcp_server.create_or_get_session(device_id)

        # 记录当前命令到会话
        self.mcp_server.update_session_context(
            session_id, 
            {"user_instruction": command, "last_command_time": time.time()}
        )

        # 使用模型接口进行命令前处理（如果需要）
        try:
            # 可以在这里添加命令的预处理，如纠正拼写错误、补充省略的命令等
            processed_command = command
            # 例如：如果命令很短且看起来不完整，可以尝试补充
            if len(command) < 10 and not any(keyword in command for keyword in ["打开", "关闭", "播放", "搜索"]):
                # 构建用户上下文
                user_context = self.mcp_context._build_user_context(device_id)
                if user_context and user_context.get("previous_queries"):
                    # 使用模型接口分析命令是否是上一个命令的后续
                    if self.model_interface._is_follow_up_query(command, user_context["previous_queries"][-1]):
                        # 补充命令
                        context = {"previous_query": user_context["previous_queries"][-1]}
                        intent = self.model_interface.analyze_user_intent(command, context)
                        if intent and intent.get("full_command"):
                            processed_command = intent.get("full_command")
                            logger.info(f"命令已补充: {command} -> {processed_command}")
        except Exception as e:
            logger.error(f"命令预处理出错: {e}")
            processed_command = command

        # 执行命令
        result = self.mcp_server.execute_command(device_id, processed_command, session_id)

        # 将会话ID添加到响应中
        if result.get("status") != "error":
            result["session_id"] = session_id

        return jsonify(result)

    def learn_command(self):
        """学习新指令API"""
        data = request.json
        command = data.get('command')
        actions = data.get('actions', [])

        if not command or not actions:
            return jsonify({"status": "error", "message": "缺少指令或动作序列"}), 400

        self.mcp_context.learn_pattern(command, actions)
        
        # 使用模型接口分析命令模式，提取关键特征
        try:
            # 分析命令模式
            pattern_analysis = self.model_interface.analyze_user_intent(command)
            if pattern_analysis and pattern_analysis.get("intent"):
                # 记录学习结果
                learning_record = {
                    "command": command,
                    "pattern": pattern_analysis.get("intent"),
                    "actions": actions,
                    "learned_at": time.time()
                }
                logger.info(f"学习了新的命令模式: {learning_record}")
                
                # 这里可以实现更复杂的学习逻辑，如更新模式识别规则等
        except Exception as e:
            logger.error(f"分析命令模式时出错: {e}")

        return jsonify({"status": "success", "message": "已学习新的指令模式"})

    def learn_app(self):
        """学习应用API"""
        data = request.json
        device_id = data.get('device_id')
        package_name = data.get('package_name')  # 可选

        if not device_id:
            return jsonify({"status": "error", "message": "缺少设备ID"}), 400

        if package_name:
            session_id = self.mcp_server.learn_app(device_id, package_name)
        else:
            session_id = self.mcp_server.learn_apps(device_id)

        if session_id:
            return jsonify({
                "status": "success",
                "message": f"学习会话已启动",
                "session_id": session_id
            })
        else:
            return jsonify({"status": "error", "message": "启动学习会话失败"}), 500

    def get_status(self):
        """获取服务状态API"""
        # 获取设备数量
        with self.mcp_server.devices_lock:
            devices_count = len(self.mcp_server.devices)
            # 获取设备列表
            devices = list(self.mcp_server.devices.keys())

        # 获取会话数量
        with self.mcp_server.sessions_lock:
            sessions_count = len(self.mcp_server.sessions)

        # 获取模式数量
        patterns_count = len(self.mcp_context.known_patterns)

        return jsonify({
            "status": "running",
            "connected_devices": devices_count,
            "devices": devices,
            "active_sessions": sessions_count,
            "known_patterns": patterns_count,
            "action_history_count": len(self.mcp_context.action_history)
        })
        
    def analyze_text(self):
        """分析文本API - 使用模型接口分析自然语言"""
        data = request.json
        text = data.get('text')
        device_id = data.get('device_id')
        
        if not text:
            return jsonify({"status": "error", "message": "缺少文本内容"}), 400
            
        try:
            # 获取设备状态和用户上下文
            device_state = None
            user_context = {}
            
            if device_id:
                device_state = self.mcp_context._get_current_device_state(device_id)
                user_context = self.mcp_context._build_user_context(device_id)

            # 使用模型接口分析文本
            analysis = self.model_interface.analyze_user_intent(text, user_context,device_state)
            # 如果识别出应用意图，尝试生成操作序列
            if analysis.get("app"):
                app_name = analysis.get("app")
                package_name = analysis.get("package_name")
                
                # 获取app知识库
                app_knowledge = self.model_interface.get_app_knowledge(
                    app_name=app_name, 
                    package_name=package_name
                )
                
                # 生成操作序列
                if "actions" not in analysis or not analysis["actions"]:
                    actions = self.model_interface.generate_action_sequence(
                        analysis, 
                        app_knowledge.get("actions", [])
                    )
                    if actions:
                        analysis["actions"] = actions
                        analysis["explanation"] = self.model_interface.explain_action_plan(actions, text)
            return jsonify({
                "status": "success",
                "analysis": analysis
            })
        except Exception as e:
            logger.error(f"分析文本时出错: {e}")
            return jsonify({
                "status": "error",
                "message": f"分析文本时出错: {str(e)}"
            }), 500