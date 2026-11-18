"""Streamlit界面：粘贴或上传JD和简历，展示分析、技能对比、改写结果。"""
import hashlib
import html
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

import streamlit as st

from src.analyzer import AnalysisError, analyze, compute_requirement_score
from src.ats import analyze_ats_keywords
from src.comparison import (
    MAX_COMPARISON_JOBS,
    JobDescription,
    comparison_row,
    parse_multi_jds,
    rank_comparison_rows,
)
from src.config import load_config, load_deployment_config
from src.demo_data import DEMO_CASES, MULTI_JD_DEMO_RESUME, MULTI_JD_DEMO_TEXT
from src.file_parser import FileParseError, parse_file
from src.evaluation import load_evaluation_summary
from src.history import HistoryStore, compare_history
from src.interview import InterviewPrep, generate_interview_prep
from src.llm_client import LLMClient, LLMError
from src.privacy import redact_personal_info
from src.resume_editor import (
    ResumeSection,
    build_resume_docx,
    parse_resume_sections,
    sections_to_text,
)
from src.rewriter import RewriteOutput, check_facts_preserved, check_new_numbers, rewrite_resume
from src.skills import analyze_skill_gap
from src.validator import check_requirement_evidence

st.set_page_config(page_title="JD匹配分析器", page_icon="🎯", layout="wide")

PROJECT_ROOT = Path(__file__).parent
HISTORY_DB = PROJECT_ROOT / "data" / "history.db"
EVAL_DATASET = PROJECT_ROOT / "tests" / "eval_dataset.jsonl"
EVAL_RESULTS = PROJECT_ROOT / "tests" / "eval_results.json"

try:
    DEPLOYMENT = load_deployment_config()
except RuntimeError as error:
    st.error(f"部署配置错误：{error}")
    st.stop()


def public_actions_remaining() -> int:
    """返回当前浏览器会话剩余的模型操作次数。"""
    used = int(st.session_state.get("public_model_actions_used", 0))
    return max(0, DEPLOYMENT.session_action_limit - used)


def consume_public_action(consent: bool) -> bool:
    """公开版每次用户主动触发模型流程时占用一次会话额度。"""
    if not DEPLOYMENT.public:
        return True
    if not consent:
        st.error("请先确认隐私提示，再使用模型分析功能。")
        return False
    remaining = public_actions_remaining()
    if remaining <= 0:
        st.error("本次浏览器会话的模型操作次数已用完。刷新页面不会恢复全站额度。")
        return False
    st.session_state["public_model_actions_used"] = (
        DEPLOYMENT.session_action_limit - remaining + 1
    )
    return True

st.markdown(
    """
    <style>
    .block-container {max-width: 1240px; padding-top: 1.6rem; padding-bottom: 4rem;}
    .hero {
        width: 100%; box-sizing: border-box;
        padding: 1.25rem 1.4rem; border-radius: 0; margin-bottom: 1.2rem;
        color: inherit; background: transparent;
        border: 1px solid rgba(127, 127, 127, .42);
        box-shadow: none;
    }
    .hero h1 {
        font-size: 1.7rem; font-weight: 700; margin: 0 0 .4rem 0;
        letter-spacing: -.02em;
    }
    .hero p {margin: 0; opacity: .72; font-size: .95rem; line-height: 1.6;}
    .section-label {font-size: .78rem; font-weight: 700; letter-spacing: .08em; color: #147d7e; text-transform: uppercase;}
    div[data-testid="stMetric"] {
        background: rgba(20,125,126,.10); border: 1px solid rgba(20,125,126,.24);
        padding: .85rem 1rem; border-radius: 16px;
    }
    .diff-panel {
        min-height: 260px; max-height: 520px; overflow-y: auto; white-space: pre-wrap;
        padding: 1rem 1.05rem; border-radius: 14px; border: 1px solid rgba(49,74,91,.16);
        background: rgba(249,251,252,.92); color: #1f2937;
        line-height: 1.72; font-size: .92rem;
    }
    .diff-delete {background: #ffe5e2; color: #9e2a24; text-decoration: line-through; border-radius: 3px;}
    .diff-insert {background: #dcf7ea; color: #126342; border-radius: 3px;}
    .skill-pill {
        display: inline-block; padding: .32rem .62rem; margin: .18rem .18rem .18rem 0;
        border-radius: 999px; font-size: .86rem; font-weight: 600;
    }
    .skill-match {background: #dcf7ea; color: #126342;}
    .skill-missing {background: #fff0d9; color: #8a4f08;}
    </style>
    <div class="hero">
      <h1>JD × 简历匹配工作台</h1>
      <p>逐条核对岗位要求，解释评分依据，识别技能差距，并真实适当地优化简历。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("使用流程")
    st.markdown("1. 输入或上传 JD\n2. 输入或上传简历\n3. 开始分析\n4. 核对证据并下载报告")
    st.divider()
    st.caption("多行业演示")
    demo_name = st.selectbox(
        "选择行业示例",
        ["请选择"] + list(DEMO_CASES),
        help="每组均包含结构完整的合成JD和简历，不包含真实个人信息或有效投递方式。",
        key="demo_case",
    )
    if st.button(
        "加载示例",
        disabled=demo_name == "请选择",
        width="stretch",
        key="load_demo",
    ):
        st.session_state["jd"] = DEMO_CASES[demo_name]["jd"]
        st.session_state["resume"] = DEMO_CASES[demo_name]["resume"]
        st.session_state.pop("analysis_bundle", None)
        st.session_state.pop("multi_comparison", None)
        st.rerun()
    if st.button("加载多岗位对比示例", width="stretch", key="load_multi_demo"):
        st.session_state["jd"] = ""
        st.session_state["resume"] = MULTI_JD_DEMO_RESUME
        st.session_state["multi_jd_text"] = MULTI_JD_DEMO_TEXT
        st.session_state["expand_multi_demo"] = True
        st.session_state.pop("analysis_bundle", None)
        st.session_state.pop("multi_comparison", None)
        st.rerun()
    st.divider()
    st.caption("辅助工具")
    if DEPLOYMENT.public:
        st.caption("公开演示版不会保存或共享任何人的分析历史。")
    else:
        history_button_label = (
            "关闭本地历史" if st.session_state.get("show_history", False)
            else "本地历史与版本比较"
        )
        if st.button(history_button_label, width="stretch", key="toggle_history"):
            st.session_state["show_history"] = not st.session_state.get("show_history", False)
            st.rerun()
    if st.button("课程展示与评测面板", width="stretch", key="toggle_course_panel"):
        st.session_state["show_course_panel"] = not st.session_state.get(
            "show_course_panel", False
        )
        st.rerun()
    st.divider()
    st.caption("隐私提示")
    st.caption(
        "上传文件解析后会删除临时副本；文本会发送至当前配置的模型服务完成分析。"
        "建议移除身份证号、住址等无关敏感信息。"
    )


def load_text(label: str, key: str) -> str:
    """文本框 + 文件上传二选一，上传优先。"""
    text = st.text_area(label, height=180, key=key)
    uploaded = st.file_uploader(
        f"或上传文件（txt/md/pdf/docx）",
        type=["txt", "md", "pdf", "docx"],
        key=f"{key}_file",
        max_upload_size=10,
    )
    if uploaded is not None:
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        try:
            text = parse_file(tmp_path)
            st.success(f"已从 {uploaded.name} 提取 {len(text)} 字")
        except FileParseError as e:
            st.error(str(e))
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return text


def parse_uploaded_text(uploaded) -> str:
    """解析一个Streamlit上传对象，并始终删除临时文件。"""
    suffix = Path(uploaded.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name
    try:
        return parse_file(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def build_diff_html(original: str, rewritten: str) -> tuple[str, str]:
    """生成安全的字符级前后对照HTML，适配无空格的中文文本。"""
    left: list[str] = []
    right: list[str] = []
    matcher = SequenceMatcher(None, original, rewritten)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old = html.escape(original[i1:i2])
        new = html.escape(rewritten[j1:j2])
        if tag == "equal":
            left.append(old)
            right.append(new)
        elif tag == "delete":
            left.append(f'<span class="diff-delete">{old}</span>')
        elif tag == "insert":
            right.append(f'<span class="diff-insert">{new}</span>')
        else:
            left.append(f'<span class="diff-delete">{old}</span>')
            right.append(f'<span class="diff-insert">{new}</span>')
    return "".join(left), "".join(right)


def render_pills(items: list[str], style: str, empty_text: str) -> None:
    if not items:
        st.caption(empty_text)
        return
    pills = "".join(
        f'<span class="skill-pill {style}">{html.escape(item)}</span>'
        for item in items
    )
    st.markdown(pills, unsafe_allow_html=True)


def build_report(
    result,
    gap,
    rewrite,
    requirements: list[dict] | None = None,
    score: int | None = None,
    extra_warnings: list[str] | None = None,
    interview: InterviewPrep | None = None,
) -> str:
    """构造可下载的Markdown分析报告。"""
    requirements = requirements or result.requirements
    score = result.score if score is None else score
    labels = {
        "skills": "技能",
        "experience": "经验",
        "education": "学历",
    }
    lines = ["# JD × 简历匹配报告", "", f"## 总分：{score} / 100", "", "### 评分维度", ""]
    if score != result.score:
        lines.insert(3, f"> 模型初始总分：{result.score} / 100；当前分数来自人工修正后的要求表。")
    for name, label in labels.items():
        value = result.score_breakdown.get(name)
        score = "不适用" if value is None else f"{value} / 100"
        lines.append(f"- **{label}**：{score} — {result.score_reasons.get(name, '')}")

    lines.extend(["", "## 逐条要求核对", "", "| JD要求 | 重要程度 | 状态 | JD依据 | 简历依据 |", "|---|---|---|---|---|"])
    importance = {"required": "必须", "preferred": "优先", "bonus": "加分"}
    statuses = {"matched": "已匹配", "partial": "部分匹配", "missing": "缺失"}
    for item in requirements:
        values = [
            item["requirement"],
            importance[item["importance"]],
            statuses[item["status"]],
            item["jd_evidence"],
            item.get("resume_evidence") or "—",
        ]
        safe_values = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(safe_values) + " |")

    lines.extend(["", "## 修改建议", ""])
    lines.extend(f"- {item}" for item in result.suggestions)
    if gap is not None:
        lines.extend(["", "## 技能集合对比", "", f"- 已掌握：{'、'.join(gap.matched) or '无'}", f"- 待补足：{'、'.join(gap.missing) or '无'}"])
    warnings = list(result.warnings) + list(extra_warnings or [])
    if rewrite is not None:
        warnings.extend(rewrite.warnings)
        lines.extend(["", "## 改写后的简历", "", rewrite.rewritten])
    if warnings:
        lines.extend(["", "## 人工核实提醒", ""])
        lines.extend(f"- {warning}" for warning in warnings)
    if interview is not None:
        lines.extend(["", "## 面试准备", ""])
        for index, question in enumerate(interview.questions, start=1):
            lines.extend(
                [
                    f"### {index}. [{question.category}] {question.question}",
                    "",
                    f"- **提问原因**：{question.why}",
                    f"- **回答框架**：{question.answer_framework}",
                    f"- **事实提醒**：{question.caution}",
                    "",
                ]
            )
    return "\n".join(lines)


def render_course_panel() -> None:
    """展示已验证的合成评测基线，不产生新的模型调用。"""
    summary = load_evaluation_summary(EVAL_DATASET, EVAL_RESULTS)
    st.markdown('<div class="section-label">课程展示 · 跨行业评测</div>', unsafe_allow_html=True)
    st.caption("以下为2026-11-16使用完全合成数据完成的已验证基线，不是当前输入的实时结果。")
    columns = st.columns(4)
    columns[0].metric("评测样例", len(summary.rows))
    columns[1].metric("Schema合格率", f"{summary.schema_success_rate}%")
    columns[2].metric("匹配组均分", summary.matched_average)
    columns[3].metric("组间分差", f"{summary.separation:+.2f}")
    st.dataframe(summary.rows, hide_index=True, width="stretch")
    role_col1, role_col2 = st.columns(2)
    with role_col1:
        st.markdown("**LLM负责**")
        st.markdown("- 语义拆解岗位要求\n- 判断维度匹配\n- 抽取技能与生成文本")
    with role_col2:
        st.markdown("**Python负责**")
        st.markdown("- 固定权重计算总分\n- Schema与事实校验\n- 集合运算、排序和关键词统计")
    st.caption("需要实时复评时，可在终端运行：python -m scripts.evaluate_live")


def render_history_panel() -> None:
    """显示本地摘要历史与两个版本之间的变化。"""
    st.markdown('<div class="section-label">本地历史 · 版本比较</div>', unsafe_allow_html=True)
    st.info("历史数据库仅保存岗位名称、分数、要求状态、差距摘要和不可逆指纹；不保存JD、简历、联系方式或上传文件原文。")
    store = HistoryStore(HISTORY_DB)
    records = store.list()
    if not records:
        st.caption("还没有本地历史。完成一次分析后，点击“保存摘要到本地历史”。")
        return
    st.dataframe(
        [
            {
                "编号": record.id,
                "时间": record.created_at.replace("T", " "),
                "岗位": record.job_title,
                "分数": record.score,
                "匹配要求": f"{record.matched_count}/{record.total_requirements}",
                "技能覆盖": "—" if record.skill_coverage is None else f"{record.skill_coverage}%",
                "差距数": len(record.missing),
            }
            for record in records
        ],
        hide_index=True,
        width="stretch",
    )
    labels = {
        record.id: f"#{record.id} · {record.job_title} · {record.score}分 · {record.created_at[5:16].replace('T', ' ')}"
        for record in records
    }
    if len(records) >= 2:
        compare_col1, compare_col2 = st.columns(2)
        older_id = compare_col1.selectbox(
            "较早版本",
            [record.id for record in records],
            index=1,
            format_func=labels.get,
            key="history_older",
        )
        newer_id = compare_col2.selectbox(
            "较新版本",
            [record.id for record in records],
            index=0,
            format_func=labels.get,
            key="history_newer",
        )
        if older_id == newer_id:
            st.warning("请选择两个不同版本进行比较。")
        else:
            by_id = {record.id: record for record in records}
            comparison = compare_history(by_id[older_id], by_id[newer_id])
            compare_metrics = st.columns(3)
            compare_metrics[0].metric("分数变化", f"{comparison.score_delta:+d}")
            compare_metrics[1].metric("已解决差距", len(comparison.resolved_gaps))
            compare_metrics[2].metric("新增差距", len(comparison.new_gaps))
            st.write("**已解决：**", "、".join(comparison.resolved_gaps) or "无")
            st.write("**要求状态改善：**", "、".join(comparison.improved_requirements) or "无")
            st.write("**新增差距：**", "、".join(comparison.new_gaps) or "无")
    with st.expander("删除一条历史记录"):
        delete_id = st.selectbox(
            "选择记录",
            [record.id for record in records],
            format_func=labels.get,
            key="history_delete_id",
        )
        confirm_delete = st.checkbox("确认删除所选记录；该操作无法撤销", key="history_delete_confirm")
        if st.button(
            "删除所选记录",
            disabled=not confirm_delete,
            key="delete_history_record",
        ):
            store.delete(delete_id)
            st.rerun()


if not DEPLOYMENT.public and st.session_state.get("show_history"):
    render_history_panel()
    st.divider()

if st.session_state.get("show_course_panel"):
    render_course_panel()
    st.divider()


st.markdown('<div class="section-label">01 · 输入材料</div>', unsafe_allow_html=True)
input_col1, input_col2 = st.columns(2, gap="large")
with input_col1:
    jd_text = load_text("职位描述（JD）", "jd")
with input_col2:
    resume_text = load_text("你的简历", "resume")

privacy_enabled = st.toggle(
    "分析前在本地隐藏手机号、邮箱、身份证号和带标签的详细地址",
    value=True,
    help="脱敏占位符会发送给模型；生成改写稿后，程序会在本地恢复模型保留的占位符。",
)

if DEPLOYMENT.public:
    st.info(
        "公开演示版不会保存JD、简历或分析历史。点击模型功能后，脱敏后的输入仍会发送至"
        "当前配置的模型服务；请先删除身份证号、详细住址等与求职无关的信息。"
    )
    public_privacy_consent = st.checkbox(
        "我已阅读隐私提示，并同意将当前JD和简历内容发送至模型服务进行分析",
        key="public_privacy_consent",
    )
    st.caption(
        f"本次浏览器会话还可主动触发 {public_actions_remaining()} 次模型操作；"
        "多岗位比较会按岗位数量产生多次模型调用。"
    )
else:
    public_privacy_consent = True

privacy_result = redact_personal_info(resume_text) if privacy_enabled else None
model_resume_text = privacy_result.text if privacy_result else resume_text
privacy_replacements = privacy_result.replacements if privacy_result else {}

if privacy_enabled:
    if privacy_result and privacy_result.total:
        summary = "、".join(
            f"{label}{count}处" for label, count in privacy_result.counts.items()
        )
        st.success(f"已在本地识别并隐藏：{summary}。原文不会写入项目文件。")
        with st.expander("预览将发送给模型的脱敏简历"):
            st.code(model_resume_text, language=None)
    else:
        st.caption("未识别到需要隐藏的手机号、邮箱、身份证号或带标签详细地址。")

input_signature = hashlib.sha256(
    f"{jd_text}\0{resume_text}\0{privacy_enabled}".encode()
).hexdigest()

previous = st.session_state.get("analysis_bundle")
if previous and previous["signature"] != input_signature:
    st.session_state.pop("analysis_bundle", None)
    previous = None

public_model_action_disabled = DEPLOYMENT.public and (
    not public_privacy_consent or public_actions_remaining() <= 0
)

action_col, hint_col = st.columns([1, 3], vertical_alignment="center")
with action_col:
    start_analysis = st.button(
        "开始分析",
        type="primary",
        disabled=(
            not jd_text.strip()
            or not resume_text.strip()
            or public_model_action_disabled
        ),
        width="stretch",
        key="start_analysis",
    )
with hint_col:
    st.caption("分析通常需要数秒，并会依次完成匹配判断、技能集合运算和简历改写。")

with st.expander(
    "多岗位横向比较（最多5个JD）",
    expanded=st.session_state.pop("expand_multi_demo", False),
):
    st.caption(
        "每个岗位用单独一行“---”分隔；可在每段首行写“岗位：岗位名称”。"
        "也可以一次上传多个JD文件。比较仅调用匹配分析，不自动生成多份改写稿。"
    )
    multi_jd_text = st.text_area(
        "多个职位描述",
        height=180,
        placeholder=(
            "岗位：数据分析实习生\n要求Python、SQL和数据分析项目经验\n"
            "---\n岗位：产品运营实习生\n要求用户调研和数据复盘能力"
        ),
        key="multi_jd_text",
    )
    multi_jd_files = st.file_uploader(
        "或批量上传JD文件（txt/md/pdf/docx）",
        type=["txt", "md", "pdf", "docx"],
        accept_multiple_files=True,
        key="multi_jd_files",
        max_upload_size=10,
    )
    compare_jobs = st.button(
        "开始多岗位比较",
        disabled=(
            not resume_text.strip()
            or (not multi_jd_text.strip() and not multi_jd_files)
            or public_model_action_disabled
        ),
        key="compare_jobs",
    )

if start_analysis:
    start_analysis = consume_public_action(public_privacy_consent)
if compare_jobs:
    compare_jobs = consume_public_action(public_privacy_consent)

multi_jobs: list[JobDescription] = []
multi_input_errors: list[str] = []
try:
    multi_jobs.extend(parse_multi_jds(multi_jd_text))
except ValueError as error:
    multi_input_errors.append(str(error))
for uploaded in multi_jd_files:
    try:
        multi_jobs.append(
            JobDescription(title=Path(uploaded.name).stem[:40], text=parse_uploaded_text(uploaded))
        )
    except FileParseError as error:
        multi_input_errors.append(f"{uploaded.name}：{error}")
if len(multi_jobs) > MAX_COMPARISON_JOBS:
    multi_input_errors.append(f"一次最多比较 {MAX_COMPARISON_JOBS} 个岗位")

multi_signature = hashlib.sha256(
    ("\0".join(f"{job.title}\0{job.text}" for job in multi_jobs) + f"\0{resume_text}\0{privacy_enabled}").encode()
).hexdigest()

if compare_jobs:
    if multi_input_errors:
        for error in multi_input_errors:
            st.error(error)
    elif not multi_jobs:
        st.error("请至少输入或上传一个用于比较的JD")
    else:
        comparison_rows: list[dict] = []
        comparison_errors: list[str] = []
        progress = st.status("正在比较多个岗位…", expanded=True)
        try:
            client = LLMClient(load_config())
            for index, job in enumerate(multi_jobs, start=1):
                progress.write(f"正在分析 {index}/{len(multi_jobs)}：{job.title}")
                try:
                    job_result = analyze(job.text, model_resume_text, client)
                    comparison_rows.append(comparison_row(job.title, job_result))
                except AnalysisError as error:
                    comparison_errors.append(f"{job.title}：{error}")
        except (RuntimeError, LLMError) as error:
            comparison_errors.append(str(error))
        state = "complete" if comparison_rows else "error"
        progress.update(label="岗位比较完成" if comparison_rows else "岗位比较未完成", state=state, expanded=False)
        st.session_state["multi_comparison"] = {
            "signature": multi_signature,
            "rows": rank_comparison_rows(comparison_rows),
            "errors": comparison_errors,
        }

multi_comparison = st.session_state.get("multi_comparison")
if multi_comparison and multi_comparison["signature"] == multi_signature:
    st.markdown('<div class="section-label">多岗位比较结果</div>', unsafe_allow_html=True)
    if multi_comparison["rows"]:
        best_job = multi_comparison["rows"][0]
        st.success(f"当前最匹配：{best_job['岗位']}（{best_job['匹配度']} / 100）")
        st.dataframe(
            multi_comparison["rows"],
            hide_index=True,
            width="stretch",
            column_config={
                "匹配度": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
            },
        )
    for error in multi_comparison["errors"]:
        st.warning(error)

if start_analysis:
    bundle = {
        "signature": input_signature,
        "analysis": None,
        "gap": None,
        "rewrite": None,
        "interview": None,
        "errors": {},
        "privacy_enabled": privacy_enabled,
    }
    progress = st.status("正在分析…", expanded=True)
    try:
        progress.write("正在连接模型服务")
        client = LLMClient(load_config())
    except (RuntimeError, LLMError) as e:
        bundle["errors"]["analysis"] = str(e)
        progress.update(label="分析未完成", state="error")
    else:
        progress.write("正在逐条核对岗位要求并计算评分")
        try:
            bundle["analysis"] = analyze(jd_text, model_resume_text, client)
        except AnalysisError as e:
            bundle["errors"]["analysis"] = str(e)

        if bundle["analysis"] is not None:
            progress.write("正在提取技能并执行集合运算")
            try:
                bundle["gap"] = analyze_skill_gap(jd_text, model_resume_text, client)
            except AnalysisError as e:
                bundle["errors"]["gap"] = str(e)

            progress.write("正在生成事实受约束的简历改写稿")
            try:
                bundle["rewrite"] = rewrite_resume(
                    model_resume_text,
                    bundle["analysis"].missing,
                    client,
                    original_resume_text=resume_text if privacy_enabled else None,
                    privacy_replacements=privacy_replacements,
                )
            except AnalysisError as e:
                bundle["errors"]["rewrite"] = str(e)
            progress.update(label="分析完成", state="complete", expanded=False)
        else:
            progress.update(label="分析未完成", state="error")

    st.session_state["analysis_bundle"] = bundle
    previous = bundle

if previous:
    errors = previous["errors"]
    result = previous["analysis"]
    gap = previous["gap"]
    rewrite = previous["rewrite"]
    interview = previous.get("interview")
    delivery_rewrite: RewriteOutput | None = None
    if rewrite is not None:
        delivery_rewrite = RewriteOutput(
            rewritten=previous.get("edited_resume", rewrite.rewritten),
            warnings=list(rewrite.warnings) + list(previous.get("edit_warnings", [])),
        )

    if result is None:
        st.error(errors.get("analysis", "分析未完成，请重试"))
        if st.button(
            "仅重试匹配分析",
            type="primary",
            key="retry_analysis",
            disabled=public_model_action_disabled,
        ) and consume_public_action(public_privacy_consent):
            try:
                client = LLMClient(load_config())
                previous["analysis"] = analyze(jd_text, model_resume_text, client)
                previous["errors"].pop("analysis", None)
            except (AnalysisError, RuntimeError, LLMError) as error:
                previous["errors"]["analysis"] = str(error)
            st.session_state["analysis_bundle"] = previous
            st.rerun()
    else:
        st.divider()
        st.markdown('<div class="section-label">02 · 分析结果</div>', unsafe_allow_html=True)

        active_requirements = previous.get("manual_requirements") or result.requirements
        active_missing_requirements = [
            item["requirement"]
            for item in active_requirements
            if item["status"] in {"partial", "missing"}
        ]
        display_score = previous.get("manual_score", result.score)
        manual_warnings = previous.get("manual_warnings", [])
        matched_count = sum(item["status"] == "matched" for item in active_requirements)
        warning_count = (
            len(result.warnings)
            + len(manual_warnings)
            + (len(rewrite.warnings) if rewrite else 0)
        )
        skill_ratio = "—"
        if gap is not None and gap.jd_skills:
            skill_ratio = f"{len(gap.matched)} / {len(gap.jd_skills)}"

        overview = st.columns(4)
        score_delta = None
        if "manual_score" in previous:
            difference = display_score - result.score
            score_delta = f"{difference:+d} 人工调整"
        overview[0].metric("综合匹配度", f"{display_score} / 100", delta=score_delta)
        overview[1].metric("明确匹配要求", f"{matched_count} / {len(active_requirements)}")
        overview[2].metric("技能集合匹配", skill_ratio)
        overview[3].metric("需要人工核实", warning_count)

        if "manual_score" in previous:
            st.caption("当前总分根据人工修正后的要求状态与重要程度重新计算；原始模型分数仍保留在评分依据中。")
        else:
            st.caption("总分由 Python 按固定权重计算：技能50%、经验30%、学历20%；JD未要求的维度不计入。")

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
            [
                "📌 结果概览",
                "🧾 要求核对",
                "🧩 技能差距",
                "🔎 ATS关键词",
                "🎤 面试准备",
                "✍️ 改写对照",
            ]
        )

        with tab1:
            st.subheader("评分依据")
            if "manual_score" in previous:
                st.info(
                    f"模型初始总分为 {result.score}；人工调整后为 {display_score}。"
                    "重评分按技能50%、经验30%、学历20%、其他10%的类别权重，"
                    "并结合必须/优先/加分与匹配/部分匹配/缺失计算。"
                )
            labels = {"skills": "技能", "experience": "经验", "education": "学历"}
            columns = st.columns(3)
            for column, (name, label) in zip(columns, labels.items()):
                value = result.score_breakdown.get(name)
                column.metric(label, "不适用" if value is None else f"{value} / 100")
                column.caption(result.score_reasons.get(name, ""))

            st.subheader("优先修改建议")
            for index, item in enumerate(result.suggestions, start=1):
                st.markdown(f"**{index}.** {item}")

            if result.warnings:
                st.subheader("需要人工核实")
                for warning in result.warnings:
                    st.warning(warning)
            for warning in manual_warnings:
                st.warning(warning)

        with tab2:
            importance_labels = {"required": "必须", "preferred": "优先", "bonus": "加分"}
            status_labels = {"matched": "已匹配", "partial": "部分匹配", "missing": "缺失"}
            category_labels = {"skill": "技能", "experience": "经验", "education": "学历", "other": "其他"}
            rows = [
                {
                    "JD要求": item["requirement"],
                    "类型": category_labels[item["category"]],
                    "重要程度": importance_labels[item["importance"]],
                    "匹配状态": status_labels[item["status"]],
                    "JD原文依据": item["jd_evidence"],
                    "简历原文依据": item.get("resume_evidence") or "—",
                }
                for item in active_requirements
            ]
            st.caption("可以修正重要程度、匹配状态和简历证据；点击“应用并重新评分”后由Python重新计算总分。")
            editor_revision = previous.get("editor_revision", 0)
            edited_rows = st.data_editor(
                rows,
                width="stretch",
                hide_index=True,
                key=f"requirements_editor_{input_signature}_{editor_revision}",
                disabled=["JD要求", "类型", "JD原文依据"],
                column_config={
                    "重要程度": st.column_config.SelectboxColumn(
                        options=["必须", "优先", "加分"], required=True
                    ),
                    "匹配状态": st.column_config.SelectboxColumn(
                        options=["已匹配", "部分匹配", "缺失"], required=True
                    ),
                    "简历原文依据": st.column_config.TextColumn(
                        help="已匹配或部分匹配时，应填写可在简历中找到的原文短句。"
                    ),
                },
            )

            apply_col, reset_col = st.columns(2)
            if apply_col.button("应用修改并重新评分", width="stretch"):
                importance_values = {value: key for key, value in importance_labels.items()}
                status_values = {value: key for key, value in status_labels.items()}
                records = (
                    edited_rows.to_dict("records")
                    if hasattr(edited_rows, "to_dict")
                    else edited_rows
                )
                updated_requirements: list[dict] = []
                validation_error = None
                for original, row in zip(active_requirements, records):
                    item = dict(original)
                    item["importance"] = importance_values[row["重要程度"]]
                    item["status"] = status_values[row["匹配状态"]]
                    evidence = str(row["简历原文依据"]).strip()
                    if evidence == "—":
                        evidence = ""
                    if item["status"] in {"matched", "partial"} and not evidence:
                        validation_error = f"“{item['requirement']}”标为匹配时必须填写简历证据。"
                        break
                    item["resume_evidence"] = evidence or None
                    if item["status"] == "missing":
                        item["resume_evidence"] = None
                    updated_requirements.append(item)

                if validation_error:
                    st.error(validation_error)
                else:
                    previous["manual_requirements"] = updated_requirements
                    previous["manual_score"] = compute_requirement_score(updated_requirements)
                    previous["manual_warnings"] = check_requirement_evidence(
                        updated_requirements,
                        jd_text,
                        resume_text + "\n" + model_resume_text,
                    )
                    previous["rewrite"] = None
                    previous["interview"] = None
                    previous["errors"]["rewrite"] = "要求状态已调整，请按当前设置重新生成改写稿。"
                    previous["errors"].pop("interview", None)
                    previous["editor_revision"] = editor_revision + 1
                    st.session_state["analysis_bundle"] = previous
                    st.rerun()

            if reset_col.button(
                "恢复模型初始判断",
                disabled="manual_requirements" not in previous,
                width="stretch",
            ):
                previous.pop("manual_requirements", None)
                previous.pop("manual_score", None)
                previous.pop("manual_warnings", None)
                previous["rewrite"] = None
                previous["interview"] = None
                previous["errors"]["rewrite"] = "要求状态已恢复，请重新生成改写稿。"
                previous["errors"].pop("interview", None)
                previous["editor_revision"] = editor_revision + 1
                st.session_state["analysis_bundle"] = previous
                st.rerun()

        with tab3:
            if gap is None:
                st.error(errors.get("gap", "技能对比未完成，请重试"))
                retry_gap_label = "仅重试技能提取"
            else:
                retry_gap_label = "重新提取技能"
                st.info("LLM只负责抽取技能；匹配与缺失由Python执行归一化后的集合交集和差集。")
                skill_col1, skill_col2 = st.columns(2, gap="large")
                with skill_col1:
                    st.subheader("已掌握")
                    render_pills(gap.matched, "skill-match", "未识别到交集技能")
                with skill_col2:
                    st.subheader("待补足")
                    render_pills(gap.missing, "skill-missing", "未识别到缺失技能")
                with st.expander("查看完整技能抽取结果"):
                    st.write("**JD技能：**", gap.jd_skills)
                    st.write("**简历技能：**", gap.resume_skills)
            if st.button(
                retry_gap_label,
                key="retry_skill_gap",
                disabled=public_model_action_disabled,
            ) and consume_public_action(public_privacy_consent):
                try:
                    client = LLMClient(load_config())
                    previous["gap"] = analyze_skill_gap(
                        jd_text, model_resume_text, client
                    )
                    previous["errors"].pop("gap", None)
                except (AnalysisError, RuntimeError, LLMError) as error:
                    previous["errors"]["gap"] = str(error)
                st.session_state["analysis_bundle"] = previous
                st.rerun()

        with tab4:
            st.info(
                "ATS覆盖仅统计JD技能关键词是否在简历中明确出现，用于检查表达完整性；"
                "它不参与综合匹配分数，也不建议为了覆盖率机械堆砌关键词。"
            )
            if gap is None:
                st.error("技能提取完成后才能生成ATS关键词覆盖结果。")
            else:
                ats_report = analyze_ats_keywords(gap.jd_skills, resume_text)
                ats_columns = st.columns(3)
                ats_columns[0].metric("关键词覆盖率", f"{ats_report.coverage}%")
                ats_columns[1].metric("已覆盖", f"{ats_report.covered_count} / {ats_report.total}")
                ats_columns[2].metric("待补充", len(ats_report.missing))
                keyword_rows = [
                    {
                        "关键词": item.keyword,
                        "状态": "已覆盖" if item.covered else "未出现",
                        "出现次数": item.occurrences,
                        "建议": (
                            "保持自然表达"
                            if item.covered
                            else "仅在确有相关经历时补充"
                        ),
                    }
                    for item in ats_report.keywords
                ]
                if keyword_rows:
                    st.dataframe(keyword_rows, hide_index=True, width="stretch")
                else:
                    st.caption("当前JD未抽取到可统计的技能关键词。")

        with tab5:
            st.info(
                "面试问题按当前JD、简历和差距清单生成。回答框架只能引用已有事实；"
                "简历没有依据的内容应在面试中如实说明。"
            )
            interview_button_label = (
                "生成面试准备清单" if interview is None else "重新生成面试准备清单"
            )
            if st.button(
                interview_button_label,
                key="generate_interview",
                type="primary" if interview is None else "secondary",
                disabled=public_model_action_disabled,
            ) and consume_public_action(public_privacy_consent):
                with st.spinner("正在生成针对性面试问题…"):
                    try:
                        client = LLMClient(load_config())
                        previous["interview"] = generate_interview_prep(
                            jd_text,
                            model_resume_text,
                            active_missing_requirements,
                            client,
                        )
                        previous["errors"].pop("interview", None)
                    except (AnalysisError, RuntimeError, LLMError) as error:
                        previous["errors"]["interview"] = str(error)
                st.session_state["analysis_bundle"] = previous
                st.rerun()
            if interview is None:
                if errors.get("interview"):
                    st.error(errors["interview"])
                else:
                    st.caption("此步骤按需运行，不会随匹配分析自动增加模型调用。")
            else:
                for index, question in enumerate(interview.questions, start=1):
                    with st.expander(
                        f"{index}. [{question.category}] {question.question}",
                        expanded=index == 1,
                    ):
                        st.markdown(f"**为什么可能会问**：{question.why}")
                        st.markdown(f"**回答框架**：{question.answer_framework}")
                        st.warning(question.caution)

        with tab6:
            option_col1, option_col2 = st.columns(2)
            rewrite_scope = option_col1.selectbox(
                "改写范围",
                ["整份简历", "项目经历", "个人总结", "技能部分"],
                key=f"rewrite_scope_{input_signature}",
            )
            rewrite_intensity = option_col2.selectbox(
                "改写强度",
                ["保守", "标准", "深度"],
                index=1,
                key=f"rewrite_intensity_{input_signature}",
            )
            rewrite_button_label = (
                "仅重试简历改写" if rewrite is None else "按当前范围和强度重新改写"
            )
            if st.button(
                rewrite_button_label,
                type="primary" if rewrite is None else "secondary",
                key="retry_rewrite",
                disabled=public_model_action_disabled,
            ) and consume_public_action(public_privacy_consent):
                try:
                    client = LLMClient(load_config())
                    previous["rewrite"] = rewrite_resume(
                        model_resume_text,
                        active_missing_requirements,
                        client,
                        scope=rewrite_scope,
                        intensity=rewrite_intensity,
                        original_resume_text=resume_text if privacy_enabled else None,
                        privacy_replacements=privacy_replacements,
                    )
                    previous.pop("edited_resume", None)
                    previous.pop("edit_warnings", None)
                    previous["resume_editor_revision"] = previous.get("resume_editor_revision", 0) + 1
                    previous["errors"].pop("rewrite", None)
                except (AnalysisError, RuntimeError, LLMError) as error:
                    previous["errors"]["rewrite"] = str(error)
                st.session_state["analysis_bundle"] = previous
                st.rerun()

            if rewrite is None:
                st.error(errors.get("rewrite", "简历改写未完成，请重试"))
            else:
                st.caption("红色表示从原文删除或替换的内容，绿色表示改写稿新增或替换后的内容。")
                active_rewritten_text = previous.get("edited_resume", rewrite.rewritten)
                original_html, rewritten_html = build_diff_html(resume_text, active_rewritten_text)
                diff_col1, diff_col2 = st.columns(2, gap="large")
                with diff_col1:
                    st.markdown("#### 原简历")
                    st.markdown(f'<div class="diff-panel">{original_html}</div>', unsafe_allow_html=True)
                with diff_col2:
                    st.markdown("#### 改写稿")
                    st.markdown(f'<div class="diff-panel">{rewritten_html}</div>', unsafe_allow_html=True)

                with st.expander("查看和复制纯文本改写稿"):
                    st.text_area(
                        "改写后的简历",
                        value=active_rewritten_text,
                        height=300,
                        key=(
                            f"rewritten_{input_signature}_"
                            f"{previous.get('resume_editor_revision', 0)}"
                        ),
                    )
                with st.expander("分模块编辑与Word导出", expanded=False):
                    st.caption(
                        "程序会按常见标题拆分简历。可修改模块名称或内容；保存后，"
                        "差异视图、报告、TXT和Word下载都会使用当前编辑稿。"
                    )
                    resume_sections = parse_resume_sections(active_rewritten_text)
                    section_rows = [
                        {"模块": section.title, "内容": section.content}
                        for section in resume_sections
                    ]
                    editor_revision = previous.get("resume_editor_revision", 0)
                    edited_sections = st.data_editor(
                        section_rows,
                        hide_index=True,
                        num_rows="dynamic",
                        width="stretch",
                        key=f"resume_sections_{input_signature}_{editor_revision}",
                        column_config={
                            "模块": st.column_config.TextColumn(required=True, width="small"),
                            "内容": st.column_config.TextColumn(required=True, width="large"),
                        },
                    )
                    save_col, reset_col = st.columns(2)
                    if save_col.button("保存模块修改", width="stretch"):
                        records = (
                            edited_sections.to_dict("records")
                            if hasattr(edited_sections, "to_dict")
                            else edited_sections
                        )
                        updated_sections = [
                            ResumeSection(str(row["模块"]).strip(), str(row["内容"]).strip())
                            for row in records
                            if str(row["模块"]).strip() or str(row["内容"]).strip()
                        ]
                        edited_text = sections_to_text(updated_sections)
                        if not edited_text:
                            st.error("编辑稿不能为空")
                        else:
                            previous["edited_resume"] = edited_text
                            previous["edit_warnings"] = (
                                check_facts_preserved(resume_text, edited_text)
                                + check_new_numbers(resume_text, edited_text)
                            )
                            previous["resume_editor_revision"] = editor_revision + 1
                            st.session_state["analysis_bundle"] = previous
                            st.rerun()
                    if reset_col.button(
                        "恢复模型改写稿",
                        disabled="edited_resume" not in previous,
                        width="stretch",
                    ):
                        previous.pop("edited_resume", None)
                        previous.pop("edit_warnings", None)
                        previous["resume_editor_revision"] = editor_revision + 1
                        st.session_state["analysis_bundle"] = previous
                        st.rerun()

                all_rewrite_warnings = list(rewrite.warnings) + list(previous.get("edit_warnings", []))
                for warning in all_rewrite_warnings:
                    st.warning(warning)
                if not all_rewrite_warnings:
                    st.success("事实校验通过：未发现原有数字或英文专有名词缺失，也未发现新增数字。")

        st.markdown('<div class="section-label">03 · 下载结果</div>', unsafe_allow_html=True)
        download_col1, download_col2 = st.columns(2)
        report = build_report(
            result,
            gap,
            delivery_rewrite,
            requirements=active_requirements,
            score=display_score,
            extra_warnings=manual_warnings,
            interview=interview,
        )
        download_col1.download_button(
            "下载完整分析报告（Markdown）",
            data=report,
            file_name="jd_match_report.md",
            mime="text/markdown",
            width="stretch",
        )
        if delivery_rewrite is not None:
            with download_col2:
                st.download_button(
                    "下载改写后的简历（TXT）",
                    data=delivery_rewrite.rewritten,
                    file_name="rewritten_resume.txt",
                    mime="text/plain",
                    width="stretch",
                )
                st.download_button(
                    "下载可编辑简历（Word）",
                    data=build_resume_docx(parse_resume_sections(delivery_rewrite.rewritten)),
                    file_name="rewritten_resume.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    width="stretch",
                )
        else:
            download_col2.caption("改写步骤完成后可下载TXT文件。")

        if not DEPLOYMENT.public:
            st.markdown(
                '<div class="section-label">04 · 本地记录</div>',
                unsafe_allow_html=True,
            )
            st.caption("保存的是摘要和不可逆指纹，不包含JD、简历、联系方式或上传文件原文。")
            if st.button("保存摘要到本地历史", key="save_history_snapshot"):
                skill_coverage = None
                if gap is not None and gap.jd_skills:
                    skill_coverage = int(
                        len(gap.matched) / len(gap.jd_skills) * 100 + 0.5
                    )
                job_title = next(
                    (line.strip() for line in jd_text.splitlines() if line.strip()),
                    "未命名岗位",
                )
                HistoryStore(HISTORY_DB).add(
                    job_title=job_title,
                    score=display_score,
                    matched_count=matched_count,
                    total_requirements=len(active_requirements),
                    skill_coverage=skill_coverage,
                    missing=active_missing_requirements,
                    requirement_statuses={
                        item["requirement"]: item["status"]
                        for item in active_requirements
                    },
                    jd_fingerprint=hashlib.sha256(jd_text.encode()).hexdigest(),
                    resume_fingerprint=hashlib.sha256(resume_text.encode()).hexdigest(),
                )
                st.session_state["show_history"] = True
                st.success("已保存本地摘要；未写入JD或简历原文。")
