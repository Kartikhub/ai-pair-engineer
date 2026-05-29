import html
import re
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st
from streamlit_ace import st_ace

from review_engine import generate_targeted_refactor, run_ai_review


SAMPLE_DIR = Path("sample_projects")

ASSISTANT_MODES = [
    "Architecture Coach",
    "Reliability Advisor",
    "Test Designer",
    "Refactor Assistant",
    "PR Readiness",
    "Full Engineering Review",
]

MODE_HINTS = {
    "Architecture Coach": [
        "Mapping service boundaries and ownership...",
        "Looking for implementation seams that will age well...",
        "Tracing dependency direction and orchestration flow...",
        "Checking whether the architecture is easy to evolve...",
    ],
    "Reliability Advisor": [
        "Evaluating operational resilience...",
        "Tracing timeout, retry, and idempotency paths...",
        "Looking for partial failure and concurrency risks...",
        "Checking how this behaves during downstream latency...",
    ],
    "Test Designer": [
        "Designing high-signal test coverage...",
        "Looking for edge cases worth locking down...",
        "Sketching failure-mode and concurrency tests...",
        "Finding the tests that would make this safer to change...",
    ],
    "Refactor Assistant": [
        "Looking for small maintainability wins...",
        "Finding refactors that avoid extra architecture...",
        "Checking readability and change isolation...",
        "Looking for simpler implementation boundaries...",
    ],
    "PR Readiness": [
        "Reviewing readiness for human feedback...",
        "Checking what a reviewer will need to trust this...",
        "Looking for missing operational context...",
        "Preparing implementation notes for the PR path...",
    ],
    "Full Engineering Review": [
        "Walking through the implementation from multiple angles...",
        "Reviewing architecture, reliability, tests, and PR readiness...",
        "Building a practical engineering pass over the code...",
        "Checking the system shape, risks, and next improvements...",
    ],
}

SAMPLE_PROJECTS = {
    "Payment Orchestrator Service": {
        "file": "payment_orchestrator_service.py",
        "scenario": "Coordinates external payment provider calls and booking confirmations.",
        "complexity": "High",
        "system_type": "Async API | External dependencies | Money movement",
        "focus": "timeouts, retries, idempotency, transactional boundaries, observability",
        "primary_concerns": ["Distributed Consistency", "Retry Handling", "Idempotency", "External Service Resilience"],
        "recommended_assistant": "Reliability Advisor",
    },
    "Ride Dispatch Worker": {
        "file": "ride_dispatch_worker.py",
        "scenario": "Processes ride allocation events from queues under concurrent load.",
        "complexity": "Medium-High",
        "system_type": "Queue worker | Concurrent allocation | State contention",
        "focus": "race conditions, backpressure, worker safety, allocation tests",
        "primary_concerns": ["Race Conditions", "Backpressure", "Worker Safety", "Concurrent State"],
        "recommended_assistant": "Architecture Coach",
    },
    "Notification Aggregation Service": {
        "file": "notification_aggregation_service.py",
        "scenario": "Handles notification fanout and retries across multiple communication providers.",
        "complexity": "Medium",
        "system_type": "Fanout service | Provider retries | Partial failure",
        "focus": "retry strategy, async throughput, dead letters, provider metrics",
        "primary_concerns": ["Retry Strategy", "Async Throughput", "Dead Letters", "Provider Metrics"],
        "recommended_assistant": "Reliability Advisor",
    },
}

GUIDANCE_SECTIONS = [
    "Architecture Guidance",
    "Reliability Advisor",
    "Test Designer",
    "Refactor Assistant",
    "PR Readiness",
    "Positive Engineering Note",
]

REFRACTOR_SECTIONS = [
    "Targeted Refactor",
    "Before",
    "After",
    "Implementation Notes",
]


def read_uploaded_file(uploaded_file) -> str:
    return uploaded_file.getvalue().decode("utf-8")


def sample_path(project_name: str) -> Path:
    return SAMPLE_DIR / SAMPLE_PROJECTS[project_name]["file"]


def selected_sample_code(project_name: str) -> tuple[str, str]:
    path = sample_path(project_name)
    return path.name, path.read_text(encoding="utf-8")


def sync_workspace(source_id: str, file_name: str, code: str) -> None:
    if st.session_state.get("source_id") != source_id:
        st.session_state.source_id = source_id
        st.session_state.file_name = file_name
        st.session_state.workspace_code = code
        st.session_state.guidance = ""
        st.session_state.refactor_result = ""


def normalize_markdown(text: str) -> str:
    text = re.sub(r"(?<!\n)\s+-\s+(?=[A-Z`])", "\n- ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_field(text: str, field_name: str) -> str:
    pattern = rf"\*\*{re.escape(field_name)}:\*\*\s*(.*?)(?=\n\*\*|\n-\s|\Z)"
    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def parse_guidance_body(body: str) -> dict[str, str]:
    body = normalize_markdown(body)
    severity_match = re.search(r"\*\*Severity:\*\*\s*(High|Medium|Low)", body)
    severity = severity_match.group(1) if severity_match else ""

    important = extract_field(body, "Most Important Fix") or extract_field(
        body, "Most Important Improvement"
    )
    why = extract_field(body, "Why This Matters")
    next_step = extract_field(body, "Recommended Next Step")

    recommendations = re.sub(r"\*\*Severity:\*\*\s*(High|Medium|Low)", "", body)
    recommendations = re.sub(
        r"\*\*Most Important (?:Fix|Improvement):\*\*\s*.*?(?=\n\*\*|\n-\s|\Z)",
        "",
        recommendations,
        flags=re.DOTALL,
    )
    recommendations = re.sub(
        r"\*\*Why This Matters:\*\*\s*.*?(?=\n\*\*|\n-\s|\Z)",
        "",
        recommendations,
        flags=re.DOTALL,
    )
    recommendations = re.sub(
        r"\*\*Recommended Next Step:\*\*\s*.*?(?=\n\*\*|\n-\s|\Z)",
        "",
        recommendations,
        flags=re.DOTALL,
    )

    return {
        "severity": severity,
        "important": important,
        "why": why,
        "next_step": next_step,
        "recommendations": normalize_markdown(recommendations),
    }


def render_severity(severity: str) -> None:
    if not severity:
        return

    label = {
        "High": "High production risk",
        "Medium": "Medium production risk",
        "Low": "Low production risk",
    }.get(severity, severity)
    st.markdown(
        f"""
        <div class="risk-row">
            <span class="risk-label">Production Risk Summary</span>
            <span class="severity severity-{severity.lower()}">{label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_callout(label: str, value: str, kind: str) -> None:
    if not value:
        return

    st.markdown(
        f"""
        <div class="callout callout-{kind}">
            <div class="callout-label">{label}</div>
            <div class="callout-body">{html.escape(value)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def loading_message(assistant_mode: str) -> str:
    last_message = st.session_state.get("last_loading_message")
    options = MODE_HINTS[assistant_mode]
    available_options = [message for message in options if message != last_message]
    message = random.choice(available_options or options)
    st.session_state.last_loading_message = message
    return message


def loading_messages(assistant_mode: str) -> list[str]:
    messages = MODE_HINTS[assistant_mode][:]
    random.shuffle(messages)
    return messages


def split_sections(result: str) -> dict[str, str]:
    sections = {}
    for index, section in enumerate(GUIDANCE_SECTIONS):
        marker = f"## {section}"
        if marker not in result:
            continue

        start = result.index(marker) + len(marker)
        next_positions = [
            result.find(f"## {next_section}", start)
            for next_section in GUIDANCE_SECTIONS[index + 1 :]
            if result.find(f"## {next_section}", start) != -1
        ]
        end = min(next_positions) if next_positions else len(result)
        sections[section] = result[start:end].strip()
    return sections


def inline_suggestions(code: str) -> list[dict[str, str]]:
    suggestions = []
    patterns = [
        (
            r"\b(httpx|requests)\.",
            "External dependency call",
            "I'd check timeout handling, retries, and idempotency around this call.",
        ),
        (
            r"asyncio\.sleep|status_code\s*>=\s*500",
            "Retry path",
            "This looks like retry behavior. I'd make it bounded, observable, and safe to replay.",
        ),
        (
            r"^\s*[A-Z_]+\s*=\s*(\{\}|\[\])",
            "In-memory shared state",
            "This will not scale across workers. I'd treat it as a prototype-only state boundary.",
        ),
        (
            r"\bprint\(",
            "Operational visibility",
            "I'd replace this with structured logging so production incidents have useful context.",
        ),
        (
            r"asyncio\.gather",
            "Concurrent execution",
            "I'd verify concurrency limits and failure handling so one slow task does not fan out risk.",
        ),
        (
            r"except Exception",
            "Broad exception handling",
            "I'd capture provider-specific failures and emit metrics instead of swallowing context.",
        ),
    ]

    for line_number, line in enumerate(code.splitlines(), start=1):
        for pattern, title, message in patterns:
            if re.search(pattern, line):
                suggestions.append(
                    {
                        "line": str(line_number),
                        "title": title,
                        "message": message,
                        "snippet": line.strip(),
                    }
                )
                break
        if len(suggestions) >= 4:
            break

    return suggestions


def render_inline_suggestions(code: str) -> None:
    suggestions = inline_suggestions(code)
    if not suggestions:
        return

    st.markdown(
        '<div class="inline-title">Inline Engineering Suggestions</div>',
        unsafe_allow_html=True,
    )
    for suggestion in suggestions:
        st.markdown(
            f"""
            <div class="inline-card">
                <div class="inline-meta">Line {suggestion["line"]} · {suggestion["title"]}</div>
                <div class="inline-message">{html.escape(suggestion["message"])}</div>
                <code>{html.escape(suggestion["snippet"])}</code>
            </div>
            """,
            unsafe_allow_html=True,
        )


def split_refactor_sections(result: str) -> dict[str, str]:
    sections = {}
    for index, section in enumerate(REFRACTOR_SECTIONS):
        marker = f"## {section}"
        if marker not in result:
            continue

        start = result.index(marker) + len(marker)
        next_positions = [
            result.find(f"## {next_section}", start)
            for next_section in REFRACTOR_SECTIONS[index + 1 :]
            if result.find(f"## {next_section}", start) != -1
        ]
        end = min(next_positions) if next_positions else len(result)
        sections[section] = result[start:end].strip()
    return sections


def extract_python_code(markdown: str) -> str:
    match = re.search(r"```(?:python)?\n(.*?)```", markdown, flags=re.DOTALL)
    return match.group(1).strip() if match else markdown.strip()


def render_refactor_preview(result: str) -> None:
    sections = split_refactor_sections(result)
    if not sections:
        st.markdown(result)
        return

    with st.expander("Apply Suggested Refactor", expanded=True):
        if sections.get("Targeted Refactor"):
            parsed = parse_refactor_summary(sections["Targeted Refactor"])
            render_severity(parsed["risk"])
            render_callout("Most Important Fix", parsed["important"], "primary")
            render_callout("Why This Matters", parsed["why"], "secondary")
            render_callout("Recommended Next Step", parsed["next_step"], "next")

        before_code = extract_python_code(sections.get("Before", ""))
        after_code = extract_python_code(sections.get("After", ""))
        if before_code or after_code:
            before_col, after_col = st.columns(2)
            with before_col:
                st.markdown(
                    '<div class="comparison-label">Current snippet</div>',
                    unsafe_allow_html=True,
                )
                st.code(before_code or "No before snippet returned.", language="python")
            with after_col:
                st.markdown(
                    '<div class="comparison-label">Improved snippet</div>',
                    unsafe_allow_html=True,
                )
                st.code(after_code or "No improved snippet returned.", language="python")

        if sections.get("Implementation Notes"):
            st.markdown(
                '<div class="recommendation-label">Implementation Notes</div>',
                unsafe_allow_html=True,
            )
            st.markdown(normalize_markdown(sections["Implementation Notes"]))


def parse_refactor_summary(body: str) -> dict[str, str]:
    risk_match = re.search(r"\*\*Production Risk:\*\*\s*(High|Medium|Low)", body)
    return {
        "risk": risk_match.group(1) if risk_match else "",
        "important": extract_field(body, "Most Important Fix"),
        "why": extract_field(body, "Why This Matters"),
        "next_step": extract_field(body, "Recommended Next Step"),
    }


def render_guidance_body(body: str) -> None:
    parsed = parse_guidance_body(body)
    has_structured_fields = any(
        [parsed["severity"], parsed["important"], parsed["why"], parsed["next_step"]]
    )

    render_severity(parsed["severity"])
    render_callout("Most Important Fix", parsed["important"], "primary")
    render_callout("Why This Matters", parsed["why"], "secondary")
    render_callout("Recommended Next Step", parsed["next_step"], "next")

    if parsed["recommendations"]:
        if has_structured_fields:
            st.markdown(
                '<div class="recommendation-label">Implementation Suggestions</div>',
                unsafe_allow_html=True,
            )
        st.markdown(parsed["recommendations"])


def render_guidance(result: str, assistant_mode: str) -> None:
    sections = split_sections(result)

    if not sections:
        render_guidance_body(result)
        return

    for section, body in sections.items():
        expanded = assistant_mode != "Full Engineering Review" or section != "Positive Engineering Note"
        with st.expander(section, expanded=expanded):
            render_guidance_body(body)


def render_system_overview(project: dict, name: str) -> None:
    concerns_html = "".join(
        f'<span class="concern-tag">{html.escape(c)}</span>'
        for c in project["primary_concerns"]
    )
    st.markdown(
        f"""
        <div class="system-overview">
            <div class="overview-label">System Overview</div>
            <div class="overview-title">{html.escape(name)}</div>
            <span class="complexity-badge">Complexity: {html.escape(project["complexity"])}</span>
            <div class="overview-sublabel">Primary Concerns</div>
            <div class="concerns-list">{concerns_html}</div>
            <div class="recommended-bar">
                <span class="recommended-label">Recommended Assistant</span>
                <span class="recommended-value">{html.escape(project["recommended_assistant"])}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(assistant_mode: str) -> None:
    mode_focus = {
        "Architecture Coach": "service boundaries, ownership patterns, and evolution paths",
        "Reliability Advisor": "timeouts, retries, idempotency, and partial failure scenarios",
        "Test Designer": "high-signal test coverage, edge cases, and failure-mode tests",
        "Refactor Assistant": "maintainability wins, readability, and change isolation",
        "PR Readiness": "what a reviewer needs to trust this implementation",
        "Full Engineering Review": "architecture, reliability, tests, and PR readiness in one pass",
    }
    focus = mode_focus.get(assistant_mode, "your implementation")
    st.markdown(
        f"""
        <div class="empty-state">
            <div class="empty-state-title">{html.escape(assistant_mode)} · Ready</div>
            <div class="empty-state-body">
                Reviewing <em>{html.escape(focus)}</em>.
                Edit the implementation or use the scenario as-is, then click
                <strong>Ask AI Pair Engineer</strong>.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(
    page_title="AI Pair Engineer",
    page_icon="🤖",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
        --bg: #eef3f8;
        --shell: #e5ecf5;
        --panel: #f8fafc;
        --panel-raised: #ffffff;
        --panel-soft: #edf2f8;
        --line: #c6d2e1;
        --line-soft: #d7e0ec;
        --text: #142033;
        --muted: #5b6b80;
        --accent: #2563eb;
        --accent-strong: #1d4ed8;
    }
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 34rem),
            linear-gradient(180deg, #f6f8fc 0%, var(--bg) 42%, #e7eef7 100%);
        color: var(--text);
    }
    header[data-testid="stHeader"] {
        height: 0;
        min-height: 0;
        visibility: hidden;
        background: transparent;
        border: 0;
    }
    header[data-testid="stHeader"] * {
        color: var(--text);
    }
    /* Sidebar expand button — must stay visible even when header is hidden */
    [data-testid="collapsedControl"] {
        visibility: visible !important;
        opacity: 1 !important;
        z-index: 999;
    }
    [data-testid="collapsedControl"] button {
        background: #f6f8fb !important;
        border: 1px solid #c8d2e0 !important;
        border-left: 0 !important;
        border-radius: 0 8px 8px 0 !important;
        color: var(--accent) !important;
    }
    [data-testid="collapsedControl"] button:hover {
        background: #e5edf7 !important;
    }
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"] {
        background: transparent;
        color: var(--text);
    }
    [data-testid="stToolbar"] button:hover,
    button[kind="header"]:hover {
        background: #dbe5f1;
        color: var(--text);
    }
    .block-container {
        padding-top: 0.65rem;
        padding-bottom: 1.5rem;
        max-width: 1500px;
    }
    h1, h2, h3 {
        color: #111827;
        letter-spacing: 0;
    }
    p, li, label, span {
        color: var(--text);
    }
    [data-testid="stSidebar"] {
        background: #f6f8fb;
        border-right: 1px solid #c8d2e0;
    }
    [data-testid="stSidebar"] * {
        color: #0f172a;
    }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #475569;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background: #ffffff;
        border-color: #94a3b8;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        border-radius: 8px;
        padding: 0.25rem 0.15rem;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {
        background: #e5edf7;
    }
    [data-testid="stSidebar"] hr {
        border-color: #d7e0ec;
    }
    .workspace-hero {
        border: 1px solid var(--line);
        background:
            linear-gradient(135deg, rgba(37, 99, 235, 0.08), transparent 45%),
            linear-gradient(180deg, #ffffff 0%, #eef4fb 100%);
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 1.1rem;
        box-shadow: 0 14px 35px rgba(31, 41, 55, 0.08);
    }
    .workspace-hero h1 {
        margin: 0;
        font-size: 1.65rem;
    }
    .workspace-hero p {
        color: var(--muted);
        margin: 0.35rem 0 0 0;
    }
    .context-card, .sample-card {
        border: 1px solid var(--line);
        background: var(--panel);
        border-radius: 8px;
        padding: 0.9rem 1rem;
        line-height: 1.55;
    }
    .sample-card {
        background: #ffffff;
        border-color: #ccd6e3;
        margin: 0.7rem 0 0.85rem 0;
    }
    .sample-card * {
        color: #0f172a;
    }
    .sample-title {
        font-size: 0.88rem;
        font-weight: 700;
        margin-bottom: 0.45rem;
    }
    .sample-meta {
        color: #475569;
        font-size: 0.8rem;
        line-height: 1.45;
    }
    .context-label {
        color: var(--muted);
        font-size: 0.76rem;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }
    .context-value {
        color: var(--text);
        font-size: 0.94rem;
    }
    .editor-shell,
    [data-testid="stCustomComponentV1"] {
        border: 1px solid var(--line);
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 18px 45px rgba(31, 41, 55, 0.12);
    }
    .severity {
        display: inline-block;
        border-radius: 999px;
        padding: 0.14rem 0.5rem;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .risk-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
        margin-bottom: 0.65rem;
    }
    .risk-label {
        color: var(--muted);
        font-size: 0.74rem;
        font-weight: 800;
        text-transform: uppercase;
    }
    .severity-high {
        color: #991b1b;
        background: #fef2f2;
        border: 1px solid #fca5a5;
    }
    .severity-medium {
        color: #92400e;
        background: #fffbeb;
        border: 1px solid #fbbf24;
    }
    .severity-low {
        color: #166534;
        background: #f0fdf4;
        border: 1px solid #86efac;
    }
    .callout {
        border: 1px solid var(--line-soft);
        border-radius: 8px;
        padding: 0.75rem 0.85rem;
        margin: 0.65rem 0;
    }
    .callout-primary {
        background: #eef6ff;
        border-color: #9cc8ff;
    }
    .callout-secondary {
        background: #f5f8fc;
        border-color: #c6d2e1;
    }
    .callout-next {
        background: #f7fbf6;
        border-color: #b8d8b8;
    }
    .callout-label {
        color: var(--accent);
        font-size: 0.74rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }
    .callout-body {
        color: var(--text);
        font-size: 0.92rem;
        line-height: 1.48;
    }
    .recommendation-label {
        color: var(--muted);
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0;
        text-transform: uppercase;
        margin: 0.85rem 0 0.35rem 0;
    }
    .inline-title {
        color: var(--muted);
        font-size: 0.76rem;
        font-weight: 800;
        text-transform: uppercase;
        margin: 0.9rem 0 0.45rem 0;
    }
    .inline-card {
        border: 1px solid #c6d2e1;
        background: #ffffff;
        border-radius: 8px;
        padding: 0.75rem 0.85rem;
        margin-bottom: 0.55rem;
        box-shadow: 0 8px 20px rgba(31, 41, 55, 0.05);
    }
    .inline-meta {
        color: #1d4ed8;
        font-size: 0.78rem;
        font-weight: 750;
        margin-bottom: 0.25rem;
    }
    .inline-message {
        color: var(--text);
        font-size: 0.88rem;
        line-height: 1.45;
        margin-bottom: 0.45rem;
    }
    .inline-card code {
        color: #334155;
        background: #f1f5f9;
        border: 1px solid #d7e0ec;
        border-radius: 6px;
        padding: 0.18rem 0.3rem;
        white-space: normal;
    }
    .comparison-label {
        color: var(--muted);
        font-size: 0.75rem;
        font-weight: 800;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }
    [data-testid="stExpander"] ul {
        margin-top: 0.35rem;
        padding-left: 1.15rem;
    }
    [data-testid="stExpander"] li {
        margin-bottom: 0.55rem;
        color: var(--text);
    }
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #0f3ea8;
        background: linear-gradient(180deg, #2f6df6 0%, #1d4ed8 100%);
        color: #ffffff !important;
        font-weight: 700;
        min-height: 2.7rem;
        box-shadow: 0 10px 22px rgba(37, 99, 235, 0.22);
    }
    .stButton > button * {
        color: #ffffff !important;
    }
    .stButton > button:hover {
        border-color: #1e40af;
        background: linear-gradient(180deg, #1d4ed8 0%, #1e40af 100%);
        color: #ffffff !important;
    }
    .stButton > button:focus {
        box-shadow: 0 0 0 2px rgba(125, 211, 252, 0.25);
    }
    [data-testid="stExpander"] {
        border: 1px solid var(--line);
        background: #ffffff;
        border-radius: 8px;
        box-shadow: 0 10px 26px rgba(31, 41, 55, 0.06);
    }
    [data-testid="stExpanderDetails"] {
        background: #ffffff;
    }
    [data-testid="stExpander"] details,
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary:hover,
    [data-testid="stExpander"] summary:focus,
    [data-testid="stExpander"] summary:focus-visible {
        background: #ffffff;
        color: #111827;
        outline: none;
    }
    [data-testid="stExpander"] summary:hover {
        background: #edf2f8;
    }
    [data-testid="stExpander"] summary:hover *,
    [data-testid="stExpander"] summary:focus *,
    [data-testid="stExpander"] summary:focus-visible * {
        color: #111827;
        background: transparent;
    }
    [data-testid="stExpander"] button:hover,
    [data-testid="stExpander"] button:focus,
    [data-testid="stExpander"] button:focus-visible {
        background: #edf2f8;
        color: #111827;
        border-color: var(--line);
        box-shadow: none;
    }
    [data-testid="stExpander"] summary p {
        color: #111827;
        font-weight: 650;
    }
    .stAlert {
        background: #ffffff;
        border: 1px solid var(--line);
        color: var(--text);
    }
    .stAlert * {
        color: var(--text);
    }
    .loading-card {
        border: 1px solid #bfdbfe;
        background: linear-gradient(180deg, #ffffff 0%, #eff6ff 100%);
        border-radius: 8px;
        padding: 0.9rem 1rem;
        margin: 0.75rem 0;
        box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
    }
    .loading-row {
        display: flex;
        align-items: center;
        gap: 0.65rem;
    }
    .loading-dot {
        width: 0.62rem;
        height: 0.62rem;
        border-radius: 999px;
        background: #2563eb;
        animation: pulse 1.1s ease-in-out infinite;
    }
    .loading-text {
        color: #1e3a8a;
        font-weight: 650;
        font-size: 0.92rem;
    }
    @keyframes pulse {
        0%, 100% { opacity: 0.35; transform: scale(0.9); }
        50% { opacity: 1; transform: scale(1.08); }
    }
    div[data-baseweb="select"] > div:hover {
        border-color: #64748b;
        background: #eef4fb;
    }
    div[data-testid="stFileUploaderDropzone"]:hover {
        border-color: #64748b;
        background: #eef4fb;
    }
    /* Selectbox / dropdown overlay — force light */
    [data-baseweb="popover"] [data-baseweb="menu"] {
        background: #ffffff;
        border: 1px solid var(--line);
        border-radius: 8px;
        box-shadow: 0 8px 24px rgba(31, 41, 55, 0.12);
    }
    [data-baseweb="option"] {
        background: #ffffff;
        color: var(--text);
    }
    [data-baseweb="option"]:hover {
        background: #edf2f8;
        color: var(--text);
    }
    /* Alert / info box → callout-primary style */
    div[data-testid="stAlert"] {
        background: #eef6ff;
        border: 1px solid #9cc8ff;
        border-radius: 8px;
        box-shadow: none;
    }
    div[data-testid="stAlert"] p {
        color: #1e3a8a;
        font-size: 0.92rem;
        line-height: 1.5;
    }
    div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
        color: #1e3a8a;
    }
    div[data-testid="stAlert"] svg {
        color: #2563eb;
        fill: #2563eb;
    }
    /* Caption consistency */
    [data-testid="stCaptionContainer"] p {
        color: var(--muted);
        font-size: 0.8rem;
    }
    /* Code blocks inside expanders */
    [data-testid="stExpander"] pre,
    [data-testid="stExpander"] code:not(.inline-card code) {
        background: #f1f5f9;
        border: 1px solid #d7e0ec;
        border-radius: 6px;
        color: #334155;
    }
    /* Column gap / layout breathing room */
    [data-testid="column"] > div:first-child {
        padding-top: 0;
    }
    /* System overview panel */
    .system-overview {
        border: 1px solid var(--line);
        background: linear-gradient(135deg, rgba(37, 99, 235, 0.04), transparent 60%), #ffffff;
        border-radius: 8px;
        padding: 0.85rem 1rem;
        margin: 0.5rem 0 0.7rem 0;
    }
    .overview-label {
        color: var(--muted);
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.4rem;
    }
    .overview-title {
        color: #0f172a;
        font-size: 0.86rem;
        font-weight: 700;
        margin-bottom: 0.4rem;
    }
    .overview-sublabel {
        color: var(--muted);
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        margin: 0.4rem 0 0.3rem 0;
    }
    .complexity-badge {
        display: inline-block;
        border-radius: 999px;
        padding: 0.12rem 0.5rem;
        font-size: 0.72rem;
        font-weight: 600;
        background: #eff6ff;
        color: #1e40af;
        border: 1px solid #bfdbfe;
        margin-bottom: 0.4rem;
    }
    .concerns-list {
        display: flex;
        flex-wrap: wrap;
        gap: 0.3rem;
        margin-bottom: 0.5rem;
    }
    .concern-tag {
        display: inline-block;
        background: #f1f5f9;
        border: 1px solid #d7e0ec;
        border-radius: 6px;
        padding: 0.1rem 0.4rem;
        font-size: 0.72rem;
        color: #334155;
    }
    .recommended-bar {
        background: #f0fdf4;
        border: 1px solid #86efac;
        border-radius: 6px;
        padding: 0.3rem 0.6rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
        flex-wrap: wrap;
    }
    .recommended-label {
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        color: #166534;
        white-space: nowrap;
    }
    .recommended-value {
        font-size: 0.78rem;
        font-weight: 600;
        color: #15803d;
    }
    /* Empty state */
    .empty-state {
        border: 1px dashed var(--line);
        border-radius: 8px;
        padding: 1.1rem 1.2rem;
        margin: 0.5rem 0;
        background: #fafcff;
    }
    .empty-state-title {
        color: var(--text);
        font-size: 0.84rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }
    .empty-state-body {
        color: var(--muted);
        font-size: 0.86rem;
        line-height: 1.5;
    }
    .empty-state-body strong {
        color: var(--accent);
        font-weight: 700;
    }
    .empty-state-body em {
        font-style: normal;
        color: var(--text);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="workspace-hero">
        <h1>AI Pair Engineer</h1>
        <p>Edit the backend implementation, choose a teammate mode, and rerun focused engineering guidance as you iterate.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Engineering Workspace")

    workspace_mode = st.radio(
        "workspace_mode",
        ["Demo Mode", "Custom Upload"],
        horizontal=True,
        label_visibility="collapsed",
    )

    uploaded_file = None
    selected_project = list(SAMPLE_PROJECTS.keys())[0]

    if workspace_mode == "Demo Mode":
        selected_project = st.selectbox(
            "Preloaded engineering scenario",
            options=list(SAMPLE_PROJECTS.keys()),
            index=0,
        )
        project = SAMPLE_PROJECTS[selected_project]
        render_system_overview(project, selected_project)
    else:
        project = SAMPLE_PROJECTS[selected_project]
        st.caption("Upload a `.py` file to analyse your own backend implementation.")
        uploaded_file = st.file_uploader(
            "Python implementation",
            type=["py"],
            label_visibility="collapsed",
        )

    st.divider()
    assistant_mode = st.radio(
        "Assistant mode",
        ASSISTANT_MODES,
        index=0,
    )

file_name, starter_code = selected_sample_code(selected_project)
scenario = project["scenario"]
source_id = f"sample:{selected_project}"

if workspace_mode == "Custom Upload" and uploaded_file is not None:
    file_name = uploaded_file.name
    starter_code = read_uploaded_file(uploaded_file)
    scenario = "Developer-uploaded backend implementation."
    source_id = f"upload:{uploaded_file.name}:{uploaded_file.size}"

sync_workspace(source_id, file_name, starter_code)

center, right = st.columns([1.22, 0.9], gap="large")

with center:
    st.subheader("Editable Implementation")
    st.caption(f"{st.session_state.file_name} | live workspace")
    edited_code = st_ace(
        value=st.session_state.workspace_code,
        language="python",
        theme="github",
        key=f"editor:{st.session_state.source_id}",
        height=620,
        font_size=14,
        tab_size=4,
        show_gutter=True,
        wrap=False,
        auto_update=True,
    )
    st.session_state.workspace_code = edited_code or ""
    render_inline_suggestions(st.session_state.workspace_code)

with right:
    st.subheader("AI Engineering Guidance")
    st.caption(f"{assistant_mode} | {st.session_state.file_name}")

    with st.container():
        st.markdown(
            f"""
            <div class="context-card">
                <div class="context-label">Current engineering context</div>
                <div class="context-value">{scenario}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    run_review = st.button(
        "Ask AI Pair Engineer",
        type="primary",
        disabled=not st.session_state.workspace_code.strip(),
        use_container_width=True,
    )

    if run_review:
        status_slot = st.empty()
        messages = loading_messages(assistant_mode)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                run_ai_review,
                code=st.session_state.workspace_code,
                file_name=st.session_state.file_name,
                assistant_mode=assistant_mode,
                scenario=scenario,
            )
            message_index = 0
            while not future.done():
                message = messages[message_index % len(messages)]
                status_slot.markdown(
                    f"""
                    <div class="loading-card">
                        <div class="loading-row">
                            <div class="loading-dot"></div>
                            <div class="loading-text">{message}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                message_index += 1
                time.sleep(3.75)

            status_slot.empty()
            st.session_state.guidance = future.result()
            st.session_state.guidance_mode = assistant_mode
            st.session_state.refactor_result = ""

    if st.session_state.get("guidance"):
        render_guidance(
            st.session_state.guidance,
            st.session_state.get("guidance_mode", assistant_mode),
        )
        generate_refactor = st.button(
            "Apply Suggested Refactor",
            disabled=not st.session_state.workspace_code.strip(),
            use_container_width=True,
        )
        if generate_refactor:
            status_slot = st.empty()
            refactor_messages = [
                "Drafting a focused implementation change...",
                "Keeping the refactor small and inspectable...",
                "Preparing a before and after snippet...",
            ]
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    generate_targeted_refactor,
                    code=st.session_state.workspace_code,
                    file_name=st.session_state.file_name,
                    assistant_mode=st.session_state.get(
                        "guidance_mode", assistant_mode
                    ),
                    scenario=scenario,
                    guidance=st.session_state.guidance,
                )
                message_index = 0
                while not future.done():
                    message = refactor_messages[
                        message_index % len(refactor_messages)
                    ]
                    status_slot.markdown(
                        f"""
                        <div class="loading-card">
                            <div class="loading-row">
                                <div class="loading-dot"></div>
                                <div class="loading-text">{message}</div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    message_index += 1
                    time.sleep(3.75)

                status_slot.empty()
                st.session_state.refactor_result = future.result()

        if st.session_state.get("refactor_result"):
            render_refactor_preview(st.session_state.refactor_result)
    else:
        render_empty_state(assistant_mode)
