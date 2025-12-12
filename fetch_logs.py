import subprocess
import json
import logging

def fetch_logs():
    print("Fetching logs for 'podcast-api' service...")
    try:
        # Fetch last 20 log entries with severity ERROR or greater
        # Filter for the specific endpoint if possible, but general errors are fine
        cmd = [
            "gcloud", "logging", "read",
            'resource.type="cloud_run_revision" AND resource.labels.service_name="podcast-api" AND severity>=ERROR',
            "--limit=20",
            "--format=json"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logs = json.loads(result.stdout)
        
        print(f"Found {len(logs)} error logs.")
        
        with open('recent_errors.json', 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2)
            
        # Print a summary to stdout
        for entry in logs:
            payload = entry.get('textPayload') or entry.get('jsonPayload', {})
            timestamp = entry.get('timestamp')
            print(f"\n[{timestamp}] Error: {payload}")
            
    except subprocess.CalledProcessError as e:
        print(f"Error running gcloud: {e}")
        print(e.stderr)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    fetch_logs()
