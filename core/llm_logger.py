import os
import json
from datetime import datetime
from typing import Any, Dict, Optional
import logging
import inspect
import textwrap

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LLM_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'current_llm_response.txt')

def _get_calling_function() -> str:
    """Get detailed context about the function that called the LLM."""
    stack = inspect.stack()
    
    # Look for the first non-logger frame
    for frame_info in stack[2:]:  # Skip current and log_llm_response frames
        # Skip internal/helper functions and framework internals
        func_name = frame_info.function
        if func_name.startswith('_') or func_name in ('call_llm', 'ainvoke', '_call_llm'):
            continue
            
        # Get the module name
        module = inspect.getmodule(frame_info.frame)
        module_name = module.__name__ if module else 'unknown_module'
        
        # Format: module.function (file:line)
        return f"{module_name}.{func_name} (line {frame_info.lineno})"
        
    return "unknown_function"

def _format_response(response: Any) -> str:
    """Format the LLM response for better readability."""
    if isinstance(response, dict) or isinstance(response, list):
        try:
            return json.dumps(response, indent=2, ensure_ascii=False)
        except:
            pass
    return str(response)

def log_llm_response(prompt: str, response: Any, metadata: Optional[Dict[str, Any]] = None):
    """
    Log LLM response to current_llm_response.txt with timestamp and function name.
    Most recent logs are added at the top of the file.
    
    Args:
        prompt: The input prompt sent to the LLM (not logged in the output)
        response: The raw response from the LLM
        metadata: Additional metadata to include in the log (e.g., model name, timestamp, etc.)
    """
    try:
        # Get the calling function name
        function_name = _get_calling_function()
        
        # Format the response for better readability
        formatted_response = _format_response(response)
        
        # Create a clean log entry with more context
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get the stage from metadata if available
        stage = metadata.get('stage', 'general').replace('_', ' ').title() if metadata else 'General'
        
        # Format the log entry with clear sections
        log_entry = f"""
╔═ {stage} ════════════════════════════════╗
║ Function: {function_name}
║ Time: {timestamp} UTC
╚═{'═' * 40}╝
{formatted_response}

{'═' * 80}
"""
        # Read existing content if file exists
        existing_content = ""
        if os.path.exists(LLM_LOG_FILE):
            try:
                with open(LLM_LOG_FILE, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
            except Exception as e:
                logger.error(f"Failed to read existing LLM log file: {e}")
        
        # Write new content followed by existing content
        with open(LLM_LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f"{log_entry}{existing_content}")
            
    except Exception as e:
        logger.error(f"Failed to log LLM response: {e}", exc_info=True)
