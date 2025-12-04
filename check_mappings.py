import subprocess
import json
import sys

def check_mappings():
    try:
        result = subprocess.run(
            ['gcloud', 'beta', 'run', 'domain-mappings', 'list', 
             '--region=us-west1', '--project=podcast612', '--format=json'],
            capture_output=True, text=True, check=True
        )
        mappings = json.loads(result.stdout)
        print(f"Found {len(mappings)} mappings:")
        for m in mappings:
            print(f"- {m['metadata']['name']} -> {m['spec']['routeName']}")
            
        # Check for wildcard
        wildcard = next((m for m in mappings if m['metadata']['name'] == '*.podcastplusplus.com'), None)
        if wildcard:
            print("\nSUCCESS: Wildcard mapping '*.podcastplusplus.com' exists!", flush=True)
            print("DETAILS:", flush=True)
            print(json.dumps(wildcard, indent=2), flush=True)
        else:
            print("\nFAILURE: Wildcard mapping '*.podcastplusplus.com' NOT found.", flush=True)
            
    except subprocess.CalledProcessError as e:
        print(f"Error running gcloud: {e.stderr}", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)

if __name__ == "__main__":
    check_mappings()
    sys.stdout.flush()
