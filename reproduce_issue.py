
import os
import sys
import logging
from dotenv import load_dotenv

# Configure logging to file
logging.basicConfig(
    filename='reproduce_output.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)
log = logging.getLogger(__name__)

# Load environment variables from backend/.env.local
env_path = os.path.join(os.getcwd(), 'backend', '.env.local')
log.info(f"Loading env from: {env_path}")
load_dotenv(dotenv_path=env_path, override=True)

# Force AI_PROVIDER to gemini for testing
os.environ["AI_PROVIDER"] = "gemini"
log.info("Forced AI_PROVIDER=gemini for testing")

key = os.getenv("GEMINI_API_KEY")
if key:
    log.info(f"Current GEMINI_API_KEY suffix: ...{key[-5:]}")
else:
    log.info("GEMINI_API_KEY is not set")

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

def test_image_generation():
    log.info("Testing image generation...")
    
    try:
        from api.services.ai_content.client_gemini import generate_podcast_cover_image
        import google.generativeai as genai
        log.info(f"Local google-generativeai version: {genai.__version__}")
        
        prompt = "A futuristic podcast about AI and coding, neon colors, cyberpunk style"
        log.info(f"Prompt: {prompt}")
        
        result = generate_podcast_cover_image(prompt)
        
        if result:
            log.info("SUCCESS: Image generated!")
            log.info(f"Result length: {len(result)}")
            if len(result) > 100:
                log.info(f"Result preview: {result[:50]}...")
        else:
            log.error("FAILURE: returned None")
            
    except Exception as e:
        log.error(f"EXCEPTION: {e}")
        import traceback
        log.error(traceback.format_exc())

if __name__ == "__main__":
    log.info("Starting reproduction script...")
    test_image_generation()
