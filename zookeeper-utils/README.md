Zookeeper Utils library
=======================
A utility for Zookeeper Bootstrapping, Dynamic Reconfiguration and Automatic detection and recovery of Quorum failure. This library is designed specifically for the requirements of this setup.


What does it do
===============
This library has functionality to do the following:

- Fresh bootstrapping
- Dynamic Reconfiguration
- Automatic Detection and Recovery of Quorum Failure


How does it do it
=================
The `scripts/zk-bootstrap` script bootstraps the cluster by getting the list of running Zookeeper EC2 instances that are configured in the autoscaling group. During the bootstrap, it would wait until there are atleast `n` instances up and running where `n` is the desired capacity as configured in the autoscaling group. This is important because it is needed for cluster membership information and to determine a majority for a functional quorum. Each Zookeeper instance would be running the same code and once atleast `n` instances are up and running, the script generates the dynamic file configuration and starts the Zookeeper server. From there on these instances will form the cluster via the Zookeeper protocol.

If there is already a functional quorum in place when another instance is launched, the script would recognize this by issuing the 4letter word `stat` command. If all is good, it should return either a `leader` or `follower` mode otherwise this would mean that no quorum exists and it needs to do a fresh bootstrap or recovery. If quorum does exist it simply does a dynamic reconfiguration of the cluster via one of the functional nodes in the cluster by issuing the `add` command. Prior to this it will check for terminated EC2 instances that are still part of the cluster and issue the `remove` command to remove them so that the quorum is maintained with the correct functional nodes.

For automatic detection and recovery of quorum failure, the `scripts/zk-recovery` is recommended to run as a cronjob on a per minute interval on every node of the cluster. It checks to see if there is a functional quorum and if there isn't, it would attempt to recover the quorum via a fresh bootstrap again.


Installation
============

```bash

>> cd zookeeper-utils
>> python setup.py install

```


To Bootstrap or Dynamically Reconfigure the cluster
===================================================
Assuming after installation the `scripts/zk-bootstrap` script is installed under `/usr/local/bin` directory, run the script via the following command:


```bash

>> /usr/local/bin/zk-bootstrap \
                  --region "<Region>" \
                  --id-file "<Path-to-ZkIdFile>" \
                  --dynamic-file "<Path-to-ZkDynamicFile>" \
                  --conf-dir "<Path-to-ZkConfDir>" \
                  --data-dir "<Path-to-ZkDataDir>" \
                  --log-group "<AwsLogGroup>"

```

To run Recovery
===============
It is recommended to run as a cronjob on a per minute interval. You can also manually run the script via the following command assuming after installation the `scripts/zk-recovery` is installed under `/usr/local/bin` directory:

```bash

>> export REGION="<Region>"
>> /usr/local/bin/zk-recovery >> /var/log/zk-recovery.log 2>&1

```


Would love to hear from you about this. Your feedback and suggestions are very much welcome through Issues and PRs :)
