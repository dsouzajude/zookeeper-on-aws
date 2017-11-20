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
# Doing it in a while loop because sometimes the tag is either overwritten or doesn't get created.
TAG_VALUE=""
while [ "$TAG_VALUE" != "$INSTANCE_NAME" ]; do
    echo "Setting EC2 Instance Name Tag"
    sleep 5
    TAG_VALUE=$(aws ec2 describe-tags \
                    --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=Name" \
                    --region=$REGION \
                    --output=text  | cut -f5)
    aws ec2 create-tags \
                    --region $REGION \
                    --resources $INSTANCE_ID \
                    --tags Key=Name,Value="$INSTANCE_NAME"
done


# Wait for aws:autoscaling:groupName tag to be set
# Sometimes the tag isn't set directly by EC2
TAG_VALUE=
while [ "x$TAG_VALUE" == "x" ]; do
    echo "Waiting for aws:autoscaling:groupName to be set"
    sleep 5
    TAG_VALUE=$(aws ec2 describe-tags \
                    --filters "Name=resource-id,Values=$INSTANCE_ID" "Name=key,Values=aws:autoscaling:groupName" \
                    --region=$REGION \
                    --output=text  | cut -f5)
done



exit 0
