# 智能旅游规划 Agent 系统

基于 LangGraph 和 MCP 协议的多 Agent 协同旅游规划系统。

## 🌟 核心功能

- **智能规划**: 将复杂旅行需求分解为结构化执行步骤
- **多 Agent 协同**: 父Agent+6个子Agent（交通/地图/天气/酒店/搜索/文件）
- **ReAct 推理**: Think-Act-Observe 循环执行
- **人工介入**: LLM自主判断信息不足并请求用户补充
- **增量优化**: 基于用户反馈智能调整，保留未调整部分
- **智能缓存**: RAG检索历史结果，避免重复MCP调用
- **上下文管理**: 消息压缩算法控制Token消耗

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Redis
- Node.js (用于前端开发)

### 安装

1. 克隆仓库
```bash
git clone https://github.com/juna1624273/trival-agent.git
cd trival-agent
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 配置环境变量
复制 `.env.example` 为 `.env` 并填写必要的API密钥：
```bash
cp .env.example .env
```

4. 启动服务
```bash
# 启动后端
python -m src.main

# 或使用 uvicorn
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

5. 访问应用
打开浏览器访问 http://127.0.0.1:8000/

## 🏗️ 系统架构

### 工作流
Plan → Execute → Replan → 循环，直到完成或需要人工介入

### Agent 架构
- **父Agent**: 总体规划与协调
- **子Agent**:
  - 交通Agent: 航班/火车/公交查询
  - 地图Agent: 地理位置与路线规划
  - 天气Agent: 天气预报与建议
  - 酒店Agent: 住宿推荐与预订
  - 搜索Agent: 通用信息检索
  - 文件Agent: 文档处理与导出

### 技术栈
- **后端**: FastAPI + LangGraph + MCP
- **前端**: HTML5 + CSS3 + JavaScript
- **数据库**: ChromaDB (向量存储) + Redis (缓存)
- **LLM**: 支持 DeepSeek、通义千问、Kimi、OpenAI 等

## 📋 API 文档

启动服务后访问 http://127.0.0.1:8000/docs 查看完整的API文档

## 🔧 配置说明

### 支持的模型
- DeepSeek (V4 Flash/V4 Pro)
- 通义千问 (Plus/Max/Turbo)
- Kimi (8K/32K/128K)
- OpenAI (GPT-4o/GPT-4o Mini)

### MCP 服务
需要配置以下MCP服务（默认运行在本地端口8100-8105）：
- 高德地图MCP
- 铁路12306 MCP
- 航班查询MCP
- 天气查询MCP
- 酒店预订MCP
- 搜索服务MCP

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

- LangGraph: 提供强大的图计算能力
- MCP 协议: 实现Agent间标准化通信
- 各LLM提供商: 提供智能推理能力