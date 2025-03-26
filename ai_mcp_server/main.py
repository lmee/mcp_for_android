import logging
from flask import Flask

from mcp.mcp_interface import MCPContext, MCPServer
from mcp.model_interface import ModelInterface
from mcp.route_handler import RouteHandler
from app_learn.app_learner import AppLearner
from mcp.mcp_protocol import MCPActionTypes

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# 预定义一些常见的指令模式
def initialize_patterns(mcp_context):
    # 音乐播放模式
    mcp_context.learn_pattern(
        "听某人的歌",
        [
            {"action": MCPActionTypes.LAUNCH_APP, "params": {"packageName": "com.netease.cloudmusic"}},
            {"action": "wait", "params": {"milliseconds": 1000}},
            {"action": MCPActionTypes.CLICK, "params": {"selector": "id=search_button"}},
            {"action": MCPActionTypes.TYPE_TEXT,
             "params": {"selector": "class=android.widget.EditText", "text": "{{search_term}}"}},
            {"action": MCPActionTypes.CLICK, "params": {"selector": "text=搜索"}},
            {"action": "wait", "params": {"milliseconds": 500}},
            {"action": MCPActionTypes.CLICK, "params": {"selector": "text={{search_term}}"}},
            {"action": MCPActionTypes.CLICK, "params": {"selector": "text=播放"}}
        ]
    )

    # 打开应用模式
    mcp_context.learn_pattern(
        "打开某个应用",
        [
            {"action": MCPActionTypes.LAUNCH_APP, "params": {"packageName": "{{app_name}}"}}
        ],
        {
            "app_name": r"打开\s*([^\s,，。.]+)"  # 提取应用名称的正则表达式
        }
    )

    # 视频观看模式
    mcp_context.learn_pattern(
        "看视频",
        [
            {"action": MCPActionTypes.LAUNCH_APP, "params": {"packageName": "tv.danmaku.bili"}},
            {"action": "wait", "params": {"milliseconds": 1000}},
            {"action": MCPActionTypes.CLICK, "params": {"selector": "id=search_button"}},
            {"action": MCPActionTypes.TYPE_TEXT,
             "params": {"selector": "class=android.widget.EditText", "text": "{{search_term}}"}},
            {"action": MCPActionTypes.CLICK, "params": {"selector": "text=搜索"}},
            {"action": "wait", "params": {"milliseconds": 500}},
            {"action": MCPActionTypes.CLICK, "params": {"selector": "class=android.widget.ImageView"}}
        ]
    )

    # 搜索模式
    mcp_context.learn_pattern(
        "搜索信息",
        [
            {"action": MCPActionTypes.LAUNCH_APP, "params": {"packageName": "com.baidu.searchbox"}},
            {"action": "wait", "params": {"milliseconds": 1000}},
            {"action": MCPActionTypes.CLICK, "params": {"selector": "id=search_button"}},
            {"action": MCPActionTypes.TYPE_TEXT,
             "params": {"selector": "class=android.widget.EditText", "text": "{{search_term}}"}},
            {"action": MCPActionTypes.CLICK, "params": {"selector": "text=搜索"}}
        ]
    )


def enhance_mcp_with_model(mcp_context, mcp_server, model_interface):
    """增强MCP与模型接口的集成"""

    # 扩展MCP上下文的execute_command方法以使用模型接口
    original_execute_command = mcp_context.execute_command

    def enhanced_execute_command(device_id, command):
        # 首先尝试使用原始方法寻找匹配的模式
        result = original_execute_command(device_id, command)

        # 如果没有找到匹配的模式，使用模型接口分析意图
        if result["status"] == "unknown_command":
            logger.info(f"未找到匹配模式，尝试使用模型接口分析意图: {command}")

            # 获取设备状态
            device_state = mcp_context._get_current_device_state(device_id)

            # 构建用户上下文
            user_context = mcp_context._build_user_context(device_id)

            # 获取应用知识库
            app_knowledge = {}
            if "recent_apps" in user_context and user_context["recent_apps"]:
                recent_app = user_context["recent_apps"][0]
                app_knowledge = model_interface.get_app_knowledge(app_name=recent_app)

            # 分析意图
            intent = model_interface.analyze_user_intent(
                command, user_context, device_state
            )

            # 如果分析出应用意图
            if intent and intent.get("app"):
                app_name = intent.get("app")
                package_name = intent.get("package_name")

                # 如果没有包名但有应用名，尝试查找包名
                if not package_name and app_name and mcp_context.app_learner:
                    package_name = mcp_context.app_learner.find_app_by_name(app_name)

                # 获取操作序列
                actions = []
                if "actions" in intent:
                    actions = intent["actions"]
                elif package_name:
                    # 使用意图中包含的优化元素（如果有）
                    if "app_elements" in intent:
                        elements = intent["app_elements"]
                        # 创建包含优化元素的app_knowledge
                        app_knowledge = {
                            "elements": elements,
                            "actions": []
                        }

                        # 如果需要其他信息，可以从完整知识库获取
                        full_knowledge = model_interface.get_app_knowledge(package_name=package_name)
                        if full_knowledge:
                            app_knowledge["actions"] = full_knowledge.get("actions", [])
                    else:
                        # 获取完整app知识库
                        app_knowledge = model_interface.get_app_knowledge(package_name=package_name)
                    # 生成操作序列
                    actions = model_interface.generate_action_sequence(intent, app_knowledge)

                if actions:
                    # 记录历史
                    mcp_context.action_history.append({
                        "device_id": device_id,
                        "command": command,
                        "intent": intent,
                        "actions": actions
                    })

                    return {
                        "status": "success",
                        "actions": actions,
                        "app": app_name,
                        "message": model_interface.explain_action_plan(actions, command)
                    }

            # 如果没有识别出意图或没有操作序列，返回失败
            return {
                "status": "model_failed",
                "message": "模型无法理解您的指令，请尝试使用其他表达方式。"
            }

        return result

    # 替换原方法
    mcp_context.execute_command = enhanced_execute_command

    # 扩展MCP服务器的execute_command方法以处理错误
    original_server_execute = mcp_server.execute_command

    def enhanced_server_execute(device_id, command, session_id):
        result = original_server_execute(device_id, command, session_id)

        # 如果执行失败，使用模型生成友好错误信息
        if result["status"] in ["error", "model_failed"]:
            error_message = result.get("message", "未知错误")
            friendly_message = model_interface.handle_error(error_message, command)
            result["message"] = friendly_message

        return result

    # 替换原方法
    mcp_server.execute_command = enhanced_server_execute


def main():
    try:
        # 初始化Flask应用
        app = Flask(__name__)

        # 初始化应用学习器
        app_learner = AppLearner()

        # 初始化MCP上下文
        mcp_context = MCPContext()
        mcp_context.app_learner = app_learner

        # 初始化预定义模式
        initialize_patterns(mcp_context)

        # 创建MCP服务器实例
        mcp_server = MCPServer(host='0.0.0.0', port=8080, mcp_context=mcp_context)
        # 设置MCP上下文与服务器的关联
        mcp_context.mcp_server = mcp_server

        from app_learn.app_deep_explorer import AppExplorer
        app_deep_explorer = AppExplorer(app_learner)  # 传入app_learner以共享知识库
        mcp_server.app_deep_explorer = app_deep_explorer

        # 初始化模型接口
        model_interface = ModelInterface(api_key="api_key",
                                         base_url="base_url",app_learner=app_learner)
        # 增强MCP与模型的集成
        enhance_mcp_with_model(mcp_context, mcp_server, model_interface)

        # 初始化路由处理器
        RouteHandler(app, mcp_context, mcp_server, model_interface)

        # 启动MCP服务器
        logger.info("正在启动MCP服务器...")
        mcp_server.start()

        # 启动Flask应用
        logger.info("正在启动Flask应用...")
        app.run(host='0.0.0.0', port=5000, debug=False)

    except Exception as e:
        logger.error(f"启动应用时出错: {e}")
    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭服务...")
    finally:
        # 确保正确关闭MCP服务器
        if 'mcp_server' in locals():
            logger.info("正在关闭MCP服务器...")
            mcp_server.stop()


if __name__ == "__main__":
    main()
