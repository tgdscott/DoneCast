from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any
import openai
import os
import json
from api.core.auth import get_current_user
from ..models.user import User

router = APIRouter()

# In a real application, you would use a more robust way to configure the API key.
# For this example, we'll use an environment variable.
# Ensure you have OPENAI_API_KEY set in your environment.
openai.api_key = os.getenv("OPENAI_API_KEY")
openai.api_base = "https://generativelanguage.googleapis.com/v1beta"

class Conversation(BaseModel):
    history: List[Dict[str, str]]
    user_id: str # To associate the template with the user

SYSTEM_PROMPT = """
You are the Podcast Plus Plus Template Wizard. Your goal is to help a user, who may be new to podcasting and not tech-savvy, create a podcast template. You must be friendly, patient, and avoid technical jargon. Your tone should be encouraging and simple.

Ask one question at a time. Start by asking for the name of their podcast.

Guide the user through the following topics:
1.  **Podcast Name:** What is the name of your podcast?
2.  **Podcast Topic/Audience:** What is your podcast about? Who is it for?
3.  **Podcast Style:** Should it be formal, casual, funny, or something else?
4.  **Structure:** Do you want an interview show, a solo show, or a story-based show?
5.  **Intro:**
    *   Do you want an intro?
    *   Do you have an audio file for it, or should we use a voiceover? (If voiceover, ask for the script.)
    *   Do you want background music? (If yes, suggest royalty-free sites like Pixabay Music, Bensound, or the YouTube Audio Library.)
6.  **Outro:**
    *   Do you want an outro?
    *   Do you have an audio file for it, or should we use a voiceover? (If voiceover, ask for the script.)
    *   Do you want background music for the outro?
7.  **Background Music for Content:** Do you want any quiet background music during the main content?

Once you have all the information, you MUST summarize it back to the user and ask for confirmation. If they confirm, you MUST respond with ONLY a valid JSON object representing the completed template, enclosed in ```json ... ```. Do not include any other text in that final message.

The JSON structure should be:
{
  "name": "<Podcast Name>",
  "segments": [
    { "segment_type": "intro", "source": { "source_type": "static"/"tts", "filename": "<file.mp3>"/"script": "<script>" } },
    { "segment_type": "content", "source": { "source_type": "static", "filename": "placeholder.mp3" } },
    { "segment_type": "outro", "source": { "source_type": "static"/"tts", "filename": "<file.mp3>"/"script": "<script>" } }
  ],
  "background_music_rules": [
    { "music_filename": "<music.mp3>", "apply_to_segments": ["intro"/"content"/"outro"] }
  ]
}
"""

@router.post("/conversation")
async def handle_conversation(conversation: Conversation, current_user: User = Depends(get_current_user)):
    """
    Handles the conversation with the user to build the podcast template.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    for message in conversation.history:
        messages.append(message)

    try:
        # Note: The Gemini API uses a different format for API calls.
        # This is a conceptual representation.
        # In a real implementation, you would use the Google AI Python SDK.
        # For now, we will simulate the response.

        # This is a mock response for demonstration purposes.
        # In a real scenario, you would call the Gemini API here.
        last_user_message = conversation.history[-1]["content"].lower()
        if "podcast name" in last_user_message:
            response_text = "Great! What is your podcast about? Who is it for?"
        elif "about" in last_user_message:
            response_text = "That sounds interesting! Should the tone be formal, casual, or something else?"
        else:
            response_text = "I'm sorry, I'm just a demo. I can't really talk to you."

        # Check if the response is a JSON object
        if response_text.strip().startswith("```json"):
            json_str = response_text.strip().replace("```json", "").replace("```", "")
            try:
                template_data = json.loads(json_str)
                # Here you would save the template to the database
                return {"is_template": True, "template": template_data}
            except json.JSONDecodeError:
                return {"response": "I tried to create a template, but it was not in the correct format. Please try again."}

        return {"response": response_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))