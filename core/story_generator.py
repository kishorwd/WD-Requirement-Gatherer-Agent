import json
from typing import List, Dict, Any, Optional, Union
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.schema import HumanMessage, SystemMessage
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StoryGenerator:
    def __init__(self, model_name: str = None, temperature: float = 0.2):
        """
        Initialize the StoryGenerator with the specified model and temperature.
        If model_name is not provided, it will use the value from LLM_MODEL environment variable
        or default to 'gemini-2.5-flash'.
        """
        self.model_name = model_name or os.getenv("LLM_MODEL", "gemini-2.5-flash")
        self.temperature = temperature
        self.llm = self._initialize_llm()
        
        # Initialize the prompt template
        self.prompt_template = """You are an expert Business Analyst. Your task is to analyze the following raw requirements 
        and convert them into well-structured user stories with clear acceptance criteria.
        
        Instructions:
        1. Group related requirements by modules and sub-modules
        2. Remove any duplicates
        3. Format each requirement as a user story following this structure:
           - Module Name
           - Sub-module Name
           - Description (As a [User], I want [Action], so that [Benefit])
           - User Acceptance Criteria (3-5 bullet points, each starting with 'GIVEN/WHEN/THEN')
        
        Raw Requirements:
        {requirements_text}
        
        Return your response as ONLY valid JSON — no markdown, no explanations, no code fences.
        Ensure it is strictly a JSON array following this exact schema:
        [
            {
                "module_name": "Module Name",
                "sub_module_name": "Sub-module Name",
                "description": "As a [User], I want [Action], so that [Benefit]",
                "acceptance_criteria": [
                    "GIVEN [context] WHEN [action] THEN [outcome]",
                    "GIVEN [context] WHEN [action] THEN [outcome]"
                ]
            }
        ]
        Ensure the JSON is 100% valid, properly closed, and does not include comments or extra text.

        """.replace('{', '{{').replace('}', '}}').replace('{{requirements_text}}', '{requirements_text}')
        
    def _initialize_llm(self):
        """Initialize the language model with proper error handling."""
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY environment variable not set")
            raise ValueError("GOOGLE_API_KEY environment variable not set")
            
        try:
            return ChatGoogleGenerativeAI(
                model=self.model_name,
                google_api_key=api_key,
                temperature=self.temperature,
                convert_system_message_to_human=True
            )
        except Exception as e:
            logger.error(f"Failed to initialize language model: {str(e)}")
            raise

    async def synthesize_user_stories(self, raw_requirements_text: str) -> List[Dict[str, Any]]:
        """
        Process raw requirements text and generate structured user stories.
        
        Args:
            raw_requirements_text: Raw text containing requirements
            
        Returns:
            List of dictionaries containing structured user stories
            
        Raises:
            ValueError: If the AI response cannot be parsed as valid JSON
            Exception: For any other errors during processing
        """
        try:
            # Input validation
            if not raw_requirements_text or not raw_requirements_text.strip():
                logger.warning("Empty or invalid requirements text provided")
                return []
                
            logger.info("Generating user stories from requirements...")
            
            try:
                # Format the prompt with the requirements text
                prompt = self.prompt_template.format(
                    requirements_text=raw_requirements_text
                )
                
                # Get response from the language model
                response = await self.llm.agenerate([[HumanMessage(content=prompt)]])
                response_text = response.generations[0][0].text.strip()
                
                logger.debug(f"Raw AI response: {response_text[:500]}...")  # Log first 500 chars of response
                
                # Clean the response to extract just the JSON part
                json_start = response_text.find('[')
                json_end = response_text.rfind(']') + 1
                
                if json_start == -1 or json_end == 0:
                    logger.error("No valid JSON array found in AI response")
                    logger.debug(f"Response content: {response_text}")
                    raise ValueError("The AI response did not contain a valid JSON array")
                    
                json_str = response_text[json_start:json_end]
                
                # Parse the JSON response
                stories = json.loads(json_str)
                
                # Validate the structure
                if not isinstance(stories, list):
                    raise ValueError("Expected a list of stories in the response")
                
                if not stories:
                    logger.warning("No stories were generated from the requirements")
                    return []
                    
                # Process and validate each story
                validated_stories = []
                for i, story in enumerate(stories, 1):
                    try:
                        if not isinstance(story, dict):
                            logger.warning(f"Skipping invalid story format at index {i-1}")
                            continue
                            
                        # Ensure all required fields exist with defaults
                        validated_story = {
                            'brn': f"BRN-{i:03d}",
                            'sub_brn': f"BRN-{i:03d}.1",
                            'module_name': str(story.get('module_name', 'Uncategorized')).strip() or 'Uncategorized',
                            'sub_module_name': str(story.get('sub_module_name', 'General')).strip() or 'General',
                            'description': str(story.get('description', '')).strip(),
                            'acceptance_criteria': [
                                str(crit).strip() 
                                for crit in story.get('acceptance_criteria', []) 
                                if str(crit).strip()
                            ]
                        }
                        
                        # Only include stories with a description
                        if validated_story['description']:
                            validated_stories.append(validated_story)
                            
                    except Exception as e:
                        logger.warning(f"Error processing story at index {i-1}: {str(e)}", exc_info=True)
                        continue
                
                logger.info(f"Successfully generated {len(validated_stories)} valid user stories")
                return validated_stories
                
            except json.JSONDecodeError as je:
                logger.error(f"Failed to parse JSON from AI response: {str(je)}")
                logger.debug(f"JSON string that failed to parse: {json_str if 'json_str' in locals() else 'N/A'}")
                raise ValueError(f"Failed to parse AI response: {str(je)}")
                
            except Exception as e:
                logger.error(f"Error during story generation: {str(e)}", exc_info=True)
                raise
                
        except Exception as e:
            logger.error(f"Unexpected error in synthesize_user_stories: {str(e)}", exc_info=True)
            raise
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {str(e)}")
            logger.debug(f"Response content: {response_text}")
            raise ValueError("Failed to parse AI response. The response was not valid JSON.")
            
        except Exception as e:
            logger.error(f"Error in synthesize_user_stories: {str(e)}", exc_info=True)
            raise

# Singleton instance
story_generator = StoryGenerator()

# Async function for direct import
async def synthesize_user_stories(raw_requirements_text: str) -> List[Dict[str, Any]]:
    """
    Async function to generate user stories from raw requirements.
    
    Args:
        raw_requirements_text: Raw text containing requirements
        
    Returns:
        List of dictionaries containing structured user stories
    """
    return await story_generator.synthesize_user_stories(raw_requirements_text)
