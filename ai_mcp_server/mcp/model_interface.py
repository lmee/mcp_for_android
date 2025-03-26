import logging
import json
import os
from typing import Dict, List, Any, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)


class ModelInterface:
    """模型接口类，负责与AI模型通信并处理自然语言理解"""

    def __init__(self, api_key=None, base_url=None, model_name="deepseek-ai/DeepSeek-V3", app_learner=None):
        """
        初始化模型接口
        
        Args:
            api_key: DeepSeek API密钥，如果为None则从环境变量获取
            base_url: DeepSeek API基础URL，如果为None则使用默认值
            model_name: 使用的模型名称，默认为"deepseek-chat"
            app_learner: 应用学习器实例 
        """
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            logger.warning("未设置DEEPSEEK_API_KEY环境变量或提供API密钥")

        self.base_url = base_url or "https://api.deepseek.com/v1"
        self.model_name = model_name
        self.app_learner = app_learner

        # 初始化OpenAI客户端
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,

        )

        # 初始化MCP操作类型描述
        self.mcp_action_descriptions = self._initialize_mcp_action_descriptions()

        logger.info(f"模型接口初始化完成，使用模型: {model_name}")

    def _initialize_mcp_action_descriptions(self) -> Dict[str, Dict]:
        """初始化MCP操作类型描述"""
        from mcp.mcp_protocol import MCPActionTypes

        # 为每种操作类型定义详细描述和参数
        return {
            MCPActionTypes.CLICK: {
                "description": "点击屏幕上的元素",
                "parameters": {
                    "selector": "定位元素的选择器，格式可以是 'id=xxx', 'text=xxx', 'class=xxx' 等"
                }
            },
            MCPActionTypes.LONG_CLICK: {
                "description": "长按屏幕上的元素",
                "parameters": {
                    "selector": "定位元素的选择器",
                    "duration": "长按时间，单位毫秒，默认为1000"
                }
            },
            MCPActionTypes.SWIPE: {
                "description": "在屏幕上滑动",
                "parameters": {
                    "start_x": "起始X坐标",
                    "start_y": "起始Y坐标",
                    "end_x": "结束X坐标",
                    "end_y": "结束Y坐标",
                    "duration": "滑动时间，单位毫秒，默认为300"
                }
            },
            MCPActionTypes.TYPE_TEXT: {
                "description": "在输入框中输入文本",
                "parameters": {
                    "selector": "定位输入框的选择器",
                    "text": "要输入的文本内容"
                }
            },
            MCPActionTypes.SCROLL: {
                "description": "滚动屏幕",
                "parameters": {
                    "direction": "滚动方向，可选值为 'up', 'down', 'left', 'right'",
                    "percent": "滚动幅度，范围0-100"
                }
            },
            MCPActionTypes.LAUNCH_APP: {
                "description": "启动应用",
                "parameters": {
                    "packageName": "应用的包名",
                    "activityName": "可选，应用的主Activity名称（如果需要完整组件名）",
                    "fullComponent": "可选，完整的组件名（包名/.Activity名）"
                }
            },
            MCPActionTypes.PRESS_BACK: {
                "description": "按下返回键"
            },
            MCPActionTypes.PRESS_HOME: {
                "description": "按下Home键"
            },
            MCPActionTypes.PRESS_RECENTS: {
                "description": "按下最近任务键"
            },
            MCPActionTypes.FIND_ELEMENT: {
                "description": "查找元素",
                "parameters": {
                    "selector": "定位元素的选择器"
                }
            },
            MCPActionTypes.GET_TEXT: {
                "description": "获取元素的文本",
                "parameters": {
                    "selector": "定位元素的选择器"
                }
            },
            MCPActionTypes.GET_UI_STATE: {
                "description": "获取当前UI状态"
            },
            MCPActionTypes.GET_INSTALLED_APPS: {
                "description": "获取已安装的应用列表"
            },
            MCPActionTypes.EXECUTE_TASK: {
                "description": "执行预定义任务",
                "parameters": {
                    "taskId": "任务ID",
                    "parameters": "任务参数"
                }
            },
            "wait": {
                "description": "等待指定时间",
                "parameters": {
                    "milliseconds": "等待时间，单位毫秒"
                }
            }
        }

    def analyze_user_intent(self, user_query: str, user_context: Dict = None,
                            device_state=None, app_knowledge: Dict = None) -> Dict[str, Any]:
        """
        统一的用户意图分析函数，支持有/无上下文的分析
        
        Args:
            user_query: 用户的自然语言查询
            user_context: 用户上下文信息（可选）
            device_state: 当前设备状态（可选）
            app_knowledge: 应用知识库（可选），包含已学习的应用信息
            
        Returns:
            包含意图分析结果的字典
        """
        # 获取应用名称到包名的映射
        app_name_to_package = {}
        if self.app_learner:
            for package_name, app_info in self.app_learner.app_knowledge.items():
                if "appName" in app_info:
                    app_name_to_package[app_info["appName"]] = package_name

        # 构建MCP操作描述
        mcp_actions_prompt = json.dumps(self.mcp_action_descriptions, ensure_ascii=False, indent=2)

        # 基础系统提示内容
        base_system_prompt = f"""
        你是一个智能助手，负责分析用户意图以便后续执行。

        你的主要任务是识别用户想要执行的操作类型和目标应用。对于应用名称到包名的映射，请使用以下学习到的对应关系：
        {json.dumps(app_name_to_package, ensure_ascii=False, indent=2)}

        你的输出应该是一个JSON格式的意图分析结果，包含以下核心字段：
        1. intent: 用户的主要意图类型 (例如: "calculate", "play_music", "open_app", "search")
        2. app: 需要使用的应用名称
        3. package_name: 应用的包名 (如果已知)
        4. parameters: 操作所需的关键参数 (如搜索词、计算表达式等)

        注意：此阶段无需生成详细的操作序列，只需准确识别意图和目标应用。
        """

        # 添加上下文相关指令（如果有上下文）
        if user_context or device_state:
            context_prompt = """
            请考虑用户的上下文历史和当前设备状态，理解用户可能省略的信息。
            如果用户查询不完整或含糊，请基于上下文补充推断。
            
            除了基本字段外，请在输出中添加:
            6. context_used: 你使用了哪些上下文信息来理解用户意图
            """
            system_prompt = base_system_prompt + context_prompt
        else:
            system_prompt = base_system_prompt

        # 构建用户提示
        user_prompt_parts = [f"用户指令: {user_query}"]

        # 添加上下文信息（如果有）
        if user_context:
            context_description = json.dumps(user_context, ensure_ascii=False, indent=2)
            user_prompt_parts.append(f"用户上下文信息:\n{context_description}")

        # 添加设备状态信息（如果有）
        if device_state:
            device_state_description = "未知"

            if hasattr(device_state, 'current_package'):
                device_state_description = {
                    "current_package": device_state.current_package,
                    "current_activity": device_state.current_activity,
                    "screen_state": device_state.screen_state,
                    "visible_text": device_state.visible_text[:20] if hasattr(device_state, 'visible_text') else []
                }
            elif isinstance(device_state, dict):
                device_state_description = device_state
            elif isinstance(device_state, str):
                device_state_description = f"原始状态字符串: {device_state[:200]}..."

            device_state_description = json.dumps(device_state_description, ensure_ascii=False, indent=2)
            user_prompt_parts.append(f"当前设备状态:\n{device_state_description}")

        # 添加应用知识库信息（如果有）
        if app_knowledge:
            app_knowledge_description = json.dumps(app_knowledge, ensure_ascii=False, indent=2)
            user_prompt_parts.append(f"已知应用知识:\n{app_knowledge_description}")

        # 组合最终用户提示
        user_prompt_parts.append("请分析用户意图并生成符合MCP协议的操作计划。")
        user_prompt = "\n\n".join(user_prompt_parts)

        try:
            # 调用模型获取基本意图分析
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )

            # 解析响应
            result = json.loads(response.choices[0].message.content.strip())
            logger.info(f"意图分析完成: {result}")

            # 添加原始查询
            if "original_query" not in result:
                result["original_query"] = user_query

            # 获取并添加优化后的应用元素
            if "intent" in result and (result.get("app") or result.get("package_name")):
                optimized_elements = self.get_optimized_app_elements(result, device_state)
                if optimized_elements:
                    result["app_elements"] = optimized_elements
                    logger.info(f"已添加优化后的应用元素: {len(optimized_elements)}个")

            return result

        except Exception as e:
            logger.error(f"调用模型分析意图时出错: {str(e)}")
            return {
                "intent": "error",
                "error": str(e),
                "original_query": user_query
            }

    def generate_action_sequence(self, intent: Dict[str, Any], app_knowledge: Dict = None) -> List[Dict]:
        """
        根据意图生成具体的操作序列
        
        Args:
            intent: 用户意图分析结果
            available_actions: 可用的操作列表
            
        Returns:
            操作序列列表
        """
        if not app_knowledge:
            app_knowledge = {}

        # 提取应用的元素和操作知识
        if "app_elements" in intent:
            elements = intent["app_elements"]
        else:
            elements = app_knowledge.get("elements", {})
        available_actions = app_knowledge.get("actions", [])

        # 构建系统提示
        system_prompt = f"""
        你是一个智能助手，负责将用户意图转化为具体的操作序列。
        基于用户的意图和可用的操作，生成一个详细的操作执行计划。
        
        你可以使用以下MCP(模型上下文协议)定义的操作类型：
        {json.dumps(self.mcp_action_descriptions, ensure_ascii=False, indent=2)}
        
        非常重要：应用知识库中包含了该应用的UI元素信息。当你需要点击或操作这些元素时：
        1. 必须使用应用知识库中的选择器信息
        2. 不要自己创建基于文本的简单选择器(如'text=xxx')，除非知识库中没有相关元素
        3. 知识库中的选择器通常更可靠，包含className、contentDescription、bounds等详细信息
        
        你的输出应该是一个JSON格式的操作序列，每个操作包含以下字段：
        1. action: 操作类型，必须是MCP协议中定义的类型
        2. params: 操作参数，必须符合对应操作类型的参数格式
        
        生成的操作序列必须是完整且可执行的，考虑操作的先后顺序和依赖关系。
        操作应用前，确保添加适当的等待时间(wait操作)，通常需要等待500-1000毫秒。
        """

        # 构建用户提示
        user_prompt = f"""
        用户意图: 
        {json.dumps(intent, ensure_ascii=False, indent=2)}
        
        可用操作:
        {json.dumps(available_actions, ensure_ascii=False, indent=2)}
        
        应用UI元素信息(必须使用这些元素的选择器):
        {json.dumps(elements, ensure_ascii=False, indent=2)}
        
        请生成详细的操作执行序列，确保符合MCP协议格式。
        务必使用应用元素信息中的选择器，而不是创建简单的文本选择器
        """

        try:
            # 调用DeepSeek模型
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )

            # 解析响应 - 处理可能的不同格式
            content = response.choices[0].message.content
            result = json.loads(content)

            # 检查结果格式：可能是数组或包含actions字段的对象
            if isinstance(result, list):
                actions = result  # 直接使用数组作为操作序列
            else:
                actions = result.get("actions", [])  # 从对象中提取actions字段

            # 验证和修正操作序列
            actions = self._validate_and_fix_actions(actions, app_knowledge.get("elements", {}))
            logger.info(f"生成操作序列完成: {actions}")
            return actions

        except Exception as e:
            logger.error(f"调用模型生成操作序列时出错: {str(e)}")
            return []

    def _validate_and_fix_actions(self, actions: List[Dict], elements: Dict) -> List[Dict]:
        """
        验证并修正操作序列，确保使用正确的选择器

        Args:
            actions: 操作序列
            elements: 可用的UI元素信息

        Returns:
            修正后的操作序列
        """
        if not actions or not elements:
            return actions

        fixed_actions = []

        for action in actions:
            fixed_action = action.copy()

            # 对于点击和输入类操作，验证选择器
            if action.get("action") in ["click", "long_click", "type_text"] and "params" in action:
                params = action.get("params", {})

                # 检查是否有选择器
                if "selector" in params:
                    selector = params["selector"]

                    # 检查是否是简单文本选择器
                    if isinstance(selector, str) and selector.startswith("text="):
                        text_value = selector.replace("text=", "")
                        better_selector = self._find_better_selector(text_value, elements)
                        if better_selector:
                            fixed_action["params"]["selector"] = better_selector
                            logger.info(f"修正选择器: {selector} -> {better_selector}")

                    # 检查是否是简单对象选择器
                    elif isinstance(selector, dict) and len(selector) == 1 and "text" in selector:
                        text_value = selector["text"]
                        better_selector = self._find_better_selector(text_value, elements)
                        if better_selector:
                            fixed_action["params"]["selector"] = better_selector
                            logger.info(f"修正选择器: {selector} -> {better_selector}")

            fixed_actions.append(fixed_action)

        # 确保启动应用后添加适当的等待时间
        has_launch_app = any(a.get("action") == "launch_app" for a in fixed_actions)
        has_wait_after_launch = False

        if has_launch_app:
            for i in range(1, len(fixed_actions)):
                prev_action = fixed_actions[i - 1]
                curr_action = fixed_actions[i]

                if prev_action.get("action") == "launch_app" and curr_action.get("action") == "wait":
                    has_wait_after_launch = True
                    # 确保等待时间足够长（至少800毫秒）
                    if "params" in curr_action and "milliseconds" in curr_action["params"]:
                        if curr_action["params"]["milliseconds"] < 800:
                            curr_action["params"]["milliseconds"] = 800
                            logger.info("增加应用启动后的等待时间到800毫秒")
                    break

            # 如果没有等待操作，添加一个
            if not has_wait_after_launch:
                for i, action in enumerate(fixed_actions):
                    if action.get("action") == "launch_app":
                        fixed_actions.insert(i + 1, {
                            "action": "wait",
                            "params": {"milliseconds": 1000}
                        })
                        logger.info("在应用启动后添加1000毫秒等待时间")
                        break

        # 验证序列中是否有无效操作或冗余操作
        i = 0
        while i < len(fixed_actions):
            action = fixed_actions[i]

            # 检查是否是无效的点击操作（没有选择器或坐标）
            if action.get("action") in ["click", "long_click"] and "params" in action:
                params = action["params"]
                if not params.get("selector") and not (params.get("x") and params.get("y")):
                    logger.warning(f"移除无效的点击操作: {action}")
                    fixed_actions.pop(i)
                    continue

            # 检查是否是无效的输入操作（没有文本或选择器）
            elif action.get("action") == "type_text" and "params" in action:
                params = action["params"]
                if not params.get("text") or not params.get("selector"):
                    logger.warning(f"移除无效的输入操作: {action}")
                    fixed_actions.pop(i)
                    continue

            i += 1

        # 如果操作序列为空，添加默认操作
        if not fixed_actions:
            logger.warning("操作序列为空，添加默认操作")
            if has_launch_app:
                fixed_actions = [
                    {"action": "launch_app", "params": {"packageName": "com.android.settings"}},
                    {"action": "wait", "params": {"milliseconds": 1000}}
                ]

        return fixed_actions

    def _find_better_selector(self, text_value: str, elements: Dict) -> Dict:
        """
        查找匹配给定文本的更好选择器

        Args:
            text_value: 文本值
            elements: 可用的UI元素

        Returns:
            更好的选择器，如果找不到则返回None
        """
        if not text_value or not elements:
            return None

        # 精确匹配
        for elem_id, elem_info in elements.items():
            # 检查文本精确匹配
            if "text" in elem_info and elem_info["text"] == text_value:
                if "selector" in elem_info:
                    return elem_info["selector"]
                else:
                    return {"text": text_value}

            # 检查内容描述精确匹配
            if "contentDescription" in elem_info and elem_info["contentDescription"] == text_value:
                if "selector" in elem_info:
                    return elem_info["selector"]
                else:
                    return {"contentDescription": text_value}

        # 模糊匹配
        best_match = None
        best_match_score = 0

        for elem_id, elem_info in elements.items():
            score = 0

            # 检查文本包含关系
            if "text" in elem_info and elem_info["text"] and text_value in elem_info["text"]:
                score = len(text_value) / len(elem_info["text"]) * 100

            # 检查内容描述包含关系
            elif "contentDescription" in elem_info and elem_info["contentDescription"] and text_value in elem_info[
                "contentDescription"]:
                score = len(text_value) / len(elem_info["contentDescription"]) * 90  # 略低于文本匹配

            # 如果是按钮或可点击元素，增加分数
            if elem_info.get("clickable", False):
                score += 10
            if "type" in elem_info and "button" in elem_info["type"].lower():
                score += 10

            # 更新最佳匹配
            if score > best_match_score:
                if "selector" in elem_info:
                    best_match = elem_info["selector"]
                else:
                    # 创建一个基于最佳属性的选择器
                    if "resourceId" in elem_info and elem_info["resourceId"]:
                        best_match = {"resourceId": elem_info["resourceId"]}
                    elif "text" in elem_info and elem_info["text"]:
                        best_match = {"text": elem_info["text"]}
                    elif "contentDescription" in elem_info and elem_info["contentDescription"]:
                        best_match = {"contentDescription": elem_info["contentDescription"]}
                    elif "bounds" in elem_info and elem_info["bounds"]:
                        best_match = {"bounds": elem_info["bounds"]}

                best_match_score = score

        # 如果找不到任何匹配，返回基于文本的简单选择器
        if not best_match and text_value:
            return {"text": text_value}

        return best_match

    def explain_action_plan(self, action_sequence: List[Dict], user_query: str) -> str:
        """
        向用户解释操作计划
        
        Args:
            action_sequence: 操作序列
            user_query: 原始用户查询
            
        Returns:
            操作计划的自然语言解释
        """
        # 构建系统提示
        system_prompt = """
        你是一个智能助手，负责向用户解释即将执行的操作计划。
        请用简洁、友好的语言解释操作计划，让用户理解系统将要执行的操作。
        不要使用技术术语，而是用日常用语描述操作。
        """

        # 构建用户提示
        user_prompt = f"""
        用户原始指令: {user_query}
        
        系统将执行的操作序列:
        {json.dumps(action_sequence, ensure_ascii=False, indent=2)}
        
        请用自然语言解释这个操作计划，让用户了解系统将要做什么。
        """

        try:
            # 调用DeepSeek模型
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7
            )

            # 获取响应文本
            explanation = response.choices[0].message.content
            logger.info(f"生成操作解释: {explanation}")
            return explanation

        except Exception as e:
            logger.error(f"调用模型解释操作计划时出错: {str(e)}")
            return f"我将尝试执行您的指令: {user_query}"

    def handle_error(self, error: str, user_query: str) -> str:
        """
        处理错误并生成用户友好的错误消息
        
        Args:
            error: 错误信息
            user_query: 原始用户查询
            
        Returns:
            用户友好的错误消息
        """
        # 构建系统提示
        system_prompt = """
        你是一个智能助手，负责将技术错误转化为用户友好的解释。
        请用简洁、友好的语言解释错误，避免使用技术术语，并提供可能的解决方案。
        """

        # 构建用户提示
        user_prompt = f"""
        用户原始指令: {user_query}
        
        系统错误: {error}
        
        请将这个技术错误转化为用户友好的解释，并提供可能的解决方案。
        """

        try:
            # 调用DeepSeek模型
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7
            )

            # 获取响应文本
            friendly_error = response.choices[0].message.content
            logger.info(f"生成友好错误消息: {friendly_error}")
            return friendly_error

        except Exception as e:
            logger.error(f"调用模型处理错误时出错: {str(e)}")
            return f"抱歉，执行您的指令时遇到了问题。请稍后再试或换一种说法。"

    def learn_from_interaction(self, user_query: str, action_sequence: List[Dict], success: bool,
                               feedback: str = None) -> Dict:
        """
        从交互中学习，改进模型理解
        
        Args:
            user_query: 用户查询
            action_sequence: 执行的操作序列
            success: 操作是否成功
            feedback: 用户反馈（可选）
            
        Returns:
            学习结果
        """
        # 这里可以实现更复杂的学习逻辑
        # 当前版本仅记录交互，未来可扩展为更新模型或知识库

        learning_record = {
            "query": user_query,
            "actions": action_sequence,
            "success": success,
            "feedback": feedback,
            "timestamp": self._get_current_time()
        }

        logger.info(f"记录交互学习: {learning_record}")
        return {"status": "recorded", "record": learning_record}

    def _get_current_time(self):
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()

    def _is_follow_up_query(self, current_query: str, previous_queries: List[str]) -> bool:
        """
        判断当前查询是否是前一个查询的后续
        
        Args:
            current_query: 当前用户查询
            previous_queries: 历史查询列表
            
        Returns:
            是否为后续查询
        """
        if not previous_queries:
            return False

        previous_query = previous_queries[-1]

        # 检查是否包含代词或省略关键信息
        follow_up_indicators = ["它", "他", "她", "这个", "那个", "下一个", "上一个", "继续"]

        # 如果查询很短且包含指示词，可能是后续查询
        if len(current_query) < 15 and any(word in current_query for word in follow_up_indicators):
            return True

        # 查询不包含主要动词或对象可能是后续查询
        if not self._contains_main_verb(current_query) or not self._contains_object(current_query):
            return True

        return False

    def _merge_with_previous_intent(self, current_intent: Dict, previous_intent: Dict) -> Dict:
        """
        将当前意图与前一个意图合并
        
        Args:
            current_intent: 当前意图分析结果
            previous_intent: 前一个意图
            
        Returns:
            合并后的意图
        """
        if not previous_intent:
            return current_intent

        merged_intent = current_intent.copy()

        # 如果当前意图缺少app信息但前一个有，则使用前一个的
        if "app" not in merged_intent and "app" in previous_intent:
            merged_intent["app"] = previous_intent["app"]

        # 如果当前意图缺少package_name但前一个有，则使用前一个的
        if "package_name" not in merged_intent and "package_name" in previous_intent:
            merged_intent["package_name"] = previous_intent["package_name"]

        # 合并实体信息
        if "entities" not in merged_intent:
            merged_intent["entities"] = {}

        if "entities" in previous_intent:
            # 当前意图中没有指定的实体，使用前一个意图的
            for entity_type, entity_value in previous_intent["entities"].items():
                if entity_type not in merged_intent["entities"]:
                    merged_intent["entities"][entity_type] = entity_value

        # 添加合并标记
        merged_intent["merged_with_previous"] = True

        return merged_intent

    def _contains_main_verb(self, query: str) -> bool:
        """
        判断查询中是否包含主要动词
        
        Args:
            query: 用户查询
            
        Returns:
            是否包含主要动词
        """
        # 常见的中文动词列表
        common_verbs = ["打开", "关闭", "启动", "停止", "发送", "接收", "查找", "搜索",
                        "播放", "暂停", "创建", "删除", "修改", "更新", "安装", "卸载",
                        "拨打", "接听", "挂断", "拍摄", "录制", "分享", "下载", "上传"]

        # 检查查询中是否包含常见动词
        for verb in common_verbs:
            if verb in query:
                return True

        return False

    def _contains_object(self, query: str) -> bool:
        """
        判断查询中是否包含操作对象
        
        Args:
            query: 用户查询
            
        Returns:
            是否包含操作对象
        """
        # 常见的应用名称和对象类型
        common_objects = ["应用", "软件", "程序", "文件", "图片", "视频", "音乐", "消息",
                          "邮件", "联系人", "电话", "短信", "微信", "支付宝", "淘宝", "QQ",
                          "浏览器", "相机", "地图", "日历", "闹钟", "备忘录", "设置"]

        # 检查查询中是否包含常见对象
        for obj in common_objects:
            if obj in query:
                return True

        # 如果查询长度超过一定值，可能包含自定义对象
        if len(query) > 10:
            return True

        return False

    def get_app_knowledge(self, app_name: str = None, package_name: str = None) -> Dict:
        """
        获取应用知识库
        
        Args:
            app_name: 应用名称
            package_name: 应用包名
            
        Returns:
            应用知识库
        """
        if not self.app_learner:
            return {}

        if package_name:
            return self.app_learner.get_app_knowledge(package_name) or {}

        if app_name:
            package_name = self.app_learner.find_app_by_name(app_name)
            if package_name:
                return self.app_learner.get_app_knowledge(package_name) or {}

        return {}

    def get_optimized_app_elements(self, intent, device_state=None):
        """获取优化后的应用元素信息"""
        app_name = intent.get("app")
        package_name = intent.get("package_name")
        intent_type = intent.get("intent", "").lower()

        # 如果没有包名但有应用名，尝试查找包名
        if not package_name and app_name and self.app_learner:
            package_name = self.app_learner.find_app_by_name(app_name)

        if not package_name:
            return {}

        # 获取应用信息
        app_info = self.app_learner.get_app_info(package_name) or {}
        all_elements = app_info.get("elements", {})

        if not all_elements:
            return {}

        # 应用过滤和精简逻辑
        filtered_elements = self._filter_elements_by_intent(all_elements, intent_type, device_state)
        simplified_elements = self._simplify_elements(filtered_elements)

        return simplified_elements

    def _filter_elements_by_intent(self, elements, intent_type, device_state=None):
        """根据意图类型过滤元素"""
        # 如果元素较少，直接返回全部
        if len(elements) <= 20:
            return elements

        # 根据意图类型定义关键词
        intent_keywords = {
            "calculate": {"数字", "计算", "+", "-", "*", "/", "=", "清除", "等于", "加", "减", "乘", "除"},
            "search": {"搜索", "查询", "输入", "查找"},
            "play_music": {"播放", "歌曲", "音乐", "暂停"},
            "open_app": {"打开", "启动", "运行"}
            # 可以添加更多意图类型
        }

        # 获取当前意图的关键词
        keywords = intent_keywords.get(intent_type, set())

        # 优先级元素：直接匹配关键词的元素
        priority_elements = {}
        for elem_id, elem in elements.items():
            elem_text = str(elem.get("text", "") or "") + " " + str(elem.get("contentDescription", "") or "")
            if any(kw in elem_text for kw in keywords):
                priority_elements[elem_id] = elem

        # 如果找到足够的优先级元素，直接返回
        if len(priority_elements) >= 5:
            return priority_elements

        # 交互性元素：可点击、可输入的元素
        interactive_elements = {}
        for elem_id, elem in elements.items():
            if elem_id not in priority_elements:
                if elem.get("clickable") or elem.get("focusable"):
                    interactive_elements[elem_id] = elem
                    # 限制数量
                    if len(priority_elements) + len(interactive_elements) >= 20:
                        break

        # 合并并返回结果
        return {**priority_elements, **interactive_elements}

    def _simplify_elements(self, elements):
        """精简元素信息，只保留关键属性"""
        simplified = {}

        for elem_id, elem in elements.items():
            simple_elem = {}

            # 只保留这些关键属性
            key_attrs = ["text", "contentDescription", "type", "className", "clickable", "bounds"]
            for attr in key_attrs:
                if attr in elem and elem[attr]:
                    simple_elem[attr] = elem[attr]

            # 确保选择器信息完整
            if "selector" in elem:
                simple_elem["selector"] = elem["selector"]

            simplified[elem_id] = simple_elem

        return simplified

    def _extract_keywords_from_query(self, query):
        """从查询中提取关键词"""
        if not query:
            return set()

        # 简单分词
        words = query.lower().split()

        # 过滤停用词
        stop_words = {"的", "了", "和", "是", "在", "有", "我", "你", "他", "她", "它", "这", "那"}
        keywords = [w for w in words if w and len(w) > 1 and w not in stop_words]

        return set(keywords)
