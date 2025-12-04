import subprocess
import json
import sys

def check_builds():
    try:
        # Run gcloud command to list builds
        result = subprocess.run(
            ['gcloud', 'builds', 'list', '--limit=1', '--project=podcast612', '--format=json'],
            capture_output=True,
            text=True,
            check=True,
            shell=True
        )
        
        builds = json.loads(result.stdout)
        
        if not builds:
            print("No builds found.", flush=True)
            return

        latest_build = builds[0]
        print(f"Latest Build ID: {latest_build.get('id')}", flush=True)
        print(f"Status: {latest_build.get('status')}", flush=True)
        print(f"Create Time: {latest_build.get('createTime')}", flush=True)
        
    except subprocess.CalledProcessError as e:
        print(f"Error running gcloud: {e.stderr}", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)

if __name__ == "__main__":
    check_builds()
    sys.stdout.flush()
