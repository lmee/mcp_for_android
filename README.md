# Android MCP (模型上下文协议) 框架

这是一个创新的Android设备控制和应用自学习框架，基于模型上下文协议（Model Context Protocol，简称MCP）。该框架能够通过自然语言指令控制Android设备，并能自动学习设备上的应用操作方式。

## 项目概述

该框架主要包含以下功能模块：

1. **MCP 核心协议**：定义了设备控制的基本数据结构和操作类型
2. **设备通信接口**：提供与Android设备的TCP通信功能
3. **应用自学习引擎**：能够自动学习和记忆Android应用的UI结构和操作方式
4. **深度应用探索**：提供更深入的应用UI探索和元素检测功能
5. **自然语言理解**：通过AI模型解析用户指令，转化为设备操作序列
6. **HTTP API**：提供RESTful API接口，方便集成到其他系统

## 系统架构

```
                    +----------------+
                    |   HTTP APIs    |
                    +-------+--------+
                            |
          +----------------+v+----------------+
          |        Model Interface           |
          |   (自然语言理解和操作生成)        |
          +----------------+-----------------+
                           |
+------------+  +----------v-----------+  +--------------+
| App Learner |<-|     MCP Context     |->| MCP Protocol |
+------^------+  +----------+-----------+  +--------------+
       |                    |
       |         +----------v-----------+
       +-------->| App Deep Explorer    |
                 +----------------------+
                            |
                  +---------v----------+
                  |    MCP Server      |
                  +---------+----------+
                            |
                  +---------v----------+
                  | Android Device     |
                  +--------------------+
```

## 技术栈

- **后端**：Python, Flask
- **AI模型**：DeepSeek-V3 AI模型
- **通信协议**：自定义TCP协议，HTTP RESTful API
- **存储**：JSON文件（应用知识库）

## 安装要求

- Python 3.8+
- Flask
- OpenAI Python SDK (使用DeepSeek API)
- Android设备或模拟器（需安装配套客户端应用）

## 安装步骤

1. 克隆仓库到本地：

```bash
git clone https://github.com/yourusername/android-mcp-framework.git
cd android-mcp-framework
```

2. 创建并激活虚拟环境：

```bash
python -m venv venv
source venv/bin/activate  # 在Windows上使用: venv\Scripts\activate
```

3. 安装依赖包：

```bash
pip install -r requirements.txt
```

4. 配置API密钥：

在`main.py`中更新DeepSeek AI的API密钥，或设置环境变量：

```bash
export DEEPSEEK_API_KEY="your-api-key-here"
```

## 运行服务器

启动MCP服务器和Flask应用：

```bash
python main.py
```

服务器将在以下端口上运行：
- MCP TCP服务器：8080
- HTTP API服务器：5000

## API 接口说明

### 设备注册

```
POST /register_device
{
    "device_id": "your-device-id",
    "capabilities": ["click", "swipe", "type_text", ...]
}
```

### 执行指令

```
POST /execute
{
    "device_id": "your-device-id",
    "command": "打开微信并发送消息给张三",
    "session_id": "optional-session-id"
}
```

### 学习应用

```
POST /learn_app
{
    "device_id": "your-device-id",
    "package_name": "com.example.app"  // 可选，省略则学习所有应用
}
```

### 文本分析

```
POST /analyze
{
    "text": "打开微信发消息",
    "device_id": "your-device-id"  // 可选
}
```

### 获取系统状态

```
GET /status
```

## 客户端设置

要使用此框架，您需要在Android设备上安装配套的MCP客户端应用。客户端负责：

1. 连接到MCP服务器
2. 接收并执行操作指令
3. 提供设备UI状态信息
4. 支持应用探索和学习

客户端安装步骤将在单独的文档中提供。

## 应用自学习功能

该框架的核心特性之一是能够自动学习设备上的应用操作方式。学习过程包括：

1. **应用发现**：扫描设备上已安装的应用
2. **UI探索**：启动应用并探索其UI结构
3. **元素识别**：识别应用中的关键UI元素（按钮、输入框等）
4. **操作学习**：学习常见操作（搜索、播放、导航等）
5. **知识存储**：将学习到的知识保存到应用知识库

学习完成后，系统能够根据用户的自然语言指令，自动执行对应的应用操作。

## 示例用法

### 1. 使用自然语言控制设备

```python
import requests

api_url = "http://localhost:5000/execute"
data = {
    "device_id": "my-android-phone",
    "command": "打开微信发送'你好'给张三"
}

response = requests.post(api_url, json=data)
print(response.json())
```

### 2. 学习特定应用

```python
import requests

api_url = "http://localhost:5000/learn_app"
data = {
    "device_id": "my-android-phone",
    "package_name": "com.tencent.mm"  # 微信包名
}

response = requests.post(api_url, json=data)
print(response.json())
```

## 深度应用探索

除了基本的应用学习功能外，系统还提供深度应用探索功能，可以：

1. 等待应用完全加载
2. 检测更多类型的UI元素
3. 支持层次化探索，通过点击关键元素访问更多屏幕
4. 生成更完整的应用知识图谱

通过深度探索，系统可以获取更全面的应用知识，提高控制精度。

## 项目结构

```
android-mcp-framework/
├── mcp/
│   ├── mcp_protocol.py     # 协议定义
│   ├── mcp_interface.py    # MCP服务器实现
│   ├── model_interface.py  # 模型接口
│   └── route_handler.py    # API路由处理
├── app_learn/
│   ├── app_learner.py      # 应用学习引擎
│   └── app_deep_explorer.py # 深度探索模块
├── main.py                 # 主程序
├── requirements.txt        # 依赖包列表
└── README.md               # 项目说明
```

## 注意事项

1. 该框架需要配套的Android客户端才能工作
2. 确保Android设备和运行服务器的计算机在同一网络中
3. 某些应用可能有反爬虫或安全机制，可能限制自动化操作
4. 需要有效的DeepSeek AI API密钥
5. 应用知识库会随着学习增长，确保有足够的存储空间

## 待解决的问题
1. 目前应用的学习精准程度还有待于提高
2. 在设置了较多的提示词后，模型的推理速度非常慢

## 贡献指南

欢迎贡献代码或提出问题！请遵循以下步骤：

1. Fork项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建Pull Request

## 许可证

该项目采用MIT许可证 - 详情请参阅LICENSE文件
