# Worker Server GCS Credentials Setup

## Problem

The worker server is failing to download files from GCS with this error:
```
Your default credentials were not found. To set up Application Default Credentials, 
see https://cloud.google.com/docs/authentication/external/set-up-adc for more information.
```

## Solution

The worker server needs GCS credentials to download intermediate files (main content, intros, outros, etc.) from GCS.

## Configuration Options

### Option 1: Service Account Key File (Recommended for Proxmox/Linux)

1. **Create or download a GCP service account key:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Navigate to IAM & Admin > Service Accounts
   - Create a new service account or use an existing one
   - Grant it the "Storage Object Viewer" role for your GCS bucket
   - Create a JSON key and download it

2. **Copy the key to your worker server:**
   ```bash
   # On your worker server (Proxmox)
   scp path/to/service-account-key.json user@worker-server:/root/CloudPod/gcp-key.json
   ```

3. **Set the environment variable:**
   ```bash
   # In your worker server's environment (systemd service, docker-compose, etc.)
   export GOOGLE_APPLICATION_CREDENTIALS=/root/CloudPod/gcp-key.json
   ```

4. **Set permissions:**
   ```bash
   chmod 600 /root/CloudPod/gcp-key.json
   ```

### Option 2: Application Default Credentials (if using gcloud CLI)

If you have `gcloud` CLI installed on the worker server:

```bash
# Authenticate with gcloud
gcloud auth application-default login

# This will create credentials at:
# ~/.config/gcloud/application_default_credentials.json
```

### Option 3: Environment Variable with JSON (for Docker/Container)

If running in Docker or a container, you can pass the service account key JSON directly:

```bash
# In your docker-compose.yml or container environment
GCS_SIGNER_KEY_JSON='{"type":"service_account","project_id":"podcast612",...}'
```

Or use a volume mount:
```yaml
volumes:
  - ./gcp-key.json:/app/gcp-key.json:ro
environment:
  GOOGLE_APPLICATION_CREDENTIALS: /app/gcp-key.json
```

## Verification

After configuring credentials, test that the worker can access GCS:

```python
# Test script (run on worker server)
from google.cloud import storage

client = storage.Client()
bucket = client.bucket('ppp-media-us-west1')
blobs = list(bucket.list_blobs(max_results=5))
print(f"Successfully connected to GCS! Found {len(blobs)} blobs.")
```

## Current Worker Server Setup

Based on your logs, the worker server is running on Proxmox. You'll need to:

1. **SSH into your Proxmox worker server**
2. **Locate your worker service configuration** (systemd service, docker-compose, etc.)
3. **Add the GCS credentials** using one of the options above
4. **Restart the worker service**

## Required GCS Permissions

The service account needs these permissions:
- **Storage Object Viewer** - to download files from GCS buckets
- **Storage Object Creator** (optional) - if the worker needs to upload files

## Security Notes

- **Never commit service account keys to git**
- **Use environment variables or secure secret management**
- **Limit service account permissions to only what's needed**
- **Rotate keys periodically**

## Next Steps

1. Configure GCS credentials on the worker server using one of the options above
2. Restart the worker service
3. Try uploading and assembling an episode again
4. Check worker logs to verify GCS downloads are working

## Troubleshooting

If you still see credential errors after configuration:

1. **Verify the key file exists:**
   ```bash
   ls -la $GOOGLE_APPLICATION_CREDENTIALS
   ```

2. **Test the credentials:**
   ```bash
   gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS
   gsutil ls gs://ppp-media-us-west1/
   ```

3. **Check environment variables:**
   ```bash
   echo $GOOGLE_APPLICATION_CREDENTIALS
   ```

4. **Verify the service account has the correct permissions in GCP Console**

5. **Check worker logs for detailed error messages**

