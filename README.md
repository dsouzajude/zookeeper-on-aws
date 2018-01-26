Zookeeper On AWS
================
A project that sets up infrastructure to host a [Zookeeper](http://zookeeper.apache.org/) Cluster on AWS. This includes the following:
- Fresh bootstrap of the cluster if none exists already.
- [Dynamically reconfiguring](http://zookeeper.apache.org/doc/r3.5.3-beta/zookeeperReconfig.html) the cluster when new nodes come and go. (Supports version [r3.5.3-beta](http://zookeeper.apache.org/doc/r3.5.3-beta/) as of now).
- (Self Healing) Automatic Detection and Recovery of quorum failure.
- Support for realtime Autoscaling while keeping the quorum intact.


Setting up Zookeeper on AWS
===========================
This project uses [AWS CloudFormation](https://aws.amazon.com/cloudformation/) to setup necessary infrastructure to host Zookeeper instances. The CloudFormation templates is generated via [Troposphere](https://github.com/cloudtools/troposphere). The template expects there is already an existing VPC and internal private subnets covering 3 availability zones.

It uses [Packer](https://www.packer.io/intro/index.html) to build Zookeeper AMIs and [Ansible](https://www.ansible.com/) playbooks to provision the AMI.

This project also installs zookeeper-utils library included within this project that performs core functionality for bootstrapping a fresh cluster, dynamically reconfiguring the cluster when nodes come and go and automatic detection and recovery of quorum failure.


More about Bootstrapping and Dynamic Reconfiguration
====================================================
As of version 3.5.1-alpha, Zookeeper supports dynamic reconfiguration of the cluster. This means you don't really require an immutable static ip non-scalable cluster. This project is based on the 3.5.3-beta release which supports these features.

The `zookeeper-utils` includes a `scripts/zk-bootstrap` script that determines whether a fresh bootstrap of the cluster is needed or a dynamic reconfiguration for a new node to join the cluster. It determines this by checking whether there is already an existing cluster which has quorum - if it has quorum it will join the cluster otherwise it will coordinate via zookeeper protocol for a fresh bootstrap.

To determine if there is a functional quorum, it simply gets all the running zookeeper EC2 instances from the Autoscaling Group and issues the 4letter word `stat` command to see whether any of the instance is a follower or a leader - If this is true, it concludes there is a functional cluster with quorum and hence it joins the cluster by issuing the `add` command. Prior to this it would check to see if there are any terminated instances that were part of the cluster and then issues the `remove` command to remove them from the cluster. This way the cluster is either freshly bootstrapped or dynamically configured keeping the quorum intact with running and functional nodes.


Assigning Zookeeper ID
======================
The challenge here is how to find a unique numeric id for each zookeeper instance without clashing with any existing instance that is probably bootstrapping at the same time. This is a requirement from Zookeeper itself. To achieve this, the bootstrap script uses [AWS CloudWatch LogGroups](http://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/WhatIsCloudWatchLogs.html) and LogStreams to claim an id because CloudWatch LogStreams give us the guarantee of integrity such that if a stream is already created it will fail on creating it again - these LogStreams would be created with the same name as the zookeeper id to guarantee uniqueness. All Zookeeper EC2 instances would also be tagged with their id as part of the bootstrap.


Building the AMI
================
This script assumes you have packer installed and appropriate credentials to AWS. To build the AMI perform the following steps:

- Edit `build.sh` to set the base ami, region and iam role.
- Execute `build.sh` or run:

```bash

>> packer build -var ami="<AMI>" \
             -var region="<Region>" \
             -var iam_instance_profile="<IamRole>" \
             ami/zookeeper.packer.json

```

After building the AMI, you can deploy it by following the below instructions.


Setting up Zookeeper Infrastructure and Deploying the AMI
=========================================================
This script runs the CloudFormation template that sets up necessary infrastructure to host Zookeeper. This includes setting up LauchConfigurations, AutoscalingGroups with instances that assume a role and SecurityGroups. It assumes there is already a VPC in place into which these resources would reside in and an IAM role for the
zookeeper instance with atleast the following permissions:

  - logs:CreateLogGroup
  - logs:CreateLogStream
  - logs:PutLogEvents
  - logs:DeleteLogStream
  - logs:DescribeLogStreams
  - ec2:DescribeInstances
  - ec2:DescribeTags
  - ec2:CreateTags
  - autoscaling:Describe*

To setup this up perform the following steps:

- Edit `deploy.sh` and set the appropriate parameters.
- Execute `deploy.sh` or run:

```bash

>> python cf/CFZookeeper.py \
         --stackname "<StackName>" \
         --keyname "<KeyName>" \
         --vpcid "<VpcId>" \
         --subnets "<SubnetA>" "<SubnetB>" "<SubnetC>" \
         --sshsource "<SshSourceSG>" \
         --numhosts "<Capacity>" \
         --environment "<Environment>" \
         --ami "<ZookeeperAMI>" \
         --instancetype "<InstanceType>" \
         --instancerole "<IamRole>"

```


Would love to hear from you about this. Your feedback and suggestions are very much welcome through Issues and PRs :)
