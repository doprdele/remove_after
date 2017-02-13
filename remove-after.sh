#!/bin/bash
sleep ${AFTER}

# Digital Ocean
if [[ $TOKEN ]]; then
  ID=$(curl -s http://169.254.169.254/metadata/v1/id)
  curl -X DELETE -H "Content Type: application/json" -H "Authorization: Bearer ${TOKEN}" "https://api.digitalocean.com/v2/droplets/${ID}"
# Google Compute
elif [[ $GCP ]]; then
  VMNAME=$(curl -H Metadata-Flavor:Google http://metadata/computeMetadata/v1/instance/hostname | cut -d. -f1)
  ZONE=$(curl -H Metadata-Flavor:Google http://metadata/computeMetadata/v1/instance/zone | cut -d/ -f4)
  /root/google-cloud-sdk/bin/gcloud compute instances delete $VMNAME --zone $ZONE --quiet
else
  echo "..unsupported cloud provider..."
fi
