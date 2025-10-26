#!/usr/bin/env python3
"""Manually dispatch all pending Cloud Tasks (workaround for auto-dispatch failure)."""
import subprocess
import json
import time

PROJECT = "podcast612"
LOCATION = "us-west1"
QUEUE = "ppp-queue"

def get_pending_tasks():
    """Get all tasks with 0 dispatch attempts."""
    cmd = [
        "gcloud", "tasks", "list",
        f"--queue={QUEUE}",
        f"--location={LOCATION}",
        f"--project={PROJECT}",
        "--format=json"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error listing tasks: {result.stderr}")
        return []
    
    tasks = json.loads(result.stdout)
    # Filter for tasks with 0 dispatches
    pending = [t for t in tasks if t.get("dispatchCount", 0) == 0]
    return pending

def dispatch_task(task_name):
    """Manually run a task."""
    # Extract just the task ID from full name
    task_id = task_name.split("/")[-1]
    cmd = [
        "gcloud", "tasks", "run", task_id,
        f"--queue={QUEUE}",
        f"--location={LOCATION}",
        f"--project={PROJECT}"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

def main():
    print("Fetching pending tasks...")
    pending = get_pending_tasks()
    
    if not pending:
        print("✅ No pending tasks found")
        return
    
    print(f"Found {len(pending)} pending tasks")
    
    for i, task in enumerate(pending, 1):
        task_name = task["name"]
        task_url = task["httpRequest"]["url"]
        print(f"[{i}/{len(pending)}] Dispatching: {task_url}")
        
        if dispatch_task(task_name):
            print(f"  ✅ Dispatched")
        else:
            print(f"  ❌ Failed")
        
        # Don't overwhelm the API
        if i < len(pending):
            time.sleep(2)
    
    print(f"\n✅ Dispatched {len(pending)} tasks")

if __name__ == "__main__":
    main()
