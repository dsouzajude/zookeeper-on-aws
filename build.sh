#!/bin/sh

packer build -var ami="ami-a8d2d7ce" \
             -var region="eu-west-1" \
             -var iam_instance_profile="wrapp-ec2-host" \
             ami/zookeeper.packer.json
