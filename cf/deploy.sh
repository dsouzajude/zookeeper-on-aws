#!/bin/sh

python CFZookeeper.py \
         --stackname zookeeper \
         --keyname jude-zk \
         --vpcid vpc-5125ef34 \
         --subnets subnet-04f4375d subnet-673bbd02 subnet-c4ca64b3 \
         --sshsource sg-7728b912 \
         --internalsource sg-7728b912 \
         --numhosts 3 \
         --environment Test \
         --ami ami-dfaf75a6 \
         --instancetype m4.large \
         --instancerole wrapp-ec2-host
