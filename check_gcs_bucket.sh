#!/bin/bash
# Check GCS for Cinema IRL episode files 195-201
# Run this in Cloud Shell where you have gcloud access

echo "Checking GCS bucket for Cinema IRL episodes 195-201..."
echo "============================================================"

BUCKET="podcastpro-media"  # Adjust if your bucket name is different

echo ""
echo "Looking for episode files in gs://$BUCKET/episodes/"
gsutil ls -lh "gs://$BUCKET/episodes/" | grep -E '195|196|197|198|199|200|201'

echo ""
echo "Looking for files in gs://$BUCKET/final/"
gsutil ls -lh "gs://$BUCKET/final/" 2>/dev/null | grep -E '195|196|197|198|199|200|201'

echo ""
echo "Looking for Cinema IRL files anywhere:"
gsutil ls -r "gs://$BUCKET/**" | grep -i "cinema" | grep -E '195|196|197|198|199|200|201'

echo ""
echo "============================================================"
echo "If files are found above, note their gs:// paths"
echo "We'll use those to populate the database gcs_audio_path field"
