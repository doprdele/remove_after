#!/bin/bash
sleep ${AFTER}

ID=$(curl -s http://169.254.169.254/metadata/v1/id)

curl -X DELETE -H "Content Type: application/json" -H "Authorization: ${TOKEN}" "https://api.digitalocean.com/v2/droplets/${ID}"
