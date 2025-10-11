# Idea: AI-Powered Social Media Clip Finder

This document outlines an idea for a feature that helps podcast creators find the best, most shareable clips from their episode transcripts for social media.

## How Difficult Is It?

-   **Overall Difficulty:** Moderate.
-   **Core Challenge:** The primary challenge is not technical but conceptual: defining what makes a "good clip" is subjective. The AI's effectiveness will depend heavily on the quality of the prompt.
-   **Technical Components:** The technical side is straightforward and involves:
    1.  Processing transcript text.
    2.  Calling an AI model (like Gemini).
    3.  Storing and displaying the results.

The existing application infrastructure is well-suited for this feature.

## Conceptual Workflow

Here is a high-level overview of how the feature would work from user interaction to final output.

1.  **Trigger Analysis:** A user clicks a "Find Social Clips" button on an episode's page. This action calls a new API endpoint (e.g., `POST /api/clips/find/{episode_id}`).

2.  **Process in Background:** The API triggers a background task (e.g., using Cloud Tasks or Celery) to handle the analysis. This prevents the user from waiting for a long-running process.

3.  **Load Transcript:** The background task loads the full episode transcript, including words, speakers, and timestamps.

4.  **Chunk and Analyze:** The transcript is broken into manageable chunks (e.g., 60-90 seconds of text). Each chunk is sent to a powerful AI model with a specific prompt.

5.  **The "Magic" Prompt:** The prompt is the core of the feature. It instructs the AI to act as an expert podcast producer and identify segments that are:
    *   **Quotable & Insightful:** Short, powerful statements.
    *   **Funny:** Jokes or moments of laughter.
    *   **Actionable:** Clear advice or takeaways.
    *   **Emotional Peaks:** Moments of high energy, passion, or vulnerability.
    *   **Controversial or Surprising:** Statements that would spark conversation.

6.  **Store Results:** The AI returns a structured list of potential clips. Each suggestion includes a start/end time, a suggested title, a category (e.g., "Funny," "Insightful"), and a justification. These are stored in a new `PodcastClip` database table.

7.  **Display to User:** The user's interface polls for the results and displays the list of suggested clips. The user can then preview the audio, edit the clip, and export it.

## Implementation Ideas

Here are some concrete code examples for the key components.

### 1. New Model: `PodcastClip`

A new model to store the clip suggestions in the database.

```python
from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional
from sqlmodel import Field, SQLModel, Relationship
from .podcast import Episode

class ClipCategory(str, Enum):
    funny = "funny"
    insightful = "insightful"
    takeaway = "takeaway"
    quote = "quote"
    controversial = "controversial"

class PodcastClip(SQLModel, table=True):
    """A suggested clip from a podcast episode, identified by AI."""
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    episode_id: UUID = Field(foreign_key="episode.id", index=True)
    
    title: str = Field(description="AI-suggested title for the clip.")
    category: ClipCategory = Field(default=ClipCategory.insightful)
    justification: Optional[str] = Field(default=None, description="Why the AI thinks this is a good clip.")
    
    start_time_ms: int
    end_time_ms: int
    
    # User feedback and status
    is_exported: bool = Field(default=False)
    user_rating: Optional[int] = Field(default=None, ge=1, le=5)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    episode: Episode = Relationship()
```

### 2. New API Router: `clips.py`

A new router to handle requests to find and list clips.

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from uuid import UUID
from typing import List

@router.post("/find/{episode_id}", status_code=202)
async def find_clips_for_episode(episode_id: UUID, ...):
    """Trigger a background task to find shareable clips in an episode."""
    # 1. Verify user owns the episode
    # 2. Dispatch a background task (e.g., using Cloud Tasks or Celery)
    #    find_clips_task.delay(episode_id=episode_id)
    return {"message": "Clip analysis started. Results will be available shortly."}

@router.get("/episode/{episode_id}", response_model=List[PodcastClip])
async def list_clips_for_episode(episode_id: UUID, ...):
    """Retrieve the list of suggested clips for an episode."""
    # Query the PodcastClip table for the given episode_id and user_id
    pass
```

### 3. New Service: `analyzer.py`

The core logic for analyzing the transcript with an AI model.

```python
def find_clips_in_transcript(episode: Episode):
    # 1. Load the full transcript for the episode
    # 2. Chunk the transcript text into manageable segments
    # 3. Create a powerful prompt for the AI model (see above)
    prompt = """
    You are a viral content producer... For each clip you identify, provide:
    - A catchy, short title.
    - The start and end time in milliseconds...
    """
    # 4. Call the AI model (e.g., Gemini)
    # 5. Parse the JSON response and save suggestions to the PodcastClip table
```