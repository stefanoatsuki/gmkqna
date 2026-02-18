"""
Adjudication Platform — Evaluator Pair Consensus Tool
Streamlit app for resolving disagreements between evaluator pairs.
Only shows disagreed metrics; agreed metrics are auto-finalized.

Screens:
  0: Login (evaluator pair selects group)
  1: Adjudication Queue (list of disagreed queries with progress)
  2: Adjudication Review (core: side-by-side ratings + resolution form)
  3: Progress Dashboard (admin — overall progress + export)
"""

import streamlit as st
import json
import sys
import requests
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# Add parent directory to path for docx_parser import
app_dir = Path(__file__).parent
parent_dir = app_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from adjudication_storage import (
    load_progress, save_adjudication, get_adjudication_status,
    get_group_progress, get_all_progress, export_calibration_data,
    rebuild_progress_from_sheets
)
try:
    from docx_parser import find_model_responses
except ImportError:
    find_model_responses = None

# Page config
st.set_page_config(
    page_title="Adjudication Platform",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load CSS
css_path = app_dir / "adjudication_style.css"
if css_path.exists():
    with open(css_path, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# --- Configuration ---
DOCX_FOLDER = parent_dir / "docx_responses"
DATA_DIR = app_dir / "adjudication_data"
DISAGREEMENTS_FILE = DATA_DIR / "disagreements.json"
AGREED_FILE = DATA_DIR / "agreed_queries.json"
DOC_LINKS_FILE = DATA_DIR / "doc_links.json"

# Group-based login — evaluator pairs log in together as a group
GROUP_PASSWORDS = {
    "Group A": "GMK-adj-group-A-2024",
    "Group B": "GMK-adj-group-B-2024",
    "Group C": "GMK-adj-group-C-2024",
}

ADMIN_PASSWORD = "GMK-admin-dashboard-2024"

GROUP_PAIRS = {
    'A': ('Evaluator 1', 'Evaluator 2'),
    'B': ('Evaluator 3', 'Evaluator 4'),
    'C': ('Evaluator 5', 'Evaluator 6'),
}

ROOT_CAUSE_OPTIONS = [
    "Select root cause...",
    "One evaluator missed a specific finding (e.g., missed a hallucination, citation error, or omission)",
    "Both evaluators saw the same issue but disagreed on severity or significance",
    "The metric rubric was unclear or ambiguous, leading to different interpretations",
    "One evaluator made a clear mistake (e.g., wrong rating selected, misread the response)",
]

# Human-readable metric names
METRIC_DISPLAY_NAMES = {
    'source_a': 'Source Accuracy (Model A)',
    'source_b': 'Source Accuracy (Model B)',
    'hallucination_a': 'Hallucination (Model A)',
    'hallucination_b': 'Hallucination (Model B)',
    'safety_a': 'Safety Omission (Model A)',
    'safety_b': 'Safety Omission (Model B)',
    'content_a': 'Content Omission (Model A)',
    'content_b': 'Content Omission (Model B)',
    'extraneous_a': 'Extraneous Information (Model A)',
    'extraneous_b': 'Extraneous Information (Model B)',
    'flow_a': 'Flow (Model A)',
    'flow_b': 'Flow (Model B)',
    'preference': 'Model Preference',
}

# Rating options per metric type
METRIC_OPTIONS = {
    'source': ["No source issues (Pass)", "Yes, at least one source (Fail)"],
    'hallucination': ["No Hallucination", "Yes Hallucination"],
    'safety': ["No Safety Omission (Safe)", "Yes, Safety Omission (Unsafe)"],
    'content': ["No Omission (Complete)", "Yes, Omission (Incomplete)"],
    'extraneous': ["No extraneous information", "Yes, extraneous information"],
    'flow': ["No flow issues", "Yes, flow issues"],
}

PREFERENCE_OPTIONS = ["Model A", "Model B"]

# Google Sheets integration — same Apps Script URL, routes by _type field
# IMPORTANT: After deploying the updated Apps Script, replace this URL with the new deployment URL
GOOGLE_SHEETS_URL = "https://script.google.com/macros/s/AKfycbzIHcDgjRg91-UPWcmQPGrH_bsieiyqlV2R59KFmJnedhg0QEeZIuZTltaQ3-GZSS_j4g/exec"


def submit_adjudication_to_sheets(query_key: str, query: Dict,
                                   adjudication_data: Dict,
                                   evaluator: str) -> bool:
    """Submit adjudication data to Google Sheets (one row per metric)."""
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Build flattened metrics array — one entry per disagreed metric
        metrics = []
        for metric_key, adj in adjudication_data.items():
            r1, _ = get_evaluator_rating(query, metric_key, 1)
            r2, _ = get_evaluator_rating(query, metric_key, 2)
            display_name = METRIC_DISPLAY_NAMES.get(metric_key, metric_key)
            metrics.append({
                'metric': display_name,
                'metric_key': metric_key,
                'eval1_rating': r1 or '',
                'eval2_rating': r2 or '',
                'rating': adj.get('rating', '') or '',
                'findings': adj.get('findings', ''),
                'root_cause': adj.get('root_cause', ''),
            })

        payload = {
            '_type': 'adjudication',
            'query_key': query_key,
            'patient_id': query.get('patient_id', ''),
            'query_num': query.get('query_num', ''),
            'group': query.get('group', ''),
            'query_type': query.get('query_type', ''),
            'evaluator': evaluator,
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics,
        }

        response = requests.post(
            GOOGLE_SHEETS_URL,
            data=json.dumps(payload),
            timeout=10,
            verify=False,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 200:
            return True
        else:
            st.warning(f"Google Sheets sync failed (status {response.status_code}). Data saved locally.")
            return False
    except Exception as e:
        st.warning(f"Google Sheets sync failed: {e}. Data saved locally.")
        return False


def recover_progress_from_sheets():
    """Auto-recover adjudication progress from Google Sheets."""
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        response = requests.get(
            GOOGLE_SHEETS_URL,
            params={'type': 'adjudication'},
            verify=False,
            timeout=10
        )

        if response.status_code == 200:
            submissions = response.json()
            if isinstance(submissions, list) and len(submissions) > 0:
                count = rebuild_progress_from_sheets(submissions)
                return count
        return 0
    except Exception:
        return 0


# --- Session State ---
if 'screen' not in st.session_state:
    st.session_state.screen = 0
if 'group' not in st.session_state:
    st.session_state.group = None
if 'evaluator_name' not in st.session_state:
    st.session_state.evaluator_name = None
if 'selected_query_key' not in st.session_state:
    st.session_state.selected_query_key = None
if 'disagreements' not in st.session_state:
    st.session_state.disagreements = []
if 'login_error' not in st.session_state:
    st.session_state.login_error = False
if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False
if 'auto_recovery_attempted' not in st.session_state:
    st.session_state.auto_recovery_attempted = False


# --- Data Loading ---
def load_doc_links() -> Dict:
    """Load Google Doc links for Model A/B responses per patient."""
    if DOC_LINKS_FILE.exists():
        with open(DOC_LINKS_FILE, 'r') as f:
            return json.load(f)
    return {}


def load_disagreements():
    """Load disagreement data and auto-recover from Google Sheets if needed."""
    if DISAGREEMENTS_FILE.exists():
        with open(DISAGREEMENTS_FILE, 'r') as f:
            st.session_state.disagreements = json.load(f)
    else:
        st.error("Disagreements data not found. Run prepare_adjudication.py first.")
        st.stop()

    # Auto-recover from Google Sheets (once per session)
    if not st.session_state.auto_recovery_attempted:
        st.session_state.auto_recovery_attempted = True
        progress = load_progress()
        if not progress:
            count = recover_progress_from_sheets()
            if count > 0:
                st.toast(f"Recovered {count} adjudications from Google Sheets")


def get_group_disagreements(group: str) -> list:
    """Get disagreements for a specific group."""
    return [d for d in st.session_state.disagreements if d['group'] == group]


def get_query_by_key(query_key: str) -> Optional[Dict]:
    """Find a query by its key."""
    for d in st.session_state.disagreements:
        if d['query_key'] == query_key:
            return d
    return None


# --- Helper Functions ---
def get_badge_html(rating: str, metric_type: str = 'metric') -> str:
    """Generate HTML badge for a rating."""
    if metric_type == 'preference':
        if 'Model A' in str(rating):
            return f'<span class="eval-badge-model-a">{rating}</span>'
        else:
            return f'<span class="eval-badge-model-b">{rating}</span>'

    fail_keywords = ['Yes', 'Fail', 'Unsafe', 'Incomplete', 'extraneous', 'flow issues']
    is_fail = any(kw.lower() in str(rating).lower() for kw in fail_keywords)

    if is_fail:
        return f'<span class="eval-badge-fail">{rating}</span>'
    else:
        return f'<span class="eval-badge-pass">{rating}</span>'


def get_severity_class(n: int) -> str:
    """Get CSS class for disagreement severity."""
    if n <= 1:
        return "severity-low"
    elif n <= 3:
        return "severity-medium"
    else:
        return "severity-high"


def get_metric_base(metric_key: str) -> str:
    if metric_key == 'preference':
        return 'preference'
    return metric_key.rsplit('_', 1)[0]


def get_metric_model(metric_key: str) -> str:
    if metric_key == 'preference':
        return ''
    return metric_key.rsplit('_', 1)[1]


def get_evaluator_rating(query: Dict, metric_key: str, evaluator_num: int) -> tuple:
    eval_key = f'evaluator_{evaluator_num}'
    evaluator = query[eval_key]

    if metric_key == 'preference':
        return evaluator['preference'], evaluator['preference_reasons']

    base = get_metric_base(metric_key)
    model = get_metric_model(metric_key)
    model_key = f'model_{model}'

    rating = evaluator[model_key].get(base, '')
    findings = evaluator[model_key].get(f'{base}_findings', '')
    return rating, findings


def get_flagging_evaluator(query: Dict, metric_key: str) -> int:
    r1, _ = get_evaluator_rating(query, metric_key, 1)
    r2, _ = get_evaluator_rating(query, metric_key, 2)

    if metric_key == 'preference':
        return 1

    fail_keywords = ['Yes', 'Fail', 'Unsafe', 'Incomplete', 'extraneous', 'flow issues']
    r1_is_fail = any(kw.lower() in str(r1).lower() for kw in fail_keywords)
    r2_is_fail = any(kw.lower() in str(r2).lower() for kw in fail_keywords)

    if r2_is_fail and not r1_is_fail:
        return 2
    return 1


def render_model_response(model_text: Optional[str], label: str):
    if model_text:
        is_html = '<' in model_text and ('div' in model_text or 'p>' in model_text or 'a href' in model_text)
        if is_html:
            st.markdown(f"<div class='model-response-content'>{model_text}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='color: #4a4a4a; white-space: pre-wrap; "
                        f"font-size: 15px; line-height: 1.7;'>{model_text}</div>", unsafe_allow_html=True)
    else:
        st.info(f"No {label} response found for this patient/query.")


# ===== SCREEN 0: LOGIN =====
def screen0_login():
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.markdown("<div style='text-align: center;'>"
                "<div style='color: #6366f1; font-size: 26px; font-weight: 700; "
                "letter-spacing: -0.02em;'>Adjudication Platform</div>"
                "<div style='color: #6b6560; font-size: 15px; margin-top: 6px;'>"
                "Evaluator Pair Consensus Tool</div>"
                "</div>", unsafe_allow_html=True)

    st.markdown("<div style='color: #555555; text-align: center; "
                "max-width: 480px; margin: 24px auto 44px auto; font-size: 15px; line-height: 1.7;'>"
                "This tool presents only the metrics where you and your partner disagreed. "
                "Log in as your evaluator group, share your screen on a call, and work through each disagreement together."
                "</div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        group_selection = st.selectbox("Select Your Evaluator Group:",
                                       ["Select..."] + list(GROUP_PASSWORDS.keys()),
                                       key="login_group")
        password = st.text_input("Group Password:", type="password", key="login_pw")

        if st.session_state.login_error:
            st.error("Invalid password. Please try again.")

        if group_selection and group_selection != "Select...":
            group_letter = group_selection[-1]
            e1, e2 = GROUP_PAIRS[group_letter]
            st.markdown(f"<div style='color: #6b6560; font-size: 15px; margin-top: 2px;'>"
                        f"{e1} & {e2}</div>", unsafe_allow_html=True)

        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        admin_pw = st.text_input("Admin Access (optional):", type="password", key="admin_pw")

        if st.button("Login", type="primary", use_container_width=True):
            if admin_pw == ADMIN_PASSWORD:
                st.session_state.is_admin = True
                st.session_state.screen = 3
                load_disagreements()
                st.rerun()
                return

            if group_selection == "Select...":
                st.warning("Please select your evaluator group.")
                return

            if GROUP_PASSWORDS.get(group_selection) == password:
                group_letter = group_selection[-1]
                st.session_state.group = group_letter
                st.session_state.evaluator_name = group_selection
                st.session_state.login_error = False
                load_disagreements()
                st.session_state.screen = 1
                st.rerun()
            else:
                st.session_state.login_error = True
                st.rerun()


# ===== SCREEN 1: ADJUDICATION QUEUE =====
def screen1_queue():
    group = st.session_state.group
    group_queries = get_group_disagreements(group)
    progress_data = get_group_progress(group, st.session_state.disagreements)
    adj_progress = load_progress()

    e1_name, e2_name = GROUP_PAIRS[group]

    # Header
    header_cols = st.columns([5, 1])
    with header_cols[0]:
        st.markdown(f"<div style='font-size: 22px; font-weight: 700; color: #1a1a1a; "
                    f"letter-spacing: -0.02em;'>Adjudication Queue</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='color: #6b6560; font-size: 15px; margin-top: 4px;'>"
                    f"Group {group} &nbsp;·&nbsp; {e1_name} & {e2_name} &nbsp;·&nbsp; "
                    f"<strong style='color: #6366f1;'>{progress_data['completed']}</strong> of "
                    f"{progress_data['total']} completed"
                    f"</div>", unsafe_allow_html=True)
    with header_cols[1]:
        if st.button("Logout", key="logout_btn"):
            st.session_state.screen = 0
            st.session_state.group = None
            st.session_state.evaluator_name = None
            st.rerun()

    # Progress bar
    pct = progress_data['percent']
    st.markdown(f"<div class='adj-progress-bar'>"
                f"<div class='adj-progress-fill' style='width: {max(pct, 2)}%;'></div>"
                f"</div>", unsafe_allow_html=True)

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # Sort: incomplete first, then by n_disagreements descending
    def sort_key(q):
        is_done = adj_progress.get(q['query_key'], {}).get('completed', False)
        return (is_done, -q['n_disagreements'], q['query_num'])

    sorted_queries = sorted(group_queries, key=sort_key)

    for q in sorted_queries:
        is_done = adj_progress.get(q['query_key'], {}).get('completed', False)
        severity = get_severity_class(q['n_disagreements'])
        completed_class = "completed" if is_done else ""

        disagreement_labels = [METRIC_DISPLAY_NAMES.get(m, m) for m in q['disagreements']]
        disagreement_text = " · ".join(disagreement_labels)

        card_html = f"""
        <div class='queue-card {completed_class}'>
            <div class='queue-card-header'>
                <div>
                    <span class='queue-card-title'>Patient {q['patient_id']}</span>
                    <span class='queue-card-meta'>&nbsp;&nbsp;Q{q['query_num']} · {q['query_type']}</span>
                </div>
                <div>
                    <span class='severity-badge {severity}'>
                        {q['n_disagreements']} disagreement{'s' if q['n_disagreements'] != 1 else ''}
                    </span>
                </div>
            </div>
            <div class='queue-card-metrics'>{disagreement_text}</div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

        btn_label = "Review" if not is_done else "Edit"
        if st.button(f"{btn_label} — Patient {q['patient_id']}, Q{q['query_num']}",
                      key=f"open_{q['query_key']}", use_container_width=True):
            st.session_state.selected_query_key = q['query_key']
            st.session_state.screen = 2
            st.rerun()

        st.markdown("<hr style='border: none; border-top: 1px solid #d5d2cd; margin: 20px 0 24px 0;'>",
                    unsafe_allow_html=True)


# ===== SCREEN 2: ADJUDICATION REVIEW =====
def screen2_review():
    query_key = st.session_state.selected_query_key
    query = get_query_by_key(query_key)

    if not query:
        st.error(f"Query {query_key} not found.")
        return

    patient_id = query['patient_id']
    query_num = query['query_num']
    disagreements = query['disagreements']
    existing_adj = get_adjudication_status(query_key) or {}

    # Navigation
    nav_cols = st.columns([1, 6, 1])
    with nav_cols[0]:
        if st.button("Back to Queue", key="back_queue"):
            st.session_state.screen = 1
            st.rerun()
    with nav_cols[2]:
        if existing_adj.get('completed'):
            st.markdown("<span style='color: #059669; font-size: 15px; font-weight: 600;'>"
                        "Adjudicated</span>", unsafe_allow_html=True)

    # Header
    st.markdown(f"<div style='margin-top: 8px;'>"
                f"<span style='color: #1a1a1a; font-size: 22px; font-weight: 700; "
                f"letter-spacing: -0.02em;'>Patient {patient_id}</span>"
                f"</div>", unsafe_allow_html=True)

    st.markdown(f"<div style='display: flex; gap: 16px; align-items: center; margin-top: 8px;'>"
                f"<span style='color: #6b6560; font-size: 15px;'>Query {query_num}</span>"
                f"<span style='color: #6b6560; font-size: 15px;'>{query['query_type']}</span>"
                f"<span style='color: #6b6560; font-size: 15px;'>PHI: {query['phi_dependency']}</span>"
                f"<span class='severity-badge severity-medium'>"
                f"{len(disagreements)} disagreement{'s' if len(disagreements) != 1 else ''}</span>"
                f"</div>", unsafe_allow_html=True)

    # Query Text
    st.markdown(f"<div style='background-color: #f7f6f3; border-radius: 12px; "
                f"padding: 20px 24px; margin: 20px 0 28px 0; "
                f"border: 1px solid #e2dfda; border-left: 4px solid #6366f1;'>"
                f"<div style='color: #6b6560; font-size: 12px; text-transform: uppercase; "
                f"letter-spacing: 0.08em; font-weight: 600; margin-bottom: 10px;'>Query</div>"
                f"<div style='color: #2d2d2d; font-size: 15px; line-height: 1.7;'>"
                f"{query['query_text']}</div>"
                f"</div>", unsafe_allow_html=True)

    # Three-column layout: Patient | Model A | Model B
    col_patient, col_a, col_b = st.columns([1, 1.2, 1.2])

    with col_patient:
        st.markdown("<div style='color: #6b6560; font-size: 12px; font-weight: 600; "
                    "text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px;'>"
                    "Patient Summary</div>", unsafe_allow_html=True)
        patient_box = st.container(height=420, border=True)
        with patient_box:
            st.markdown(f"<div style='color: #3d3d3d; font-size: 15px; "
                        f"white-space: pre-wrap; line-height: 1.7;'>{query['patient_summary']}</div>",
                        unsafe_allow_html=True)

    # Load DOCX responses
    model_a_text, model_b_text = None, None
    if find_model_responses and DOCX_FOLDER.exists():
        model_a_text, model_b_text = find_model_responses(DOCX_FOLDER, patient_id, str(query_num))

    # Load Google Doc links
    doc_links = load_doc_links()
    patient_links = doc_links.get(patient_id, {})

    with col_a:
        a_url = patient_links.get('model_a_url', '')
        label_a = ("<div style='color: #059669; font-size: 12px; font-weight: 600; "
                   "text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px;'>Model A")
        if a_url:
            label_a += (f" &nbsp;<a href='{a_url}' target='_blank' style='color: #6366f1; "
                        f"font-size: 12px; text-decoration: none; font-weight: 500;'>Open in Docs</a>")
        label_a += "</div>"
        st.markdown(label_a, unsafe_allow_html=True)
        a_box = st.container(height=420, border=True)
        with a_box:
            render_model_response(model_a_text, "Model A")

    with col_b:
        b_url = patient_links.get('model_b_url', '')
        label_b = ("<div style='color: #2563eb; font-size: 12px; font-weight: 600; "
                   "text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px;'>Model B")
        if b_url:
            label_b += (f" &nbsp;<a href='{b_url}' target='_blank' style='color: #6366f1; "
                        f"font-size: 12px; text-decoration: none; font-weight: 500;'>Open in Docs</a>")
        label_b += "</div>"
        st.markdown(label_b, unsafe_allow_html=True)
        b_box = st.container(height=420, border=True)
        with b_box:
            render_model_response(model_b_text, "Model B")

    # --- Disagreed Metrics ---
    st.markdown("<hr class='adj-section-divider'>", unsafe_allow_html=True)
    st.markdown(f"<div style='margin-bottom: 4px;'>"
                f"<span style='color: #1a1a1a; font-size: 20px; font-weight: 700;'>"
                f"Resolve Disagreements</span>"
                f"<span style='color: #6b6560; font-size: 15px; margin-left: 10px;'>"
                f"{len(disagreements)} metric{'s' if len(disagreements) != 1 else ''}</span>"
                f"</div>", unsafe_allow_html=True)

    adjudication_data = {}

    for metric_key in disagreements:
        display_name = METRIC_DISPLAY_NAMES.get(metric_key, metric_key)
        base_metric = get_metric_base(metric_key)

        r1, f1 = get_evaluator_rating(query, metric_key, 1)
        r2, f2 = get_evaluator_rating(query, metric_key, 2)
        e1_name = query['evaluator_1']['name']
        e2_name = query['evaluator_2']['name']

        flagging_eval = get_flagging_evaluator(query, metric_key)
        existing_metric_adj = existing_adj.get(metric_key, {})

        st.markdown(f"<div class='metric-disagreed'>"
                    f"<span style='color: #4338ca; font-weight: 700; font-size: 15px;'>"
                    f"{display_name}</span>"
                    f"</div>", unsafe_allow_html=True)

        # Both evaluators side by side
        eval_col1, eval_col2 = st.columns(2)

        with eval_col1:
            badge1 = get_badge_html(r1, 'preference' if metric_key == 'preference' else 'metric')
            findings_html1 = (f"<div class='eval-findings'>{f1}</div>" if f1
                              else "<div class='eval-findings' style='color: #8a8580;'>(no findings)</div>")
            st.markdown(f"<div class='eval-card'>"
                        f"<div style='color: #6b6560; font-size: 14px; font-weight: 600; "
                        f"margin-bottom: 6px;'>{e1_name}</div>"
                        f"{badge1}"
                        f"{findings_html1}"
                        f"</div>", unsafe_allow_html=True)

        with eval_col2:
            badge2 = get_badge_html(r2, 'preference' if metric_key == 'preference' else 'metric')
            findings_html2 = (f"<div class='eval-findings'>{f2}</div>" if f2
                              else "<div class='eval-findings' style='color: #8a8580;'>(no findings)</div>")
            st.markdown(f"<div class='eval-card'>"
                        f"<div style='color: #6b6560; font-size: 14px; font-weight: 600; "
                        f"margin-bottom: 6px;'>{e2_name}</div>"
                        f"{badge2}"
                        f"{findings_html2}"
                        f"</div>", unsafe_allow_html=True)

        # Source accuracy callout
        if 'source' in metric_key:
            st.markdown("<div class='citation-callout'>"
                        "⚠ <strong>Source Accuracy:</strong> Please review ALL citations for this response "
                        "(not just the first 2 reviewed during initial evaluation)."
                        "</div>", unsafe_allow_html=True)

        # Adjudication form
        st.markdown("<div style='border-top: 1px solid #e2dfda; margin: 8px 0 6px 0; padding-top: 8px;'>"
                    "<div class='adj-form-label'>Final Adjudication</div>"
                    "</div>", unsafe_allow_html=True)

        if metric_key == 'preference':
            options = PREFERENCE_OPTIONS
            default_idx = None
            if existing_metric_adj.get('rating') and existing_metric_adj['rating'] in options:
                default_idx = options.index(existing_metric_adj['rating'])

            adj_rating = st.radio(
                "Adjudicated Preference:",
                options, index=default_idx,
                key=f"adj_{metric_key}", horizontal=True, label_visibility="collapsed"
            )

            adj_findings = st.text_area(
                "Final Preference Reasons:",
                value=existing_metric_adj.get('findings', ''),
                key=f"adj_findings_{metric_key}", height=80,
                placeholder="Agreed-upon preference reasoning...",
                label_visibility="visible"
            )
        else:
            options = METRIC_OPTIONS.get(base_metric, ["Pass", "Fail"])
            default_idx = None
            if existing_metric_adj.get('rating') and existing_metric_adj['rating'] in options:
                default_idx = options.index(existing_metric_adj['rating'])

            adj_rating = st.radio(
                f"Adjudicated {display_name}:",
                options, index=default_idx,
                key=f"adj_{metric_key}", horizontal=True, label_visibility="collapsed"
            )

            adj_findings = st.text_area(
                "Final Findings:",
                value=existing_metric_adj.get('findings', ''),
                key=f"adj_findings_{metric_key}", height=60,
                placeholder="Agreed-upon findings...",
                label_visibility="visible"
            )

        # Root cause
        default_root_cause_idx = 0
        if existing_metric_adj.get('root_cause') in ROOT_CAUSE_OPTIONS:
            default_root_cause_idx = ROOT_CAUSE_OPTIONS.index(existing_metric_adj['root_cause'])

        root_cause = st.selectbox(
            "Root Cause of Disagreement:",
            ROOT_CAUSE_OPTIONS,
            index=default_root_cause_idx,
            key=f"rc_{metric_key}",
            label_visibility="visible"
        )

        adjudication_data[metric_key] = {
            'rating': adj_rating,
            'findings': adj_findings,
            'root_cause': root_cause,
            'root_cause_detail': '',
        }

        # Visual separator between metrics
        st.markdown("<div style='border-bottom: 3px solid #c5c0bb; margin: 28px 0 24px 0;'></div>",
                    unsafe_allow_html=True)

    # Submit
    st.markdown("<hr class='adj-section-divider'>", unsafe_allow_html=True)

    submit_col1, submit_col2 = st.columns([3, 1])
    with submit_col1:
        if st.button("Submit Adjudication", type="primary", use_container_width=True, key="submit_adj"):
            missing_rating = []
            missing_findings = []
            missing_root_cause = []
            for mk, data in adjudication_data.items():
                display = METRIC_DISPLAY_NAMES.get(mk, mk)
                if data['rating'] is None:
                    missing_rating.append(display)
                if not data['findings'].strip():
                    missing_findings.append(display)
                if data['root_cause'] == "Select root cause...":
                    missing_root_cause.append(display)

            if missing_rating:
                st.error(f"Please select a rating for: {', '.join(missing_rating)}")
            elif missing_findings:
                st.error(f"Please enter findings for: {', '.join(missing_findings)}")
            elif missing_root_cause:
                st.error(f"Please select a root cause for: {', '.join(missing_root_cause)}")
            else:
                save_adjudication(query_key, adjudication_data)

                sheets_ok = submit_adjudication_to_sheets(
                    query_key, query, adjudication_data,
                    st.session_state.evaluator_name or 'admin'
                )
                if sheets_ok:
                    st.success("Adjudication saved & synced to Google Sheets!")
                else:
                    st.success("Adjudication saved locally. (Sheets sync will retry later.)")

                progress = load_progress()
                group_queries = get_group_disagreements(st.session_state.group)
                next_query = None
                for q in group_queries:
                    if not progress.get(q['query_key'], {}).get('completed', False):
                        if q['query_key'] != query_key:
                            next_query = q
                            break

                if next_query:
                    st.session_state.selected_query_key = next_query['query_key']
                    st.rerun()
                else:
                    st.session_state.screen = 1
                    st.rerun()

    with submit_col2:
        if st.button("Back to Queue", key="back_btn"):
            st.session_state.screen = 1
            st.rerun()


# ===== SCREEN 3: ADMIN DASHBOARD =====
def screen3_dashboard():
    st.markdown("<div style='font-size: 22px; font-weight: 700; color: #1a1a1a; "
                "letter-spacing: -0.02em;'>Admin Dashboard</div>", unsafe_allow_html=True)

    load_disagreements()
    overall = get_all_progress(st.session_state.disagreements)

    # Overall progress
    st.markdown(f"<div style='background-color: #f7f6f3; border-radius: 12px; "
                f"padding: 24px; margin: 16px 0; border: 1px solid #e2dfda;'>"
                f"<div style='color: #6b6560; font-size: 15px; font-weight: 600;'>"
                f"Overall Adjudication Progress</div>"
                f"<div style='margin-top: 8px;'>"
                f"<span style='color: #6366f1; font-size: 32px; font-weight: 700; "
                f"font-variant-numeric: tabular-nums;'>{overall['completed']}</span>"
                f"<span style='color: #6b6560; font-size: 16px;'> / {overall['total']} completed</span>"
                f"</div>"
                f"<div class='adj-progress-bar' style='margin-top: 12px;'>"
                f"<div class='adj-progress-fill' style='width: {max(overall['percent'], 2)}%;'></div>"
                f"</div>"
                f"</div>", unsafe_allow_html=True)

    # Per-group progress
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for i, group in enumerate(['A', 'B', 'C']):
        gp = get_group_progress(group, st.session_state.disagreements)
        e1, e2 = GROUP_PAIRS[group]
        with cols[i]:
            gpct = gp['percent']
            st.markdown(f"<div style='background-color: #f7f6f3; border-radius: 12px; "
                        f"padding: 20px; text-align: center; border: 1px solid #e2dfda;'>"
                        f"<div style='color: #6366f1; font-weight: 700; font-size: 15px;'>"
                        f"Group {group}</div>"
                        f"<div style='color: #6b6560; font-size: 14px; margin-top: 2px;'>"
                        f"{e1} & {e2}</div>"
                        f"<div style='color: #1a1a1a; font-size: 22px; font-weight: 700; "
                        f"margin-top: 8px; font-variant-numeric: tabular-nums;'>"
                        f"{gp['completed']}/{gp['total']}</div>"
                        f"<div class='adj-progress-bar' style='margin-top: 8px;'>"
                        f"<div class='adj-progress-fill' style='width: {max(gpct, 2)}%;'></div>"
                        f"</div></div>", unsafe_allow_html=True)

    # Calibration data
    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
    st.markdown("<div style='color: #1a1a1a; font-size: 16px; font-weight: 700;'>"
                "Calibration Data</div>", unsafe_allow_html=True)

    calibration = export_calibration_data(st.session_state.disagreements)
    if calibration:
        import pandas as pd
        cal_df = pd.DataFrame(calibration)

        if 'root_cause' in cal_df.columns:
            st.markdown("<div style='color: #555555; font-size: 15px; font-weight: 600; "
                        "margin-top: 8px;'>Root Cause Distribution</div>", unsafe_allow_html=True)
            rc_counts = cal_df['root_cause'].value_counts()
            for rc, count in rc_counts.items():
                pct_rc = count / len(cal_df) * 100
                st.markdown(f"<div style='color: #3d3d3d; font-size: 15px; margin: 2px 0;'>"
                            f"{rc}: <strong>{count}</strong> ({pct_rc:.1f}%)</div>",
                            unsafe_allow_html=True)

        st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
        if 'metric' in cal_df.columns and 'root_cause' in cal_df.columns:
            st.markdown("<div style='color: #555555; font-size: 15px; font-weight: 600;'>"
                        "Root Cause by Metric</div>", unsafe_allow_html=True)
            pivot = cal_df.groupby(['metric', 'root_cause']).size().unstack(fill_value=0)
            st.dataframe(pivot, use_container_width=True)
    else:
        st.info("No adjudication data yet. Calibration summary will appear as queries are adjudicated.")

    # Export
    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    exp_col1, exp_col2 = st.columns(2)

    with exp_col1:
        if st.button("Export Calibration Report (CSV)", use_container_width=True):
            if calibration:
                import pandas as pd
                cal_df = pd.DataFrame(calibration)
                csv_data = cal_df.to_csv(index=False)
                st.download_button("Download calibration_report.csv", csv_data,
                                   "calibration_report.csv", "text/csv")
            else:
                st.warning("No calibration data to export yet.")

    with exp_col2:
        if st.button("Export Final Dataset (CSV)", use_container_width=True):
            st.info("Run merge_final_dataset.py after all adjudication is complete.")

    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
    if st.button("Logout", key="admin_logout"):
        st.session_state.screen = 0
        st.session_state.is_admin = False
        st.rerun()


# ===== MAIN ROUTER =====
def main():
    if st.session_state.screen == 0:
        screen0_login()
    elif st.session_state.screen == 1:
        screen1_queue()
    elif st.session_state.screen == 2:
        screen2_review()
    elif st.session_state.screen == 3:
        screen3_dashboard()
    else:
        st.session_state.screen = 0
        st.rerun()


if __name__ == "__main__":
    main()
