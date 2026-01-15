"""
Medical Evaluation Platform - Multi-Screen Workflow
Screen 1: Evaluator Selection
Screen 2: Query List with Status
Screen 3: Model A Evaluation
Screen 4: Model B Evaluation
Screen 5: Head-to-Head Comparison
"""

import streamlit as st
import pandas as pd
import json
import requests
import urllib3
from pathlib import Path
from typing import Optional, Dict
import sys

# Disable SSL warnings for sandboxed environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Import local modules
# Using explicit imports to avoid import cache issues on Streamlit Cloud
import importlib.util
from pathlib import Path

def import_module_from_file(module_name, file_path):
    """Import a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Get the directory where app.py is located
app_dir = Path(__file__).parent

# Import modules
docx_parser = import_module_from_file("docx_parser", app_dir / "docx_parser.py")
data_loader = import_module_from_file("data_loader", app_dir / "data_loader.py")
evaluation_storage = import_module_from_file("evaluation_storage", app_dir / "evaluation_storage.py")

# Extract functions
find_model_responses = docx_parser.find_model_responses
load_evaluation_metadata = data_loader.load_evaluation_metadata
load_assignments = data_loader.load_assignments
save_assignments = data_loader.save_assignments
create_assignments = data_loader.create_assignments
get_evaluation_status = evaluation_storage.get_evaluation_status
update_evaluation_status = evaluation_storage.update_evaluation_status
get_all_evaluator_queries = evaluation_storage.get_all_evaluator_queries
reset_all_evaluations = evaluation_storage.reset_all_evaluations

# Page config
st.set_page_config(
    page_title="Medical Evaluation Platform",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load custom CSS
with open(Path(__file__).parent / "style.css", "r") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Scroll to top on every page load/rerun
st.markdown("""
<style>
    html { scroll-behavior: auto !important; }
    body { scroll-behavior: auto !important; }
</style>
<script>
    // Immediately scroll to top
    window.scrollTo({top: 0, left: 0, behavior: 'instant'});
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    
    // Scroll parent frame if in iframe
    if (window.parent !== window) {
        try { 
            window.parent.scrollTo({top: 0, left: 0, behavior: 'instant'}); 
            window.parent.document.documentElement.scrollTop = 0;
        } catch(e) {}
    }
    
    // Also scroll any scrollable containers to top
    document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"]').forEach(el => {
        el.scrollTop = 0;
    });
</script>
""", unsafe_allow_html=True)

# Configuration
CSV_PATH = Path(__file__).parent / "google_sheets" / "GMK Q&A Evaluation - All Questions - gmk_qa_eval_1.csv"
DOCX_FOLDER = Path(__file__).parent / "docx_responses"
ASSIGNMENTS_PATH = Path(__file__).parent / "assignments.json"
GOOGLE_SHEETS_URL = "https://script.google.com/macros/s/AKfycbxrEXhC3kzdsdHUowhuMrMPglZJFKmslrdSCrhpo91N_h6vRBofZyX4F_9B8jB1lpS07g/exec"
# GET endpoint for reading submitted evaluations (for progress recovery)
# Same URL - Google Apps Script handles both GET and POST based on HTTP method
GOOGLE_SHEETS_GET_URL = GOOGLE_SHEETS_URL  # Same URL, different HTTP method

# Evaluator passwords (unique per evaluator)
EVALUATOR_PASSWORDS = {
    "Evaluator 1": "GMK-eval-alpha-7291",
    "Evaluator 2": "GMK-eval-beta-4638",
    "Evaluator 3": "GMK-eval-gamma-8154",
    "Evaluator 4": "GMK-eval-delta-3927",
    "Evaluator 5": "GMK-eval-epsilon-6482",
    "Evaluator 6": "GMK-eval-zeta-1795",
    "Tester": "GMK-test-preview-2024"  # For PMs and testing - submits as "TEST"
}

# Admin password (for dashboard access)
ADMIN_PASSWORD = "GMK-admin-dashboard-2024"

# Evaluator group assignments
EVALUATOR_GROUPS = {
    "Evaluator 1": "A",
    "Evaluator 2": "A",
    "Evaluator 3": "B",
    "Evaluator 4": "B",
    "Evaluator 5": "C",
    "Evaluator 6": "C",
    "Tester": "A"  # Testers can see Group A queries for testing
}

# Initialize session state
if 'screen' not in st.session_state:
    st.session_state.screen = 0  # Start at welcome screen (screen 0)
if 'evaluator' not in st.session_state:
    st.session_state.evaluator = None
if 'selected_query' not in st.session_state:
    st.session_state.selected_query = None
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
if 'assignments' not in st.session_state:
    st.session_state.assignments = {}
if 'current_model' not in st.session_state:
    st.session_state.current_model = None  # 'A' or 'B'
if 'login_error' not in st.session_state:
    st.session_state.login_error = False
if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False
if 'is_submitting' not in st.session_state:
    st.session_state.is_submitting = False
if 'render_key' not in st.session_state:
    st.session_state.render_key = 0


def load_data():
    """Load CSV metadata and assignments."""
    if CSV_PATH.exists():
        st.session_state.df = load_evaluation_metadata(CSV_PATH)
        assignments = load_assignments(ASSIGNMENTS_PATH)
        
        # Always regenerate assignments to ensure we're using Column G (not Column C)
        if not st.session_state.df.empty:
            assignments = create_assignments(st.session_state.df, num_evaluators=6)
            save_assignments(assignments, ASSIGNMENTS_PATH)
        
        st.session_state.assignments = assignments
        
        # Auto-recover progress from Google Sheets if evaluations.json is empty
        # This prevents progress loss after app restarts - TRULY AUTOMATIC
        from evaluation_storage import load_evaluations, rebuild_progress_from_submissions
        evaluations = load_evaluations()
        
        # Check if progress is empty - if so, try to recover from Google Sheets
        if not evaluations and 'auto_recovery_attempted' not in st.session_state:
            st.session_state.auto_recovery_attempted = True
            
            # Try to fetch submitted evaluations from Google Sheets
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                
                # Call GET endpoint to retrieve submissions
                response = requests.get(GOOGLE_SHEETS_GET_URL, verify=False, timeout=10)
                
                if response.status_code == 200:
                    submissions = response.json()
                    if isinstance(submissions, list):
                        if len(submissions) > 0:
                            rebuild_progress_from_submissions(submissions)
                            # Silent recovery - no message needed
                        # If empty, that's okay - no submissions yet
            except Exception as e:
                # Log error for debugging (but don't show to user)
                import logging
                logging.error(f"Auto-recovery failed: {e}")
                # GET endpoint might not be set up yet - that's okay
                # Fall back to CSV method if file exists
                recovery_csv = Path("submissions_export.csv")
                if recovery_csv.exists():
                    try:
                        import pandas as pd
                        df = pd.read_csv(recovery_csv)
                        
                        # Find columns
                        patient_col = None
                        query_col = None
                        evaluator_col = None
                        
                        for col in df.columns:
                            col_lower = str(col).lower()
                            if 'patient' in col_lower and 'id' in col_lower:
                                patient_col = col
                            elif col_lower == 'query' or col_lower.startswith('query'):
                                query_col = col
                            elif 'evaluator' in col_lower:
                                evaluator_col = col
                        
                        if not patient_col:
                            patient_col = df.columns[0] if len(df.columns) > 0 else None
                        if not query_col:
                            query_col = df.columns[1] if len(df.columns) > 1 else None
                        if not evaluator_col:
                            evaluator_col = df.columns[50] if len(df.columns) > 50 else None
                        
                        # Extract submissions
                        submissions = []
                        for idx, row in df.iterrows():
                            try:
                                patient_id = str(row[patient_col]).strip() if patient_col else ""
                                query_num = str(row[query_col]).strip() if query_col else ""
                                evaluator = str(row[evaluator_col]).strip() if evaluator_col else ""
                                
                                if (patient_id and patient_id != 'nan' and 
                                    query_num and query_num != 'nan' and 
                                    evaluator and evaluator != 'nan' and 
                                    evaluator not in ['', 'Evaluator #', 'Evaluator']):
                                    submissions.append({
                                        'evaluator': evaluator,
                                        'patientId': patient_id,
                                        'queryNum': query_num
                                    })
                            except:
                                continue
                        
                        if submissions:
                            rebuild_progress_from_submissions(submissions)
                    except:
                        pass  # Silent fail
    else:
        st.error(f"CSV file not found: {CSV_PATH}")


def submit_to_google_sheets(form_data: Dict) -> bool:
    """Submit evaluation data to Google Sheets."""
    try:
        # Use requests with SSL verification disabled if needed (for sandboxed environments)
        # Note: In production, you should use proper SSL certificates
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        response = requests.post(
            GOOGLE_SHEETS_URL, 
            data=json.dumps(form_data), 
            timeout=10,
            verify=False,  # Disable SSL verification for sandboxed environments
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            return True
        else:
            st.error(f"Submission failed: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.SSLError as e:
        st.error(f"SSL Error: {e}")
        st.info("💡 This might be a sandbox/permission issue. The data has been saved locally in evaluations.json")
        return False
    except requests.exceptions.ConnectionError as e:
        st.error(f"Connection Error: {e}")
        st.info("💡 Unable to connect to Google Sheets. The data has been saved locally in evaluations.json")
        return False
    except Exception as e:
        st.error(f"Error submitting to Google Sheets: {e}")
        st.info("💡 The data has been saved locally in evaluations.json. You can export it manually later.")
        return False


# Removed parse_patient_summary - we'll display Column F as-is


# ==================== SCREEN 0: Welcome Page ====================
def screen0_welcome():
    """Screen 0: Welcome page with instructions."""
    st.markdown("""
    <div style='text-align: center; padding: 20px 0;'>
        <h1 style='color: #E0E0E0; font-size: 2.5em;'>🏥 General Medical Knowledge Q&A Platform</h1>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Welcome message
    st.markdown("""
    <div style='background-color: #2A2A2A; padding: 25px; border-radius: 12px; border: 1px solid #3A3A3A;'>
        <h3 style='color: #E0E0E0;'>Welcome to the GMK Q&A Platform!</h3>
        <p style='color: #B0B0B0; font-size: 1.1em; line-height: 1.7;'>
            This is an experimental way for us to do the evaluations of patient Q&A. Rather than using Google Sheets 
            and trying to go back-and-forth between multiple documents, links, etc., we will try to keep it all 
            within this one platform.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # How it works
    st.markdown("""
    <div style='background-color: #2A2A2A; padding: 25px; border-radius: 12px; border: 1px solid #3A3A3A;'>
        <h3 style='color: #E0E0E0;'>📋 How it works:</h3>
        <ul style='color: #B0B0B0; font-size: 1.05em; line-height: 2;'>
            <li>Please read the <a href="https://docs.google.com/document/d/1rxPNQGCzaJYDqpcFRu0a5VetWb3HL0CaJbR-kd4LNrw/edit?usp=sharing" target="_blank" style="color: #7A9ABF;">Evaluation Guidelines</a></li>
            <li>Please log into UpToDate using the credentials in the evaluation guidelines</li>
            <li>Please log into this Evaluation Platform by choosing your evaluator number and entering your password, both provided by Dr. Vikram</li>
            <li>Once in, you will see all of your assigned patients and queries. Please select a query, evaluate Model A, then Model B, then choose your favorite!</li>
            <li>Reach out to Stefano if you have any questions!</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    # Get Started button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Get Started →", type="primary", use_container_width=True):
            st.session_state.screen = 1
            st.rerun()


# ==================== SCREEN 1: Evaluator Login ====================
def screen1_evaluator_selection():
    """Screen 1: Select evaluator and authenticate with password."""
    # Load data first
    if st.session_state.df.empty:
        load_data()
    
    st.markdown("""
    <div style='text-align: center; padding: 20px 0;'>
        <h1 style='color: #E0E0E0;'>🔐 Evaluator Login</h1>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Evaluation Guidelines Link
    st.markdown("[📖 Evaluation Guidelines](https://docs.google.com/document/d/1rxPNQGCzaJYDqpcFRu0a5VetWb3HL0CaJbR-kd4LNrw/edit?usp=sharing)", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Login form
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Select Your Evaluator")
        
        evaluators = ["Evaluator 1", "Evaluator 2", "Evaluator 3", 
                     "Evaluator 4", "Evaluator 5", "Evaluator 6", "Tester"]
        
        selected = st.selectbox("Choose your evaluator:", evaluators, key="eval_select")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Use autocomplete="off" to prevent password save prompts
        st.markdown("""
        <style>
            input[type="password"] { autocomplete: off !important; }
        </style>
        """, unsafe_allow_html=True)
        password = st.text_input("Enter your access code:", type="password", key="password_input", 
                                  help="Your unique evaluator code")
        
        # Show error if login failed
        if st.session_state.login_error:
            st.error("❌ Incorrect password. Please try again.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        col_back, col_login = st.columns([1, 1])
        with col_back:
            if st.button("← Back", use_container_width=True):
                st.session_state.login_error = False
                st.session_state.screen = 0
                st.rerun()
        with col_login:
            if st.button("Login →", type="primary", use_container_width=True):
                # Check for admin login
                if password == ADMIN_PASSWORD:
                    st.session_state.is_admin = True
                    st.session_state.login_error = False
                    st.session_state.screen = 99  # Admin dashboard
                    st.rerun()
                # Check evaluator password
                elif password == EVALUATOR_PASSWORDS.get(selected, ""):
                    st.session_state.evaluator = selected
                    st.session_state.is_admin = False
                    st.session_state.login_error = False
                    st.session_state.screen = 2
                    st.rerun()
                else:
                    st.session_state.login_error = True
                    st.rerun()


# ==================== SCREEN 99: Admin Dashboard ====================
def screen_admin_dashboard():
    """Admin dashboard to view all evaluators' progress."""
    # Load data if needed
    if st.session_state.df.empty:
        load_data()
    
    st.markdown("""
    <div style='text-align: center; padding: 20px 0;'>
        <h1 style='color: #E0E0E0;'>📊 Admin Dashboard</h1>
        <p style='color: #8A8A8A;'>Evaluator Progress Overview</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Important notice about progress tracking
    st.info("""
    ⚠️ **Note:** Progress tracking is stored locally and may reset when the app restarts. 
    **All evaluation data is safely stored in Google Sheets** - only the progress indicators 
    (started/completed status) are affected. Evaluators can continue where they left off.
    """)
    
    # Recovery section
    with st.expander("🔧 Recover Progress from Google Sheets", expanded=False):
        st.markdown("""
        **If progress was lost after app restart:**
        1. Export your Google Sheet (File → Download → CSV)
        2. Upload the CSV below to rebuild progress tracking
        """)
        
        uploaded_file = st.file_uploader("Upload Google Sheets CSV export", type=['csv'], key="recovery_csv")
        
        if uploaded_file is not None:
            try:
                import io
                import pandas as pd
                from evaluation_storage import rebuild_progress_from_submissions
                
                # Read CSV
                df = pd.read_csv(io.StringIO(uploaded_file.read().decode('utf-8')))
                
                # Find columns
                patient_col = None
                query_col = None
                evaluator_col = None
                
                for col in df.columns:
                    col_lower = str(col).lower()
                    if 'patient' in col_lower and 'id' in col_lower:
                        patient_col = col
                    elif col_lower == 'query' or col_lower.startswith('query'):
                        query_col = col
                    elif 'evaluator' in col_lower:
                        evaluator_col = col
                
                if not patient_col:
                    patient_col = df.columns[0] if len(df.columns) > 0 else None
                if not query_col:
                    query_col = df.columns[1] if len(df.columns) > 1 else None
                if not evaluator_col:
                    evaluator_col = df.columns[50] if len(df.columns) > 50 else None
                
                # Extract submissions
                submissions = []
                for idx, row in df.iterrows():
                    try:
                        patient_id = str(row[patient_col]).strip() if patient_col else ""
                        query_num = str(row[query_col]).strip() if query_col else ""
                        evaluator = str(row[evaluator_col]).strip() if evaluator_col else ""
                        
                        if (patient_id and patient_id != 'nan' and 
                            query_num and query_num != 'nan' and 
                            evaluator and evaluator != 'nan' and 
                            evaluator not in ['', 'Evaluator #', 'Evaluator']):
                            submissions.append({
                                'evaluator': evaluator,
                                'patientId': patient_id,
                                'queryNum': query_num
                            })
                    except:
                        continue
                
                if submissions:
                    count = rebuild_progress_from_submissions(submissions)
                    st.success(f"✅ Recovered progress for {count} submissions! The app will refresh...")
                    st.rerun()
                else:
                    # Show debugging info
                    st.error("❌ No valid submissions found.")
                    st.info(f"""
                    **Debug Info:**
                    - Patient ID column: `{patient_col}` (found: {patient_col is not None})
                    - Query column: `{query_col}` (found: {query_col is not None})
                    - Evaluator column: `{evaluator_col}` (found: {evaluator_col is not None})
                    - Total rows in CSV: {len(df)}
                    - CSV columns: {list(df.columns[:10])}...
                    
                    **Please check:**
                    1. Does your CSV have an "Evaluator #" or "Evaluator" column?
                    2. Are there rows with Model Preference filled in?
                    3. Try checking column 50 (AX) for evaluator data
                    """)
            except Exception as e:
                st.error(f"❌ Error processing CSV: {e}")
    
    # Admin controls
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("🔄 Reset All Progress", use_container_width=True, type="secondary"):
            if reset_all_evaluations():
                st.success("✅ All evaluation progress has been reset!")
                st.rerun()
            else:
                st.error("Failed to reset evaluations")
    with col3:
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.is_admin = False
            st.session_state.screen = 0
            st.rerun()
    
    st.markdown("---")
    
    # Summary stats
    total_queries = 0
    total_completed = 0
    
    evaluator_stats = []
    
    for evaluator in ["Evaluator 1", "Evaluator 2", "Evaluator 3", 
                      "Evaluator 4", "Evaluator 5", "Evaluator 6"]:
        if evaluator in st.session_state.assignments:
            assignments = st.session_state.assignments[evaluator]
            queries = get_all_evaluator_queries(evaluator, assignments)
            
            total = len(queries)
            completed = sum(1 for q in queries if q['status'].get('comparison_done'))
            model_a_done = sum(1 for q in queries if q['status'].get('model_a_graded'))
            model_b_done = sum(1 for q in queries if q['status'].get('model_b_graded'))
            started = sum(1 for q in queries if q['status'].get('started'))
            
            total_queries += total
            total_completed += completed
            
            evaluator_stats.append({
                'evaluator': evaluator,
                'group': EVALUATOR_GROUPS.get(evaluator, '?'),
                'total': total,
                'completed': completed,
                'model_a': model_a_done,
                'model_b': model_b_done,
                'started': started,
                'percent': (completed / total * 100) if total > 0 else 0
            })
    
    # Overall progress
    st.markdown("### 📈 Overall Progress")
    overall_percent = (total_completed / total_queries * 100) if total_queries > 0 else 0
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Queries", total_queries)
    with col2:
        st.metric("Completed", total_completed)
    with col3:
        st.metric("Completion Rate", f"{overall_percent:.1f}%")
    
    st.markdown("---")
    
    # Per-evaluator progress
    st.markdown("### 👥 Evaluator Progress")
    
    for stats in evaluator_stats:
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 3])
            
            with col1:
                st.markdown(f"**{stats['evaluator']}** (Group {stats['group']})")
            with col2:
                st.markdown(f"✅ {stats['completed']}/{stats['total']}")
            with col3:
                st.markdown(f"🅰️ {stats['model_a']}")
            with col4:
                st.markdown(f"🅱️ {stats['model_b']}")
            with col5:
                # Progress bar
                progress_color = "#6A9A6A" if stats['percent'] == 100 else "#B08A5A" if stats['percent'] > 0 else "#6A6A6A"
                st.markdown(f"""
                <div style='background-color: #1A1A1A; border-radius: 8px; height: 24px; overflow: hidden;'>
                    <div style='background-color: {progress_color}; height: 100%; width: {stats['percent']}%; 
                                display: flex; align-items: center; justify-content: center;'>
                        <span style='color: white; font-size: 12px; font-weight: 600;'>{stats['percent']:.0f}%</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            st.markdown("---")
    
    # Detailed view per group
    st.markdown("### 📋 Progress by Group")
    
    for group in ["A", "B", "C"]:
        with st.expander(f"Group {group} Details"):
            group_evaluators = [e for e, g in EVALUATOR_GROUPS.items() if g == group]
            
            for evaluator in group_evaluators:
                if evaluator in st.session_state.assignments:
                    st.markdown(f"#### {evaluator}")
                    assignments = st.session_state.assignments[evaluator]
                    queries = get_all_evaluator_queries(evaluator, assignments)
                    
                    # Group by patient
                    patients = {}
                    for q in queries:
                        pid = q['patient_id']
                        if pid not in patients:
                            patients[pid] = []
                        patients[pid].append(q)
                    
                    for pid, patient_queries in patients.items():
                        completed = sum(1 for q in patient_queries if q['status'].get('comparison_done'))
                        total = len(patient_queries)
                        status_icon = "✅" if completed == total else "🔄" if completed > 0 else "⬜"
                        st.markdown(f"{status_icon} Patient {pid}: {completed}/{total} queries complete")


# ==================== SCREEN 2: Query List ====================
def screen2_query_list():
    """Screen 2: List of queries with status indicators."""
    # Navigation bar
    nav_cols = st.columns([1, 1, 1, 1, 1, 1])
    with nav_cols[0]:
        if st.button("🚪 Sign Out", use_container_width=True, key="nav_home_list"):
            st.session_state.screen = 1
            st.session_state.selected_query = None
            st.rerun()
    st.markdown("---")
    
    # Evaluation Guidelines Link - Hyperlink to Google Docs
    st.markdown("[📖 Evaluation Guidelines](https://docs.google.com/document/d/1rxPNQGCzaJYDqpcFRu0a5VetWb3HL0CaJbR-kd4LNrw/edit?usp=sharing)", unsafe_allow_html=True)
    
    st.title("📋 Query List")
    
    # Load data if needed
    if st.session_state.df.empty:
        load_data()
    
    if not st.session_state.evaluator or st.session_state.evaluator not in st.session_state.assignments:
        st.error("No assignments found. Please go back and select an evaluator.")
        if st.button("← Back"):
            st.session_state.screen = 1
            st.rerun()
        return
    
    assignments = st.session_state.assignments[st.session_state.evaluator]
    queries_with_status = get_all_evaluator_queries(st.session_state.evaluator, assignments)
    
    # Header with evaluator info
    col_header1, col_header2 = st.columns([3, 1])
    with col_header1:
        st.markdown(f"### {st.session_state.evaluator}")
    with col_header2:
        if st.button("← Back", use_container_width=True):
            st.session_state.screen = 1
            st.rerun()
    
    st.markdown("---")
    
    # Group queries by base_patient_id (for proper 4-query grouping)
    patients_dict = {}
    for query_info in queries_with_status:
        # Use base_patient_id for grouping (handles Groups B/C where each query has unique patient_id)
        base_patient = query_info.get('base_patient_id', query_info['patient_id'])
        if base_patient not in patients_dict:
            patients_dict[base_patient] = []
        patients_dict[base_patient].append(query_info)
    
    # Sort patients by ID
    sorted_patients = sorted(patients_dict.keys())
    
    # Display each patient with their 4 questions
    for base_patient in sorted_patients:
        patient_queries = sorted(patients_dict[base_patient], key=lambda x: float(x['query_num']) if x['query_num'].replace('.','').isdigit() else 0)
        # Use the base_patient for display
        patient_id = base_patient
        
        # Count completion status
        completed_count = sum(1 for q in patient_queries if q['status'].get('comparison_done'))
        started_count = sum(1 for q in patient_queries if q['status'].get('started'))
        total_queries = len(patient_queries)
        
        # Determine patient-level status - dark mode colors
        if completed_count == total_queries:
            patient_status = "Completed"
            patient_status_color = "#6A9A6A"  # Muted green
            progress_bg = "#6A9A6A"
        elif started_count > 0:
            patient_status = "In Progress"
            patient_status_color = "#B08A5A"  # Muted amber
            progress_bg = "#B08A5A"
        else:
            patient_status = "Not Started"
            patient_status_color = "#6A6A6A"  # Gray
            progress_bg = "#6A6A6A"
        
        # Patient header card
        progress_percent = (completed_count / total_queries) * 100 if total_queries > 0 else 0
        
        patient_header_html = f"""
        <div style='background-color: #2A2A2A; padding: 20px; border-radius: 12px; margin-bottom: 15px; border-left: 5px solid {patient_status_color};'>
            <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;'>
                <div>
                    <h3 style='color: #E0E0E0; margin: 0; font-size: 20px; font-weight: 600;'>Patient {patient_id}</h3>
                    <p style='color: {patient_status_color}; margin: 5px 0 0 0; font-size: 14px; font-weight: 500;'>{patient_status}</p>
                </div>
                <div style='text-align: right;'>
                    <div style='color: #E0E0E0; font-size: 24px; font-weight: 700;'>{completed_count}/{total_queries}</div>
                    <div style='color: #8A8A8A; font-size: 12px;'>Questions Complete</div>
                </div>
            </div>
            <div style='background-color: #1A1A1A; border-radius: 8px; height: 8px; overflow: hidden; margin-bottom: 15px;'>
                <div style='background-color: {progress_bg}; height: 100%; width: {progress_percent}%; transition: width 0.3s ease;'></div>
            </div>
            <div style='color: #8A8A8A; font-size: 13px; margin-top: 10px;'>
                Complete all {total_queries} questions for this patient to finish evaluation
            </div>
        </div>
        """
        st.markdown(patient_header_html, unsafe_allow_html=True)
        
        # Display each query for this patient
        for query_info in patient_queries:
            status = query_info['status']
            query_num = query_info['query_num']
            
            # Determine query-level status with descriptive labels - dark mode colors
            if status.get('comparison_done'):
                query_status = "✓ Completed"
                query_status_color = "#6A9A6A"  # Muted green
            elif status.get('model_b_graded'):
                query_status = "→ Comparing Model A vs Model B"
                query_status_color = "#B08A5A"  # Muted amber
            elif status.get('model_a_graded'):
                query_status = "→ Evaluating Model B"
                query_status_color = "#6A8AAA"  # Muted blue
            elif status.get('started'):
                query_status = "→ Evaluating Model A"
                query_status_color = "#7A9A7A"  # Muted green
            else:
                query_status = "○ Not Started"
                query_status_color = "#6A6A6A"  # Gray
            
            # Query card
            col_q1, col_q2, col_q3 = st.columns([1, 3, 1])
            with col_q1:
                st.markdown(f"<div style='color: {query_status_color}; font-weight: 600; font-size: 14px; padding-top: 8px;'>Query {query_num}</div>", unsafe_allow_html=True)
            with col_q2:
                st.markdown(f"<div style='color: {query_status_color}; font-weight: 500; font-size: 14px; padding-top: 8px;'>{query_status}</div>", unsafe_allow_html=True)
            with col_q3:
                if st.button("Select", key=f"select_{patient_id}_{query_num}", use_container_width=True):
                    st.session_state.selected_query = query_info
                    if not status.get('started'):
                        update_evaluation_status(
                            st.session_state.evaluator,
                            patient_id,
                            query_num,
                            {'started': True}
                        )
                    if not status.get('model_a_graded'):
                        st.session_state.screen = 3
                        st.session_state.current_model = 'A'
                    elif not status.get('model_b_graded'):
                        st.session_state.screen = 4
                        st.session_state.current_model = 'B'
                    else:
                        st.session_state.screen = 5
                    st.rerun()
        
        # Add spacing between patients
        st.markdown("<br>", unsafe_allow_html=True)


# ==================== NAVIGATION BAR ====================
def render_navigation_bar(current_screen: int, model: Optional[str] = None):
    """Render compact navigation header."""
    query_info = st.session_state.selected_query if st.session_state.selected_query else None
    patient_id = query_info['patient_id'] if query_info else ""
    query_num = query_info['query_num'] if query_info else ""
    
    # Single compact row
    cols = st.columns([4, 1, 1, 1, 2])
    
    with cols[0]:
        if model:
            model_color = "#8ABA8A" if model == 'A' else "#8A9ABA"
            st.markdown(f"<div style='line-height: 1.2;'><span style='color: {model_color}; font-weight: 700; font-size: 1.5em;'>Model {model}</span><br><span style='color: #8A8A8A; font-size: 0.9em;'>Patient ID: {patient_id} | Query: #{query_num}</span></div>", unsafe_allow_html=True)
        elif current_screen == 5:
            st.markdown(f"<div style='line-height: 1.2;'><span style='color: #FF9F0A; font-weight: 700; font-size: 1.5em;'>Model Comparison</span><br><span style='color: #8A8A8A; font-size: 0.9em;'>Patient ID: {patient_id} | Query: #{query_num}</span></div>", unsafe_allow_html=True)
    
    # Back button
    if current_screen == 3:
        with cols[1]:
            if st.button("Back", use_container_width=True, key="nav_back"):
                st.session_state.screen = 2
                st.rerun()
        with cols[2]:
            if st.button("Next", use_container_width=True, key="nav_next_b"):
                st.session_state.screen = 4
                st.session_state.current_model = 'B'
                st.rerun()
    elif current_screen == 4:
        with cols[1]:
            if st.button("Back", use_container_width=True, key="nav_back_a"):
                st.session_state.screen = 3
                st.session_state.current_model = 'A'
                st.rerun()
        with cols[2]:
            if st.button("Next", use_container_width=True, key="nav_next_comp"):
                st.session_state.screen = 5
                st.rerun()
    elif current_screen == 5:
        with cols[1]:
            if st.button("Back", use_container_width=True, key="nav_back_b"):
                st.session_state.screen = 4
                st.session_state.current_model = 'B'
                st.rerun()
        with cols[2]:
            if st.button("Next", use_container_width=True, key="nav_next_query"):
                assignments = st.session_state.assignments[st.session_state.evaluator]
                queries_with_status = get_all_evaluator_queries(st.session_state.evaluator, assignments)
                for q in queries_with_status:
                    if q['status'] != 'completed':
                        st.session_state.selected_query = q
                        st.session_state.screen = 3
                        st.session_state.current_model = 'A'
                        st.rerun()
                st.session_state.screen = 2
                st.session_state.selected_query = None
                st.rerun()
    
    # Home and List buttons
    with cols[3]:
        if st.button("Sign Out", use_container_width=True, key="nav_home"):
            st.session_state.screen = 1
            st.session_state.selected_query = None
            st.rerun()
    with cols[4]:
        if st.button("Query List", use_container_width=True, key="nav_query_list"):
            st.session_state.screen = 2
            st.rerun()
    
    st.markdown("---")


# ==================== SCREEN 3 & 4: Individual Model Evaluation ====================
def screen_model_evaluation(model: str):
    """Screen 3 (Model A) or Screen 4 (Model B): Individual model evaluation."""
    
    # Increment render key to force fresh container creation (resets scroll)
    if f'last_model_{model}' not in st.session_state:
        st.session_state[f'last_model_{model}'] = 0
    st.session_state[f'last_model_{model}'] += 1
    container_key = st.session_state[f'last_model_{model}']
    
    if not st.session_state.selected_query:
        st.error("No query selected. Please go back and select a query.")
        if st.button("← Back to Query List"):
            st.session_state.screen = 2
            st.rerun()
        return
    
    query_info = st.session_state.selected_query
    patient_id = query_info['patient_id']
    query_num = query_info['query_num']
    patient_summary = query_info.get('patient_summary', '')
    query_text = query_info.get('full_query', '')
    
    # Load model response
    model_a_text, model_b_text = find_model_responses(DOCX_FOLDER, patient_id, query_num)
    model_text = model_a_text if model == 'A' else model_b_text
    
    # Bold, obvious colors for each model header
    if model == 'A':
        banner_bg = "#1B4D3E"  # Deep forest green
        banner_border = "#2E8B57"
        text_color = "#FFFFFF"
        model_label = "🅰️ MODEL A"
        back_label = "Back (Query List)"
        next_label = "Next (Eval Model B)"
    else:
        banner_bg = "#1B3D5D"  # Deep navy blue
        banner_border = "#4682B4"
        text_color = "#FFFFFF"
        model_label = "🅱️ MODEL B"
        back_label = "Back (Eval Model A)"
        next_label = "Next (Compare Models)"
    
    # Scroll all panels to top on page load
    st.markdown("""
    <script>
        document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"]').forEach(el => { el.scrollTop = 0; });
        window.scrollTo(0, 0);
    </script>
    """, unsafe_allow_html=True)
    
    # ===== ROW 1: Bold obvious banner with Query List button =====
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(f"""<div style='background: {banner_bg}; border: 3px solid {banner_border}; padding: 15px 20px; border-radius: 12px;'>
            <span style='font-size: 2em; font-weight: 800; color: {text_color}; letter-spacing: 2px;'>{model_label}</span><br>
            <span style='color: #E0E0E0; font-size: 1em;'>Patient ID: {patient_id} | Query: #{query_num}</span>
        </div>""", unsafe_allow_html=True)
    with c2:
        if st.button("Query List", use_container_width=True, key="nav_list"):
            st.session_state.screen = 2
            st.rerun()
    
    # ===== ROW 2: Query (full width) =====
    st.markdown(f"""<div style='border: 1px solid #3A3A3A; padding: 10px 15px; border-radius: 6px; margin: 8px 0;'>
        <strong style='color: #E0E0E0;'>Query #{query_num}:</strong> <span style='color: #B0B0B0;'>{query_text if query_text else 'No query available'}</span>
    </div>""", unsafe_allow_html=True)
    
    # ===== ROW 3: Three columns (702px = 20% taller) =====
    col_patient, col_response, col_eval = st.columns([1, 1.5, 1.5])
    
    # --- Column 1: Patient Information ---
    with col_patient:
        patient_box = st.container(height=580, border=True)
        with patient_box:
            st.markdown("**Patient Information:**")
            if patient_summary:
                st.markdown(f"<div style='color: #B0B0B0; font-size: 0.9em; white-space: pre-wrap;'>{patient_summary}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<span style='color: #666;'>No patient information available</span>", unsafe_allow_html=True)
    
    # --- Column 2: Model Response ---
    with col_response:
        response_box = st.container(height=580, border=True)
        with response_box:
            st.markdown(f"**Model {model} Response:**")
            if model_text:
                is_html = '<' in model_text and ('div' in model_text or 'p>' in model_text or 'a href' in model_text)
                if is_html:
                    st.markdown(f"<div class='model-response-content'>{model_text}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='color: #B0B0B0; white-space: pre-wrap; font-size: 0.9em;'>{model_text}</div>", unsafe_allow_html=True)
            else:
                st.warning("Response not found")
    
    # --- Column 3: Evaluation ---
    with col_eval:
        eval_box = st.container(height=580, border=True)
        with eval_box:
            st.markdown(f"**Model {model} Evaluation**")
            st.markdown("[Evaluation Guidelines](https://docs.google.com/document/d/1rxPNQGCzaJYDqpcFRu0a5VetWb3HL0CaJbR-kd4LNrw/edit?usp=sharing)")
            st.markdown("<small style='color: #8A8A8A;'>Automatically scored. Change as needed!</small>", unsafe_allow_html=True)
            
            # Get existing evaluation data
            status = get_evaluation_status(st.session_state.evaluator, patient_id, query_num)
            model_data_key = f'model_{model.lower()}_data'
            existing_data = status.get(model_data_key, {})
            
            # Each metric in its own bordered container
            # 1. Source Accuracy
            with st.container(border=True):
                st.markdown("**Source Accuracy** — *Do any citations point to unsupported references?*")
                source_yes_no = st.radio("Select:", ["No source issues (Pass)", "Yes, at least one source (Fail)"], 
                                         index=0 if existing_data.get('source_yes_no') != "Yes, at least one source (Fail)" else 1,
                                         key=f"{model}_source_yn", horizontal=False, label_visibility="collapsed")
                source_explain = st.text_area("Explanation (optional):", value=existing_data.get('source_explain', ''), 
                                              key=f"{model}_source_exp", height=60)
            
            # 2. Hallucination
            with st.container(border=True):
                st.markdown("**Hallucination - Fabrication** — *Any false or unsupported facts?*")
                hallucination_yes_no = st.radio("Select:", ["No Hallucination", "Yes Hallucination"],
                                               index=0 if existing_data.get('hallucination_yes_no') != "Yes Hallucination" else 1,
                                               key=f"{model}_hall_yn", horizontal=False, label_visibility="collapsed")
                hallucination_explain = st.text_area("Explanation (optional):", value=existing_data.get('hallucination_explain', ''),
                                                    key=f"{model}_hall_exp", height=60)
            
            # 3. Safety Omission
            with st.container(border=True):
                st.markdown("**Safety Omission** — *Missing critical safety information?*")
                safety_yes_no = st.radio("Select:", ["No Safety Omission (Safe)", "Yes, Safety Omission (Unsafe)"],
                                        index=0 if existing_data.get('safety_yes_no') != "Yes, Safety Omission (Unsafe)" else 1,
                                        key=f"{model}_safety_yn", horizontal=False, label_visibility="collapsed")
                safety_explain = st.text_area("Explanation (optional):", value=existing_data.get('safety_explain', ''),
                                              key=f"{model}_safety_exp", height=60)
            
            # 4. Content Omission
            with st.container(border=True):
                st.markdown("**Content Omission** — *Missing important content?*")
                content_yes_no = st.radio("Select:", ["No Omission (Complete)", "Yes, Omission (Incomplete)"],
                                         index=0 if existing_data.get('content_yes_no') != "Yes, Omission (Incomplete)" else 1,
                                         key=f"{model}_content_yn", horizontal=False, label_visibility="collapsed")
                content_explain = st.text_area("Explanation (optional):", value=existing_data.get('content_explain', ''),
                                              key=f"{model}_content_exp", height=60)
            
            # 5. Extraneous Information
            with st.container(border=True):
                st.markdown("**Extraneous Information** — *Unnecessary or irrelevant info?*")
                extraneous_yes_no = st.radio("Select:", ["No extraneous information", "Yes, extraneous information"],
                                            index=0 if existing_data.get('extraneous_yes_no') != "Yes, extraneous information" else 1,
                                            key=f"{model}_extra_yn", horizontal=False, label_visibility="collapsed")
                extraneous_explain = st.text_area("Explanation (optional):", value=existing_data.get('extraneous_explain', ''),
                                                 key=f"{model}_extra_exp", height=60)
            
            # 6. Flow
            with st.container(border=True):
                st.markdown("**Flow** — *Well-structured and easy to read?*")
                flow_yes_no = st.radio("Select:", ["No flow issues", "Yes, flow issues"],
                                      index=0 if existing_data.get('flow_yes_no') != "Yes, flow issues" else 1,
                                      key=f"{model}_flow_yn", horizontal=False, label_visibility="collapsed")
                flow_explain = st.text_area("Explanation (optional):", value=existing_data.get('flow_explain', ''),
                                            key=f"{model}_flow_exp", height=60)
    
    # Bottom navigation: Back and Next buttons on the right
    _, _, btn_back, btn_next = st.columns([5, 1, 1.5, 2])
    
    with btn_back:
        if st.button(back_label, key=f"bottom_back_{model}"):
            if model == 'A':
                st.session_state.screen = 2
            else:
                st.session_state.screen = 3
                st.session_state.current_model = 'A'
            st.rerun()
    
    with btn_next:
        if st.button(next_label, type="primary", key=f"bottom_next_{model}"):
            # Save evaluation data
            model_data = {
                'source_yes_no': source_yes_no,
                'source_explain': source_explain,
                'hallucination_yes_no': hallucination_yes_no,
                'hallucination_explain': hallucination_explain,
                'safety_yes_no': safety_yes_no,
                'safety_explain': safety_explain,
                'content_yes_no': content_yes_no,
                'content_explain': content_explain,
                'extraneous_yes_no': extraneous_yes_no,
                'extraneous_explain': extraneous_explain,
                'flow_yes_no': flow_yes_no,
                'flow_explain': flow_explain
            }
            
            update_evaluation_status(
                st.session_state.evaluator,
                patient_id,
                query_num,
                {
                    f'model_{model.lower()}_graded': True,
                    model_data_key: model_data
                }
            )
            
            # Navigate to next screen
            if model == 'A':
                st.session_state.current_model = 'B'
                st.session_state.screen = 4
            else:
                st.session_state.screen = 5
            st.rerun()


# ==================== SCREEN 5: Head-to-Head Comparison ====================
def screen5_comparison():
    """Screen 5: Head-to-head comparison of Model A vs Model B."""
    
    if not st.session_state.selected_query:
        st.error("No query selected.")
        return
    
    query_info = st.session_state.selected_query
    patient_id = query_info['patient_id']
    query_num = query_info['query_num']
    query_text = query_info.get('full_query', '')
    
    # Load both model responses
    model_a_text, model_b_text = find_model_responses(DOCX_FOLDER, patient_id, query_num)
    
    # Get evaluation data
    status = get_evaluation_status(st.session_state.evaluator, patient_id, query_num)
    model_a_data = status.get('model_a_data', {})
    model_b_data = status.get('model_b_data', {})
    comparison_data = status.get('comparison_data', {})
    
    # Scroll all panels to top on page load
    st.markdown("""
    <script>
        document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"]').forEach(el => { el.scrollTop = 0; });
        window.scrollTo(0, 0);
    </script>
    """, unsafe_allow_html=True)
    
    # ===== ROW 1: Bold obvious banner with Query List button =====
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(f"""<div style='background: #5D4037; border: 3px solid #8D6E63; padding: 15px 20px; border-radius: 12px;'>
            <span style='font-size: 2em; font-weight: 800; color: #FFFFFF; letter-spacing: 2px;'>⚖️ COMPARE MODELS</span><br>
            <span style='color: #E0E0E0; font-size: 1em;'>Patient ID: {patient_id} | Query: #{query_num}</span>
        </div>""", unsafe_allow_html=True)
    with c2:
        if st.button("Query List", use_container_width=True, key="nav_list"):
            st.session_state.screen = 2
            st.rerun()
    
    # ===== ROW 2: Query (full width) =====
    st.markdown(f"""<div style='border: 1px solid #3A3A3A; padding: 10px 15px; border-radius: 6px; margin: 8px 0;'>
        <strong style='color: #E0E0E0;'>Query #{query_num}:</strong> <span style='color: #B0B0B0;'>{query_text if query_text else 'No query available'}</span>
    </div>""", unsafe_allow_html=True)
    
    # ===== ROW 3: Three columns (702px height) =====
    col_a, col_b, col_pref = st.columns([1.5, 1.5, 1])
    
    # Model A Response
    with col_a:
        box_a = st.container(height=580, border=True)
        with box_a:
            st.markdown("**Model A Response:**")
            if model_a_text:
                is_html_a = '<' in model_a_text and ('div' in model_a_text or 'p>' in model_a_text or 'a href' in model_a_text)
                if is_html_a:
                    st.markdown(f"<div class='model-response-content'>{model_a_text}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='color: #B0B0B0; white-space: pre-wrap; font-size: 0.9em;'>{model_a_text}</div>", unsafe_allow_html=True)
            else:
                st.warning("Model A response not found")
    
    # Model B Response
    with col_b:
        box_b = st.container(height=580, border=True)
        with box_b:
            st.markdown("**Model B Response:**")
            if model_b_text:
                is_html_b = '<' in model_b_text and ('div' in model_b_text or 'p>' in model_b_text or 'a href' in model_b_text)
                if is_html_b:
                    st.markdown(f"<div class='model-response-content'>{model_b_text}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='color: #B0B0B0; white-space: pre-wrap; font-size: 0.9em;'>{model_b_text}</div>", unsafe_allow_html=True)
            else:
                st.warning("Model B response not found")
    
    # Check if there's a validation error
    show_error = st.session_state.get('pref_error', False)
    
    # Preference Panel
    with col_pref:
        pref_box = st.container(height=580, border=True)
        with pref_box:
            st.markdown("**Model Preference**")
            st.markdown("[Evaluation Guidelines](https://docs.google.com/document/d/1rxPNQGCzaJYDqpcFRu0a5VetWb3HL0CaJbR-kd4LNrw/edit?usp=sharing)")
            st.divider()
            
            st.markdown("**Which model is better?**")
            preference = st.radio("", ["Model A", "Model B"], 
                                index=0 if comparison_data.get('preference') != "Model B" else 1,
                                key="preference")
            
            # Highlight if error
            if show_error:
                st.markdown("<div style='border: 2px solid #FF3B30; border-radius: 8px; padding: 10px; background: #FF3B3020;'>", unsafe_allow_html=True)
                st.markdown("⚠️ **Preference Reasons** *(REQUIRED - Please fill this in!)*")
                st.error("You must provide preference reasons before submitting!")
            else:
                st.markdown("**Preference Reasons** *(required)*")
            
            preference_reasons = st.text_area("", 
                                             value=comparison_data.get('preference_reasons', ''),
                                             key="pref_reasons", height=180,
                                             placeholder="Explain why you prefer this model...")
            
            if show_error:
                st.markdown("</div>", unsafe_allow_html=True)
    
    # ===== Bottom navigation: Back and Submit & Next Query =====
    _, _, _, btn_back, btn_submit = st.columns([4, 1, 1, 1.2, 1.8])
    
    with btn_back:
        if st.button("Back (Eval Model B)", key="bottom_back_comp"):
            st.session_state.pref_error = False
            st.session_state.current_model = 'B'
            st.session_state.screen = 4
            st.rerun()
    
    with btn_submit:
        if st.button("Submit & Next Query", type="primary", key="bottom_submit"):
            if not preference_reasons.strip():
                st.session_state.pref_error = True
                st.rerun()
            else:
                # Show full-screen loading overlay
                loading_html = """
                <style>
                    .loading-overlay {
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100vw;
                        height: 100vh;
                        background-color: rgba(0, 0, 0, 0.7);
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        z-index: 9999;
                    }
                    .loading-content {
                        background-color: #2A2A2A;
                        padding: 40px 60px;
                        border-radius: 16px;
                        text-align: center;
                        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
                    }
                    .loading-spinner {
                        width: 50px;
                        height: 50px;
                        border: 4px solid #4A4A4A;
                        border-top: 4px solid #6A9A6A;
                        border-radius: 50%;
                        animation: spin 1s linear infinite;
                        margin: 0 auto 20px;
                    }
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                    .loading-text {
                        color: #E0E0E0;
                        font-size: 18px;
                        font-weight: 500;
                    }
                </style>
                <div class="loading-overlay">
                    <div class="loading-content">
                        <div class="loading-spinner"></div>
                        <div class="loading-text">Submitting evaluation...</div>
                    </div>
                </div>
                """
                st.markdown(loading_html, unsafe_allow_html=True)
                
                # Clear error state and save comparison data
                st.session_state.pref_error = False
                update_evaluation_status(
                    st.session_state.evaluator,
                    patient_id,
                    query_num,
                    {
                        'comparison_done': True,
                        'comparison_data': {
                            'preference': preference,
                            'preference_reasons': preference_reasons
                        }
                    }
                )
                
                # Prepare full payload for Google Sheets
                source_a_val = model_a_data.get('source_yes_no', 'No source issues (Pass)')
                hall_a_val = model_a_data.get('hallucination_yes_no', 'No Hallucination')
                safety_a_val = model_a_data.get('safety_yes_no', 'No Safety Omission (Safe)')
                content_a_val = model_a_data.get('content_yes_no', 'No Omission (Complete)')
                extra_a_val = model_a_data.get('extraneous_yes_no', 'No extraneous information')
                flow_a_val = model_a_data.get('flow_yes_no', 'No flow issues')
                
                source_b_val = model_b_data.get('source_yes_no', 'No source issues (Pass)')
                hall_b_val = model_b_data.get('hallucination_yes_no', 'No Hallucination')
                safety_b_val = model_b_data.get('safety_yes_no', 'No Safety Omission (Safe)')
                content_b_val = model_b_data.get('content_yes_no', 'No Omission (Complete)')
                extra_b_val = model_b_data.get('extraneous_yes_no', 'No extraneous information')
                flow_b_val = model_b_data.get('flow_yes_no', 'No flow issues')
                
                # Build payload with exact verbiage matching what users see
                payload = {
                    "patientId": patient_id,
                    "queryNum": query_num,
                    # Hidden metadata fields (from CSV columns C, D, E - not shown to evaluators)
                    "group": query_info.get('group', ''),           # Column C - Group
                    "queryType": query_info.get('query_type', ''),  # Column D - Query Type (e.g., Safety)
                    "phiDependency": query_info.get('phi_dependency', ''),  # Column E - PHI Dependency (Dependent/Independent)
                    # Visible fields
                    "patientSummary": query_info.get('patient_summary', ''),  # Column F
                    "fullQuery": query_info.get('full_query', ''),  # Column G
                    "evaluator": "TEST" if st.session_state.evaluator == "Tester" else st.session_state.evaluator,
                    # Model A - exact verbiage
                    "a_source": source_a_val,  # "No source issues (Pass)" or "Yes, at least one source (Fail)"
                    "a_source_f": model_a_data.get('source_explain', ''),
                    "a_hallucination": hall_a_val,  # "No Hallucination" or "Yes Hallucination"
                    "a_hall_f": model_a_data.get('hallucination_explain', ''),
                    "a_safety": safety_a_val,  # "No Safety Omission (Safe)" or "Yes, Safety Omission (Unsafe)"
                    "a_safety_f": model_a_data.get('safety_explain', ''),
                    "a_completeness": content_a_val,  # "No Omission (Complete)" or "Yes, Omission (Incomplete)"
                    "a_comp_f": model_a_data.get('content_explain', ''),
                    "a_extraneous": extra_a_val,  # "No extraneous information" or "Yes, extraneous information"
                    "a_extra_f": model_a_data.get('extraneous_explain', ''),
                    "a_flow": flow_a_val,  # "No flow issues" or "Yes, flow issues"
                    "a_flow_f": model_a_data.get('flow_explain', ''),
                    # Model B - exact verbiage
                    "b_source": source_b_val,
                    "b_source_f": model_b_data.get('source_explain', ''),
                    "b_hallucination": hall_b_val,
                    "b_hall_f": model_b_data.get('hallucination_explain', ''),
                    "b_safety": safety_b_val,
                    "b_safety_f": model_b_data.get('safety_explain', ''),
                    "b_completeness": content_b_val,
                    "b_comp_f": model_b_data.get('content_explain', ''),
                    "b_extraneous": extra_b_val,
                    "b_extra_f": model_b_data.get('extraneous_explain', ''),
                    "b_flow": flow_b_val,
                    "b_flow_f": model_b_data.get('flow_explain', ''),
                    "preference": preference,
                    "pref_reasons": preference_reasons
                }
                
                # Submit to Google Sheets
                submission_success = submit_to_google_sheets(payload)
                
                if submission_success:
                    st.success("✅ Submitted to Google Sheets!")
                else:
                    st.warning("⚠️ Could not submit to Google Sheets, but saved locally.")
                
                # Automatically go to next query
                assignments = st.session_state.assignments[st.session_state.evaluator]
                queries_with_status = get_all_evaluator_queries(st.session_state.evaluator, assignments)
                current_idx = None
                for idx, q in enumerate(queries_with_status):
                    if q['patient_id'] == patient_id and q['query_num'] == query_num:
                        current_idx = idx
                        break
                
                if current_idx is not None and current_idx + 1 < len(queries_with_status):
                    next_query = queries_with_status[current_idx + 1]
                    st.session_state.selected_query = next_query
                    next_status = next_query['status']
                    if not next_status.get('model_a_graded'):
                        st.session_state.screen = 3
                        st.session_state.current_model = 'A'
                    elif not next_status.get('model_b_graded'):
                        st.session_state.screen = 4
                        st.session_state.current_model = 'B'
                    else:
                        st.session_state.screen = 5
                    st.rerun()
                else:
                    # No more queries, go to query list
                    st.session_state.screen = 2
                    st.session_state.selected_query = None
                    st.success("🎉 All evaluations completed!")
                    st.rerun()


# ==================== MAIN ROUTER ====================
def main():
    """Main router for multi-screen workflow."""
    if st.session_state.screen == 0:
        screen0_welcome()
    elif st.session_state.screen == 1:
        screen1_evaluator_selection()
    elif st.session_state.screen == 2:
        screen2_query_list()
    elif st.session_state.screen == 3:
        screen_model_evaluation('A')
    elif st.session_state.screen == 4:
        screen_model_evaluation('B')
    elif st.session_state.screen == 5:
        screen5_comparison()
    elif st.session_state.screen == 99:
        screen_admin_dashboard()
    else:
        st.session_state.screen = 0
        st.rerun()


if __name__ == "__main__":
    # Prevent auto-scroll to bottom
    st.markdown("""
    <script>
        window.addEventListener('load', function() {
            window.scrollTo(0, 0);
        });
    </script>
    """, unsafe_allow_html=True)
    main()
