import subprocess
import sys
import os

print("Starting forceful deployment of podcast-api...")

# Ensure we are in the right directory
cwd = os.getcwd()
print(f"Working directory: {cwd}")

# The command that was in cloudbuild.yaml
cmd = "gcloud builds submit --config=cloudbuild.yaml --project=podcast612 --quiet"

print(f"Running: {cmd}")
try:
    # Use Popen to stream output in real-time to the agent logs
    process = subprocess.Popen(
        cmd, 
        shell=True, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Print output line by line
    for line in process.stdout:
        print(line, end='')
        
    process.wait()
    
    if process.returncode != 0:
        print(f"\nDeployment FAILED with code {process.returncode}")
        sys.exit(process.returncode)
    else:
        print("\nDeployment SUCCESSFUL!")
        
except Exception as e:
    print(f"\nExecution Error: {e}")
    sys.exit(1)
