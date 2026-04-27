from typing import List, Dict, Any, Optional
import logging
from core.scope_gap_analyzer import analyze_transcript_against_sow

def analyze_project_scope(sow_text: str, session_transcripts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Analyze scope by processing raw transcripts against the SOW
    
    Args:
        sow_text: The Statement of Work text
        session_transcripts: List of dictionaries containing session_id and transcript text
        
    Returns:
        List of analyzed requirements with scope status and justification
    """
    results = []
    
    for session in session_transcripts:
        session_id = session.get('session_id')
        transcript = session.get('transcript', '')
        
        if not transcript:
            continue
            
        try:
            # Analyze the transcript against the SOW to extract and analyze requirements
            analysis_results = analyze_transcript_against_sow(sow_text, transcript)
            
            # Add session context to each requirement
            for req in analysis_results:
                req['session_id'] = session_id
                req['session_number'] = session.get('session_number', 0)
                results.append(req)
                
        except Exception as e:
            logging.error(f"Error analyzing session {session_id}: {str(e)}")
            continue
    
    return results

def consolidate_requirements(requirements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Consolidate duplicate requirements across sessions
    """
    # Group requirements by text and module
    requirements_by_text = {}
    
    for req in requirements:
        key = (req['text'].strip().lower(), req.get('module', '').strip().lower())
        if key not in requirements_by_text:
            requirements_by_text[key] = {
                'text': req['text'],
                'module': req.get('module'),
                'session_ids': set(),
                'scope_statuses': set(),
                'justifications': []
            }
        
        requirements_by_text[key]['session_ids'].add(req['session_id'])
        
        if 'scope_status' in req:
            requirements_by_text[key]['scope_statuses'].add(req['scope_status'])
        if 'justification' in req:
            requirements_by_text[key]['justifications'].append(req['justification'])
    
    # Convert sets to lists and determine consensus status
    consolidated = []
    
    for key, req in requirements_by_text.items():
        # If there are multiple statuses, mark as 'Needs Review'
        if len(req['scope_statuses']) > 1:
            status = 'Needs Review'
        elif req['scope_statuses']:
            status = next(iter(req['scope_statuses']))
        else:
            status = 'Pending Analysis'
        
        consolidated.append({
            'text': req['text'],
            'module': req['module'],
            'session_ids': list(req['session_ids']),
            'scope_status': status,
            'justification': ' | '.join(set(j for j in req['justifications'] if j)),
            'occurrences': len(req['session_ids'])
        })
    
    return consolidated
