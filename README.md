# 实习招聘 JD 匹配分析器

面向所有行业的实习/校招岗位。粘贴或上传招聘 JD 与简历（PDF/DOCX/TXT/MD），自动完成：

- **匹配分析**：匹配度评分、已满足要求、差距清单（每条结论可追溯到 JD/简历原文，疑似幻觉自动标注）
- **逐条要求核对**：区分必须/优先/加分项，展示JD原文、简历证据和匹配状态
- **技能对比**：LLM 抽取技能，Python 集合运算得出"已掌握/待补足"
- **简历改写**：在不编造事实的前提下优化简历措辞，提供前后差异高亮和事实校验
- **结果下载**：下载完整Markdown分析报告、TXT改写稿和可继续编辑的Word简历
- **本地隐私脱敏**：默认隐藏手机号、邮箱、身份证号和带标签地址，模型返回后在本地恢复保留的占位符
- **人工校正与重评分**：修改要求的重要程度、匹配状态和证据，由Python重新计算总分
- **选择性改写**：选择整份简历、项目经历、个人总结或技能部分，并设置保守/标准/深度强度
- **独立重试**：分析、技能提取和简历改写可分别重试，无需重复调用全部步骤
- **多岗位比较**：一次输入或上传最多5个JD，按匹配度排序并展示主要差距与投递建议
- **ATS关键词覆盖**：确定性统计JD技能关键词在简历中的出现情况，不参与综合分数
- **分模块编辑**：按教育、项目、实习、技能等常见标题编辑改写稿，保存后统一用于预览和下载
- **多行业演示**：内置证券研究、软件开发、品牌营销、产品运营和人力资源5组完整合成JD与简历
- **多岗位对比示例**：一键载入同一候选人及5个研究方向岗位，直接体验横向排序
- **本地历史与版本比较**：仅保存评分摘要、要求状态与不可逆指纹，不保存JD或简历原文
- **面试准备**：按需生成项目追问、技能基础、行为经历和差距核实问题，并提示事实边界
- **课程评测面板**：展示6条跨行业合成样例的已验证评分区分度与LLM/Python职责
- **公开部署保护**：云端模式要求隐私确认、禁用共享历史，并提供会话与全站调用额度

匹配总分不是直接采用模型给出的黑盒数字：模型分别判断技能、经验、学历，Python按50%/30%/20%计算总分；JD未要求的维度不参与计算。

## 环境要求

- Python 3.10+
- 一个 LLM API Key（默认 DeepSeek，兼容 OpenAI 接口的其他服务也可用）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key：复制 .env.example 为 .env，填入你的密钥
#    DEEPSEEK_API_KEY=sk-xxxx

# 3. 启动应用（浏览器自动打开 http://localhost:8501）
python -m streamlit run app.py
```

## 运行测试

```bash
pip install pytest
python -m pytest tests/ -v
```

当前离线基线：102个测试通过，覆盖核心逻辑、隐私脱敏、公开部署保护、历史版本、面试准备、多岗位比较、ATS统计、Word导出、评测面板和Streamlit状态保持。

## 发布为公开网站

项目可部署到Streamlit Community Cloud，生成任何人都能打开的
`*.streamlit.app` 地址。公开版需在云端Secrets中设置API密钥和
`PUBLIC_DEPLOYMENT="true"`，不要把密钥写进GitHub。

完整步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 项目结构

```
app.py               # Streamlit 界面入口
src/
  config.py          # 配置加载（.env / 环境变量）
  llm_client.py      # LLM API 客户端（重试/异常处理）
  prompts.py         # 提示词模板
  analyzer.py        # 匹配分析流程
  validator.py       # 输出校验：结构/范围/枚举/防幻觉
  skills.py          # 技能抽取 + 集合运算
  rewriter.py        # 简历改写 + 事实保持校验
  privacy.py         # 本地隐私识别、占位符替换与恢复
  comparison.py      # 多JD解析、岗位结果整理与排序
  ats.py             # ATS关键词覆盖统计
  resume_editor.py   # 简历分模块编辑与Word生成
  demo_data.py       # 多行业及多岗位合成演示数据
  history.py         # SQLite本地摘要历史与版本差异
  interview.py       # 面试问题生成与严格结构校验
  evaluation.py      # 已验证跨行业评测基线读取
  file_parser.py     # PDF/DOCX/TXT 解析
examples/            # 可复制使用的多岗位JD与配套简历示例
tests/               # 102 个 pytest 用例
```

## 切换其他模型

本项目使用 OpenAI 兼容接口，在 `.env` 中可覆盖：

```
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TIMEOUT=60
DEEPSEEK_MAX_RETRIES=2
```

例如改用其他兼容服务，只需替换 BASE_URL 和 MODEL。

## 当前边界

- 深度分析一次处理一个JD；横向比较一次最多处理5个JD，不做用户系统或自动投递。
- 上传文件上限10MB；扫描版PDF暂不支持OCR。
- LLM结果经过结构和业务规则检查，但开放式文本仍可能需要人工核实；界面会展示相应警告。
- 隐私脱敏默认开启；关闭后，原始简历文本会直接发送给配置的模型服务。
- ATS覆盖率只反映关键词是否明确出现，不代表招聘平台的真实筛选结果。
- 本地个人模式的历史数据库位于`data/history.db`并被Git忽略；公开部署模式会禁用历史读写。
- 面试准备是生成式辅助内容，回答仍必须以用户真实经历为准。
