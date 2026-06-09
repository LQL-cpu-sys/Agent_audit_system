# 🛡️ Agent Audit System — 多智能体安全审计系统

异构多智能体协作的 AI Agent 安全审计系统，实时检测并拦截针对 AI Agent 的恶意越狱攻击与高危越权操作。采用「意图解析 + 双线审查 + 协调仲裁」的三级流水线架构，支持命令行、Python API、Gradio Web 控制台三种交互方式。

## 架构总览

```
用户输入
   │
   ▼
┌──────────────┐
│  Agent 1     │  意图解析 (InputParser)
│  通义千问 LLM │  提取 action / target / params
└──────┬───────┘
       │
       ├──────────────────┐
       ▼                  ▼
┌──────────────┐  ┌──────────────┐
│  Agent 2     │  │  Agent 3     │
│  越狱检测     │  │  风险评估     │
│  XGBoost +   │  │  规则引擎     │
│  TF-IDF      │  │  + 配置表    │
└──────┬───────┘  └──────┬───────┘
       │                  │
       └────────┬─────────┘
                ▼
       ┌──────────────┐
       │  Agent 4     │
       │  协调仲裁     │
       │  Coordinator │
       └──────┬───────┘
              │
              ▼
    ┌─────────────────┐
    │ allow / reject  │
    │ / manual_review │
    └─────────────────┘
```

## 项目结构

```
Agent_audit_system/
├── main.py                     # 系统入口，AuditSystem 主类
├── agents/
│   ├── input_parser.py         # Agent 1: 通义千问意图解析
│   ├── jailbreak_model.py      # Agent 2: XGBoost 越狱检测器
│   ├── risk_evaluator.py       # Agent 3: 规则引擎风险评估
│   └── coordinator.py          # Agent 4: 协调仲裁决策
├── data/
│   ├── api_risk_config.json    # 风险配置表（动作评级 + 敏感目标黑名单）
│   ├── eval_data_malicious_prompts.csv   # 红方测试集
│   └── eval_data_normal_prompts.csv     # 蓝方测试集
├── scripts/
│   └── evaluate.py             # 自动化评测引擎
├── data_preprocess.py          # 越狱提示词数据集预处理
├── open_data_preprocess/       # 预处理后的数据集及切分
│   └── splits/                 # train / val / test
├── app_ui.py                   # Gradio Web 控制台（浅色主题）
├── app_ui_new.py               # Gradio Web 控制台（优化版）
├── app_ui_black.py             # Gradio Web 控制台（深色主题）
├── test.py                     # 快速功能测试
├── drownload.py                # 安全对齐数据集下载工具
└── utils/
    └── data_preprocess.py      # 数据处理工具
```

## 快速开始

### 环境要求

- Python 3.10+
- 依赖安装：

```bash
pip install numpy scipy scikit-learn xgboost joblib openai gradio pandas tqdm datasets
```

### 1. 配置 API Key

编辑 `agents/input_parser.py`，将 `api_key` 替换为你的阿里云百炼 API Key：

```python
self.client = OpenAI(
    api_key="your-api-key-here",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
```

### 2. 训练越狱检测模型

```bash
cd agents
python jailbreak_model.py
```

训练完成后会在 `agents/` 下生成 `jailbreak_model.pkl`。

### 3. 运行审计系统

```python
from main import AuditSystem

system = AuditSystem()
result = system.run_audit("帮我总结一下工作汇报")
print(result["final_decision"])  # {"decision": "allow", ...}
```

### 4. 启动 Web 控制台

```bash
python app_ui.py        # 浅色主题
python app_ui_new.py    # 优化版
python app_ui_black.py  # 深色主题
```

访问 `http://localhost:7860`。

## 核心模块详解

### Agent 1 — 意图解析 (InputParser)

调用通义千问 (qwen-plus) 将自然语言指令解析为结构化 JSON：

```json
{
  "action": "read_file",
  "target": "/etc/passwd",
  "params": {}
}
```

- 低温推理 (temperature=0.1) 保证输出格式稳定
- 正则兜底容错：LLM 输出非标准 JSON 时自动提取

### Agent 2 — 越狱检测 (JailbreakDetector)

基于 XGBoost + TF-IDF 的轻量级越狱文本分类器：

- **特征提取**：TF-IDF (max_features=10000, ngram_range=(1,2))
- **模型**：XGBoost 二分类，网格搜索调参
- **阈值优化**：在验证集上搜索满足 FPR ≤ 0.5% 的最优阈值
- **攻击类型推断**：基于关键词匹配识别 7 类攻击模式 (Role Play, Token Obfuscation, Constraint Override 等)

### Agent 3 — 风险评估 (RiskEvaluator)

基于规则引擎的行为风险评估：

- **查表评级**：根据解析出的 action 查询预定义风险等级（low / medium / high / critical）
- **敏感目标升级**：若 target 命中敏感黑名单（如 `/etc/passwd`, `password`），自动升级为 critical
- **熔断保护**：解析失败时默认标为 high risk

### Agent 4 — 协调仲裁 (Coordinator)

综合双线审查结果的最终决策引擎，遵循三级裁决逻辑：

| 优先级 | 条件 | 裁决 |
|--------|------|------|
| 1 | 意图解析失败 | `manual_review` （人工审核） |
| 2 | 检测到越狱攻击 | `reject` （一票否决） |
| 3 | 风险等级 high / critical | `reject` |
| 4 | 风险等级 medium | `manual_review` |
| 5 | 其他 | `allow` |

## 评测

```bash
python scripts/evaluate.py
```

自动化评测引擎会分别测试红方（恶意指令拦截率 TPR）和蓝方（正常指令误报率 FPR），生成评测报告：

```
🎯 【红方防御效果】 (越狱攻击拦截率)
   - 攻击样本总数: xxx
   - 成功拦截数量: xxx
   - 👉 最终拦截率: xx.xx%

⚖️ 【蓝方通行效果】 (日常指令误报率)
   - 正常样本总数: xxx
   - 错误拦截数量: xxx
   - 👉 最终误报率: x.xx%
```

## 数据预处理

支持原始格式和 RTPB2026 格式的越狱提示词数据集预处理：

```bash
# 默认处理
python data_preprocess.py

# 处理 RTPB2026 格式
python data_preprocess.py --input open_data/redteam_prompt_benchmark.json --format rtpb2026

# 自定义切分比例
python data_preprocess.py --split 0.8 0.1 0.1
```

预处理流程：加载 → 去重 (精确哈希) → 清洗 → 自动打标签 → 导出 (JSON/CSV/TXT) + 数据集切分 (train/val/test)。

## API

### `AuditSystem.run_audit(raw_user_input: str) -> dict`

```python
{
    "request_id": "req_abc12345",
    "original_input": "...",
    "intermediate_states": {
        "parser_result": {"action": "...", "target": "...", "params": {}, "parse_success": true},
        "jailbreak_result": {"is_jailbreak": false, "confidence": 0.05, "attack_type": "none"},
        "risk_result": {"level": "low", "is_sensitive": false}
    },
    "final_decision": {
        "decision": "allow",        # allow | reject | manual_review
        "risk_level": "low",        # low | medium | high | critical
        "reason": "请求已通过安全审计，允许执行。"
    }
}
```

## 风险配置

编辑 `data/api_risk_config.json` 可自定义规则：

```json
{
  "action_risk_map": {
    "search_web": "low",
    "read_file": "medium",
    "execute_shell_command": "critical"
  },
  "sensitive_targets_regex": [
    "/etc/passwd",
    "/etc/shadow",
    "password"
  ]
}
```

## 安全提醒

- `agents/input_parser.py` 中的 API Key 仅供本地测试使用，提交代码前请移除或替换为环境变量
- 越狱检测模型 (`jailbreak_model.pkl`) 较大，建议通过 `.gitignore` 排除，或使用 Git LFS
- 建议在 `.gitignore` 中添加：

```
__pycache__/
*.pyc
*.pkl
.gradio/
.ipynb_checkpoints/
safety_data/
```

## License

MIT License
