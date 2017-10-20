#!/bin/bash

### Script to initialize the EC2 instance
###

set -ex

INSTANCE_ID=`curl "http://169.254.169.254/latest/meta-data/instance-id"`
INSTANCE_NAME="zookeeper-$INSTANCE_ID"

# Wait for instance in `running` status
STATE=""
while [ "$STATE" != "running" ]; do
    echo "Waiting for running status"
    sleep 5
    OUT=$(aws ec2 describe-instances \
                    --region $REGION \
                    --instance-ids $INSTANCE_ID \
                    --output text)
    STATE=$(echo "$OUT" | grep STATE | cut -f 3)
done


# Set Hostname
hostnamectl set-hostname $INSTANCE_NAME
echo "127.0.0.1 localhost $INSTANCE_NAME" > /etc/hosts


# Set EC2 Instance Name
aws ec2 create-tags \
                --region $REGION \
                --resources $INSTANCE_ID \
                --tags Key=Name,Value="$INSTANCE_NAME"

exit 0
