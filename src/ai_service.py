import os
from cerebras.cloud.sdk import Cerebras
import json
from dotenv import load_dotenv
from .campaign_routes import LOCATIONS, INTERESTS
import asyncio

# Load environment variables from .env file if it exists
load_dotenv()

class AIService:
    """Service for AI-powered campaign suggestions using Cerebras LLM."""
    
    def __init__(self):
        """Initialize the Cerebras client."""
        self.client = None
        self.model = "llama-4-scout-17b-16e-instruct"
        
        # Initialize the client if API key is available
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Cerebras client with API key from environment variables."""
        api_key = os.environ.get("CEREBRAS_API_KEY")
        if api_key:
            try:
                self.client = Cerebras(api_key=api_key)
            except Exception as e:
                print(f"Error initializing Cerebras client: {e}")
        else:
            print("Cerebras API key not found. Please set the CEREBRAS_API_KEY environment variable.")
    
    async def get_campaign_suggestion(self, business_type=None):
        """
        Get an AI-generated campaign suggestion.
        
        Args:
            business_type: Optional type of business to tailor suggestions for
        
        Returns:
            dict: Campaign suggestion with title, description, targeting, and ad text
        """
        if not self.client:
            raise ValueError("Cerebras client is not initialized. Please set the CEREBRAS_API_KEY environment variable.")
            
        try:
            prompt = self._build_prompt(business_type)
            
            # Create the messages payload
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert marketing assistant that creates targeted advertising campaign suggestions with specific details."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            
            # Run the synchronous API call in a thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    messages=messages,
                    model=self.model
                )
            )
            
            # Parse the response
            suggestion_text = response.choices[0].message.content
            parsed_suggestion = self._parse_suggestion(suggestion_text)
            
            # Ensure all required fields are present
            if not self._validate_suggestion(parsed_suggestion):
                raise ValueError("Invalid suggestion format received from API.")
                
            return parsed_suggestion
        
        except Exception as e:
            print(f"Error getting AI suggestion: {e}")
            raise
    
    def _build_prompt(self, business_type=None):
        """Build the prompt for the AI based on business type."""
        # Use the imported constants
        interests_list = ", ".join(INTERESTS)
        locations_list = ", ".join(LOCATIONS)
        
        if business_type:
            prompt = f"""
            Create a detailed advertising campaign suggestion for a {business_type} business.
            The response should be structured as valid JSON with the following fields:
            - title: A catchy campaign title
            - description: A brief campaign strategy description
            - targeting: A string with target demographics in the format "Age: X-Y, Location: [City], Interests: [Interest1, Interest2]"
            - adText: Compelling ad copy text
            
            IMPORTANT CONSTRAINTS:
            1. For the "Interests" section in targeting, ONLY use interests from this predefined list: {interests_list}
               Select 1-3 interests that would be most relevant for this business type.
            2. For the "Location" section in targeting, ONLY use locations from this predefined list: {locations_list}
               Select ONE location that would be most appropriate for this business type.
            
            Keep the response strictly in valid JSON format.
            """
        else:
            prompt = f"""
            Create a detailed advertising campaign suggestion.
            The response should be structured as valid JSON with the following fields:
            - title: A catchy campaign title
            - description: A brief campaign strategy description
            - targeting: A string with target demographics in the format "Age: X-Y, Location: [City], Interests: [Interest1, Interest2]"
            - adText: Compelling ad copy text
            
            IMPORTANT CONSTRAINTS:
            1. For the "Interests" section in targeting, ONLY use interests from this predefined list: {interests_list}
               Select 1-3 interests that would be most relevant.
            2. For the "Location" section in targeting, ONLY use locations from this predefined list: {locations_list}
               Select ONE location that would be most appropriate.
            
            Keep the response strictly in valid JSON format.
            """
        
        return prompt
    
    def _parse_suggestion(self, suggestion_text):
        """Parse the suggestion text from the AI into a structured format."""
        # Extract JSON from the response (in case there's additional text)
        try:
            # Find the JSON part of the response
            start_idx = suggestion_text.find('{')
            end_idx = suggestion_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = suggestion_text[start_idx:end_idx]
                return json.loads(json_str)
            
            # If we can't find JSON markers, try parsing the whole response
            return json.loads(suggestion_text)
        except json.JSONDecodeError:
            print("Failed to parse AI response as JSON")
            raise ValueError("Failed to parse AI response as JSON")
    
    def _validate_suggestion(self, suggestion):
        """Validate that a suggestion has all required fields."""
        required_fields = ['title', 'description', 'targeting', 'adText']
        return all(field in suggestion and suggestion[field] for field in required_fields)

# Singleton instance
ai_service = AIService() 