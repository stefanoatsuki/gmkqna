"""
Evaluation Storage - Tracks evaluation progress and stores results
"""

import json
from pathlib import Path
from typing import Dict, Optional


EVALUATIONS_FILE = Path(__file__).parent / "evaluations.json"


def load_evaluations() -> Dict:
    """Load all evaluations from JSON file."""
    if EVALUATIONS_FILE.exists():
        try:
            with open(EVALUATIONS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading evaluations: {e}")
            return {}
    return {}


def save_evaluations(evaluations: Dict):
    """Save all evaluations to JSON file."""
    try:
        with open(EVALUATIONS_FILE, 'w') as f:
            json.dump(evaluations, f, indent=2)
    except Exception as e:
        print(f"Error saving evaluations: {e}")


def get_evaluation_status(evaluator: str, patient_id: str, query_num: str) -> Dict:
    """Get evaluation status for a specific query."""
    evaluations = load_evaluations()
    key = f"{evaluator}_{patient_id}_{query_num}"
    return evaluations.get(key, {
        'started': False,
        'model_a_graded': False,
        'model_b_graded': False,
        'comparison_done': False,
        'model_a_data': {},
        'model_b_data': {},
        'comparison_data': {}
    })


def update_evaluation_status(evaluator: str, patient_id: str, query_num: str, 
                            status_updates: Dict):
    """Update evaluation status for a specific query."""
    evaluations = load_evaluations()
    key = f"{evaluator}_{patient_id}_{query_num}"
    
    if key not in evaluations:
        evaluations[key] = {
            'started': False,
            'model_a_graded': False,
            'model_b_graded': False,
            'comparison_done': False,
            'model_a_data': {},
            'model_b_data': {},
            'comparison_data': {}
        }
    
    evaluations[key].update(status_updates)
    save_evaluations(evaluations)


def get_all_evaluator_queries(evaluator: str, assignments: list) -> list:
    """Get all queries for an evaluator with their status."""
    queries_with_status = []
    evaluations = load_evaluations()
    
    for assignment in assignments:
        patient_id = assignment['patient_id']
        query_num = assignment['query_num']
        key = f"{evaluator}_{patient_id}_{query_num}"
        
        status = evaluations.get(key, {
            'started': False,
            'model_a_graded': False,
            'model_b_graded': False,
            'comparison_done': False
        })
        
        queries_with_status.append({
            **assignment,
            'status': status
        })
    
    return queries_with_status

