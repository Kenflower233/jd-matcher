# 公开部署说明（Streamlit Community Cloud）

本项目可直接部署为公开的 `*.streamlit.app` 网站。公开模式会：

- 要求访客在使用模型功能前确认隐私提示；
- 禁用本地历史，避免不同访客共享服务器上的SQLite记录；
- 限制每个浏览器会话的模型操作次数；
- 限制单个服务进程每天的实际模型请求总数；
- 继续在解析后删除上传文件的临时副本，并默认对常见个人信息脱敏。

## 1. 推送代码

将项目最新代码提交并推送到GitHub。不要提交 `.env` 或
`.streamlit/secrets.toml`；它们已被 `.gitignore` 排除。

## 2. 创建应用

1. 登录 <https://share.streamlit.io>；
2. 点击 **Create app**；
3. 选择GitHub仓库和需要部署的分支；
4. Entrypoint file 填写 `app.py`；
5. Python版本选择与本地一致的受支持版本；
6. 打开 **Advanced settings**，填写下一节的Secrets；
7. 点击 **Deploy**。

## 3. 配置Secrets

在Streamlit Community Cloud的Secrets输入框中填写：

```toml
DEEPSEEK_API_KEY = "替换为你的真实API密钥"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_TIMEOUT = "60"
DEEPSEEK_MAX_RETRIES = "2"

PUBLIC_DEPLOYMENT = "true"
PUBLIC_SESSION_ACTION_LIMIT = "5"
PUBLIC_DAILY_LLM_CALL_LIMIT = "120"
```

API密钥只能填入Secrets后台，不能写入GitHub文件、提交记录、网页文本或截图。

## 4. 设为公开

部署完成后进入应用的 **Settings → Sharing**，选择
**This app is public and searchable**。之后将生成的 `*.streamlit.app`
地址发给其他人即可。

## 5. 额度说明

- `PUBLIC_SESSION_ACTION_LIMIT`：一个浏览器会话可主动点击模型功能的次数；
- `PUBLIC_DAILY_LLM_CALL_LIMIT`：当前服务进程当天可发出的实际模型请求数，
  包括分析、技能提取、改写、面试准备、多岗位比较和失败重试；
- 免费托管服务重启后，进程内的当日计数会重新开始。费用的最终保护仍应在
  模型服务商后台设置余额提醒或账户额度；
- 多岗位比较会为每个岗位分别调用模型，公开部署时建议保持当前最多5个岗位的限制。

## 6. 更新网站

以后将新代码推送到同一GitHub分支，Streamlit Community Cloud会自动重新部署。
如需排错，可在应用右下角打开 **Manage app** 查看Cloud logs。
