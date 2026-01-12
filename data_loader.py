"""
Data Loader for Medical Evaluation Platform
Handles CSV metadata reading and evaluator assignment management.
"""

import pandas as pd
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import streamlit as st


def get_base_patient_id(patient_id: str, row_index_in_group: int) -> str:
    """
    Extract base patient ID.
    
    Since each patient has 4 consecutive rows in the CSV, we use the row index
    divided by 4 to determine which patient group a row belongs to.
    
    Args:
        patient_id: The patient ID from the row
        row_index_in_group: The 0-based index of this row within its group
        
    Returns:
        A base patient identifier (patient_index within group)
    """
    # Each patient has 4 consecutive queries, so rows 0-3 = patient 0, 4-7 = patient 1, etc.
    patient_index = row_index_in_group // 4
    return f"patient_{patient_index}"


def load_evaluation_metadata(csv_path: Path) -> pd.DataFrame:
    """
    Load the evaluation metadata CSV file.
    
    CSV Structure:
    - Column A (index 0): Patient ID (only in first row of each group of 4)
    - Column B (index 1): Query number
    - Column F (index 5): Patient Summary (same for all 4 queries of a patient)
    - Column G (index 6): Query text (the actual query, not the full prompt)
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        DataFrame with evaluation metadata
    """
    try:
        df = pd.read_csv(csv_path)
        # Normalize column names (handle variations)
        df.columns = df.columns.str.strip()
        
        # Identify columns by index (more reliable)
        # Column A (index 0): Patient ID - SHOWN
        # Column B (index 1): Query number - SHOWN
        # Column C (index 2): Group - HIDDEN (captured for submission)
        # Column D (index 3): Query Type - HIDDEN (captured for submission)
        # Column E (index 4): PHI Dependency - HIDDEN (captured for submission)
        # Column F (index 5): Patient Summary (Ground Truth) - SHOWN
        # Column G (index 6): Query - SHOWN
        patient_col = df.columns[0]      # Column A - Patient ID
        query_num_col = df.columns[1]    # Column B - Query number
        group_col = df.columns[2]        # Column C - Group (hidden)
        query_type_col = df.columns[3]   # Column D - Query Type (hidden)
        phi_dep_col = df.columns[4]      # Column E - PHI Dependency (hidden)
        summary_col = df.columns[5]      # Column F - Patient Summary (shown)
        query_text_col = df.columns[6]   # Column G - Query text (shown)
        
        # Forward-fill Patient IDs (since they're only in first row of each group)
        df[patient_col] = df[patient_col].ffill()
        
        # Forward-fill Patient Summary (same for all queries of a patient)
        df[summary_col] = df[summary_col].ffill()
        
        # Remove rows where Patient ID is still NaN (header or empty rows)
        df = df[df[patient_col].notna()]
        
        # Store column names for reference
        df.attrs['patient_col'] = patient_col
        df.attrs['query_col'] = query_num_col
        df.attrs['query_text_col'] = query_text_col
        df.attrs['summary_col'] = summary_col
        # Hidden columns (captured but not shown to evaluators)
        df.attrs['group_col'] = group_col
        df.attrs['query_type_col'] = query_type_col
        df.attrs['phi_dep_col'] = phi_dep_col
        
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()


def load_assignments(assignments_path: Path) -> Dict:
    """
    Load evaluator assignments from JSON file.
    
    Returns:
        Dictionary with evaluator assignments
    """
    if assignments_path.exists():
        try:
            with open(assignments_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Error loading assignments: {e}")
            return {}
    return {}


def save_assignments(assignments: Dict, assignments_path: Path):
    """Save evaluator assignments to JSON file."""
    try:
        with open(assignments_path, 'w') as f:
            json.dump(assignments, f, indent=2)
    except Exception as e:
        st.error(f"Error saving assignments: {e}")


def create_assignments(df: pd.DataFrame, num_evaluators: int = 6) -> Dict:
    """
    Create evaluator assignments based on patient groups.
    
    Group assignments:
    - Evaluators 1 & 2 → Group A (12 patients)
    - Evaluators 3 & 4 → Group B (12 patients)
    - Evaluators 5 & 6 → Group C (12 patients)
    
    Each evaluator gets exactly 12 patients with all their respective queries.
    
    Args:
        df: DataFrame with evaluation metadata
        num_evaluators: Number of evaluators
        
    Returns:
        Dictionary mapping evaluator names to their assigned patient-query pairs
    """
    assignments = {}
    
    # Get column references
    patient_col = df.attrs.get('patient_col', df.columns[0])
    query_col = df.attrs.get('query_col', df.columns[1])
    group_col = df.attrs.get('group_col', df.columns[2])
    
    # Define which evaluators get which groups
    # Each group has 2 evaluators (for inter-rater reliability)
    evaluator_groups = {
        "Evaluator 1": "A",
        "Evaluator 2": "A",
        "Evaluator 3": "B",
        "Evaluator 4": "B",
        "Evaluator 5": "C",
        "Evaluator 6": "C",
        "Tester": "A"  # Testers can access Group A for testing
    }
    
    for evaluator, assigned_group in evaluator_groups.items():
        # Get all rows for this group
        group_df = df[df[group_col] == assigned_group].copy().reset_index(drop=True)
        
        # Add base patient ID column for proper grouping (every 4 rows = 1 patient)
        group_df['base_patient_id'] = [get_base_patient_id(pid, i) for i, pid in enumerate(group_df[patient_col])]
        
        # Also store the first patient_id of each group of 4 as display name
        group_df['display_patient_id'] = group_df.groupby('base_patient_id')[patient_col].transform('first')
        
        # Get all queries for this group (should be 48 = 12 patients × 4 queries)
        evaluator_assignments = []
        for _, row in group_df.iterrows():
            evaluator_assignments.append({
                # Visible fields (shown to evaluators)
                'patient_id': str(row[patient_col]),
                'base_patient_id': str(row['display_patient_id']),  # Use first patient ID of group for display
                'query_num': str(row[query_col]),
                'full_query': str(row.get(df.attrs.get('query_text_col', ''), '')),
                'patient_summary': str(row.get(df.attrs.get('summary_col', ''), '')),
                # Hidden fields (captured for submission, not shown to evaluators)
                'group': str(row.get(df.attrs.get('group_col', ''), '')),
                'query_type': str(row.get(df.attrs.get('query_type_col', ''), '')),
                'phi_dependency': str(row.get(df.attrs.get('phi_dep_col', ''), ''))
            })
        
        assignments[evaluator] = evaluator_assignments
    
    return assignments


def get_current_assignment(evaluator: str, assignments: Dict, current_index: int) -> Optional[Dict]:
    """Get the current assignment for an evaluator."""
    if evaluator not in assignments:
        return None
    
    evaluator_assignments = assignments[evaluator]
    if 0 <= current_index < len(evaluator_assignments):
        return evaluator_assignments[current_index]
    return None


def get_progress(evaluator: str, assignments: Dict, current_index: int) -> Tuple[int, int]:
    """Get progress for an evaluator: (completed, total)."""
    if evaluator not in assignments:
        return 0, 0
    
    total = len(assignments[evaluator])
    completed = min(current_index, total)
    return completed, total

