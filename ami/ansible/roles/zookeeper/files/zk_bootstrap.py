import os
import time
import socket
import subprocess
from datetime import datetime

import argparse
import requests
import boto3
import botocore

'''

This script is intended to configure and bootstrap the zookeeper cluster.

For the bootstrapping we require two files to be configured:
   - File that contains the machine id:
       {ZK_DATA_DIR}/myid
   - File that contains the list of servers:
       {ZK_CONF_DIR}/zoo.dynamic.cfg


Challenges:

 1. Fresh vs Existing bootstrap:

   Determining if a fresh bootstrap of a zookeeper cluster
   is needed or the there exists a cluster but needs
   dynamic reconfiguration to allow this current host
   to participate in the cluster.

   - Fresh bootstrap means, there is no zookeeper cluster
   or nodes are just started and need to form a cluster.
     - In this case, the active zookeepers would need
       to generate the {ZK_CONF_DIR}/zoo.dynamic.cfg and
       use that to form the cluster.

   - Dynamic Reconfiguration means there is a zookeeper cluster
   that this host can connet to and using that connection
   add itself to the cluster.

 2. Assigning unique zookeeper id:

   The challenge with this is to somehow not have clashing zookeeper ids
   which means we would need to avoid any kind of race condition if possible
   so that no two zookeeper instances share the same id.

   The id must be decided upon boot. For a fresh launch of the instance,
   it should pick an unclaime id that no other zookeeper instance has claimed.
   For a restart of the same instance, it should use the already assinged
   zookeeper id.

   Once the id is assigned we determine whether it is a fresh bootstrap of the
   cluster or just a dynamic configuration is needed and accordingly proceed
   to the bootstrap process.

 3. Removing terminated zookeeper instances

   We need a way to remove zookeeper instances that were once part of the
   cluster after they have been terminated otherwise they would
   zookeeper would think they are part of the cluster but unavailable
   and hence it would break the quorum.

'''

ZK_PORT = 2181
ZK_ID_TAG = 'zookeeper_id'
ZK_LOG_GROUP = '/zookeeper/instances'
ZK_PATH = '/opt/zookeeper/bin'
MAX_INSTANCES = 10


class CommandError(Exception):
   def __init__(self, stdout, stderr):
      self.stdout = stdout
      self.stderr = stderr
      super(CommandError, self)\
         .__init__("stdout: {stdout}\nstderr: {stderr}" \
         .format(stdout=stdout,stderr=stderr))


def _run_command(command):
   result = subprocess.Popen(
               command,
               shell=True,
               stdout=subprocess.PIPE,
               stderr=subprocess.PIPE
            )
   stdout, stderr = result.communicate()
   stdout = stdout.strip()
   stderr = stderr.strip()
   if stderr:
      raise CommandError(stdout, stderr)
   return stdout


def save_to_file(filename, content):
   ''' Performs backup of existing file and saves the new
   content to the file.
   '''
   content = str(content)

   # Backup old content
   if os.path.isfile(filename):
      backup_filename = '{filename}.bk'.format(filename=filename)
      with open(backup_filename, 'w') as fwrite:
         with open(filename, 'r') as fread:
            old_content = fread.read()
         fwrite.write(old_content)

   # Save new content
   with open(filename, 'w') as fwrite:
      fwrite.write(content)


def get_instance_id():
   ''' Returns the current EC2's instance id. '''
   resp = requests.get('http://169.254.169.254/latest/meta-data/instance-id')
   instance_id = resp.text
   return instance_id


def get_autoscaling_group(region):
   ''' Returns the autoscaling group of the current EC2 instance '''
   ec2 = boto3.client('ec2', region)
   instance_id = get_instance_id()
   response = ec2.describe_instances(InstanceIds=[instance_id])
   instance = response['Reservations'][0]['Instances'][0]
   tags = instance['Tags']
   asgroup_name = None
   for tag in tags:
      if tag["Key"] == 'aws:autoscaling:groupName':
         asgroup_name = tag["Value"]
         break

   autoscaling = boto3.client('autoscaling', region)
   response = autoscaling.describe_auto_scaling_groups(
      AutoScalingGroupNames=[asgroup_name]
   )
   asgroup = response['AutoScalingGroups'][0]
   return asgroup


def get_zookeeper_instances(region):
   ''' Returns instances of zookeeper.
   This method will continue to loop until we get all running instances
   in the cluster as set in the autoscaling group.
   '''
   asgroup = get_autoscaling_group(region)
   asgroup_name = asgroup['AutoScalingGroupName']
   num_instances = asgroup['DesiredCapacity']
   ec2 = boto3.client('ec2', region)

   # Loop indefinitely until we get a total of num_instances
   # as setup in the autoscaling group
   # This is important because we need to bootstrap the cluster with
   # that many instances.
   # Not only should the instances be running but their `zookeeper_id`
   # tag should also be set
   while True:
      response = ec2.describe_instances(
         Filters=[
            {
               'Name': 'tag:aws:autoscaling:groupName',
               'Values': [asgroup_name]
            },
            {
               'Name': 'tag:zookeeper_id',
               'Values': [str(num) for num in range(1, MAX_INSTANCES)]
            }
         ]
      )
      reservations = response['Reservations']
      instances = [r['Instances'][0] for r in reservations]
      instances = [
         i for i in instances if i['State']['Name'] in ['running', 'pending']
      ]

      print 'Found=%s, Actual=%s' % (len(instances), num_instances)
      if len(instances) >= num_instances:
         break
      else:
         print 'Waiting for all ZK instances to be up and running ...'
         time.sleep(60) # seconds

   return instances


def get_zookeeper_id(region, log_group):
   ''' Gets an unclaimed zookeeper id that is unique and which does not
   clash with any functional zookeeper id. It guarantees this property
   with the help of CloudWatch Logs.
   '''
   cwlogs = boto3.client('logs', region)
   for zkid in range(1, MAX_INSTANCES):
      try:
         cwlogs.create_log_stream(
            logGroupName=log_group,
            logStreamName=str(zkid)
         )
         return zkid
      except botocore.exceptions.ClientError as ex:
         if ex.response['Error']['Code'] == "ResourceAlreadyExistsException":
            continue
         else:
            raise
   raise Exception("No zookeeper id available")


def get_tag(region, instance_id, tag_key):
   ''' Gets the current EC2 zookeeper_id tag on the current instance
   if there is any tag set. '''
   ec2 = boto3.client('ec2', region)
   response = ec2.describe_instances(InstanceIds=[instance_id])
   instance = response['Reservations'][0]['Instances'][0]
   tags = instance['Tags']
   tag_value = None
   for tag in tags:
      if tag["Key"] == tag_key:
         tag_value = tag["Value"]
   return tag_value


def set_tag(region, instance_id, tag_key, tag_value):
   ''' Sets the EC2 zookeeper_id tag on the current instance. '''
   ec2 = boto3.resource('ec2', region)
   tag = ec2.create_tags(
            Resources=[instance_id],
            Tags=[
               {
                  'Key': tag_key,
                  'Value': str(tag_value)
               }
            ]
         )


def start_zookeeper(conf_dir):
   try:
      _run_command(
         """{zk_path}/zkServer.sh --config {conf_dir} start
         """.format(zk_path=ZK_PATH, conf_dir=conf_dir)
      )
   except CommandError as ex:
      print ex.stderr
      if 'JMX' not in str(ex):
         raise
   print ex.stdout


def check_ensemble(ips):
   ''' Checks if there is a zookeeper ensemble up and running
   by using the 4 letter word command.

   Note that other ZK nodes can fail in the cluster but if we are able
   to connect successfully to one instance and run the 4letter word
   command we have atleast a majority running and therefore a
   functional ensemble.

   Returns a valid ip if there is a functional ensemble otherwise None.
   '''
   for ip in ips:
      print 'Trying to connect with %s' % ip
      retry_count = 3
      while retry_count > 0:
         try:
            s = socket.socket()
            s.settimeout(1)
            s.connect((ip, ZK_PORT))
            s.send('stat')
            s.close()
            print 'Ensemble is functional. Connected to %s' % (ip)
            return ip
         except socket.error, e:
            print 'Unable to connect to %s' % (ip)
            retry_count -= 1
            time.sleep(3)
   print 'Ensemble is not functional'


def reconfigure_ensemble(zookeeper_id,
                         zookeeper_ip,
                         ensemble_ip,
                         dynamic_file):
   ''' Reconfigures the zookeeper ensemble by adding a new server to it. '''

   # Get the current configuration
   config =_run_command(
      """{zk_path}/zkCli.sh \
                  -server {ip}:{port} get /zookeeper/config|grep ^server
      """.format(zk_path=ZK_PATH, ip=ensemble_ip, port=ZK_PORT))

   # Add host as an observer to the ensemble configuration
   config += "server.{id}={ip}:2888:3888:observer;{port}".format(
      id=zookeeper_id,
      ip=zookeeper_ip,
      port=ZK_PORT
   )
   save_to_file(dynamic_file, config)

   # Add host as participant to the ensemble with "add" command
   _run_command(
      """{zk_path}/zkCli.sh \
            -server {ensemble_ip}:{port} \
            reconfig -add "server.{id}={zk_ip}:2888:3888:participant;{port}"
      """.format(
         zk_path=ZK_PATH,
         ensemble_ip=ensemble_ipd,
         port=port,
         zk_ip=zookeeper_ip,
         id=zookeeper_id
      )
   )


def configure_ensemble(zk_id_ip_pairs, dynamic_file):
   '''Configures zookeeper ensemble with zookeeper instances. '''
   configs = []
   for pair in zk_id_ip_pairs:
      zk_id = pair[0]
      zk_ip = pair[1]
      config = """server.{id}={ip}:2888:3888:participant;{port}""".format(
         id=zk_id,
         ip=zk_ip,
         port=ZK_PORT
      )
      configs.append(config)

   ensemble_config = '\n'.join(configs)
   save_to_file(dynamic_file, ensemble_config)


def do_bootstrap(region, id_file, dynamic_file, conf_dir):
   ''' Bootstraps the zookeeper cluster if it does not exists
   otherwise it bootstraps this instance to join the cluster
   via dynamic reconfiguration.
   '''
   # Get the zookeeper_id
   instance_id = get_instance_id()
   print 'InstanceId=%s' % instance_id
   zk_id = get_tag(region, instance_id, ZK_ID_TAG)
   if not zk_id:
      zk_id = get_zookeeper_id(region, ZK_LOG_GROUP)
      set_tag(region, instance_id, ZK_ID_TAG, zk_id)

   print 'ZookeeperId=%s' % zk_id
   save_to_file(id_file, zk_id)
   print 'Saved ZookeeperId to file=%s' % id_file

   # Determine if there is a functional zk ensemble.
   # Even if there is an ensemble but does not have a quorum (or majority
   # of functional nodes) the ensemble will not be functional and
   # will not accept connections on the client ports.
   #
   # The loss of the last majority-making member in any N-member quorum
   # would imply a complete failure of quorum, and the remaining peers will
   # shut off their client serving port and go into a 'waiting' mode for
   # members to reappear to form a majority for leader re-election again.

   # As per docs:
   #  As long as a majority of the servers are available,
   #  the ZooKeeper service will be available.
   #  https://zookeeper.apache.org/doc/r3.1.2/zookeeperAdmin.html
   print 'Getting all Zookeeper instances'
   zk_instances = get_zookeeper_instances(region)
   print 'Total instances=%s' % len(zk_instances)
   zk_id_ip_pairs = []
   zk_ip = None
   zk_other_ips = []
   zk_all_ips = []
   print 'Getting (id, ip) pairs'
   for i in zk_instances:
      ip = i['NetworkInterfaces'][0]['PrivateIpAddress']
      if i['InstanceId'] == instance_id:
         zk_ip = ip
         zk_id_ip_pairs.append((zk_id, ip))
      else:
         zk_other_ips.append(ip)
         tags = i['Tags']
         tags = [t for t in tags if t['Key']==ZK_ID_TAG]
         zk_other_id = tags[0]['Value']
         zk_id_ip_pairs.append((zk_other_id, ip))
      zk_all_ips.append(ip)

   print 'Checking for a functional ensemble'
   valid_ip = check_ensemble(zk_other_ips)
   if valid_ip:
      print 'Reconfiguring ensemble with new server'
      reconfigure_ensemble(zk_id, zk_ip, valid_ip, dynamic_file)
   else:
      print 'Configuring ensemble with all servers'
      configure_ensemble(zk_id_ip_pairs, dynamic_file)

   # Start the zookeeper server
   print 'Starting Zookeeper server'
   start_zookeeper(conf_dir)
   print 'Zookeeper started.'


   # Set bootstrap finished tag
   print 'Setting `bootstrap_finished_time` tag'
   now = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
   set_tag(region, instance_id, "bootstrap_finished_time", now)


def _parse_args():
    parser = argparse.ArgumentParser(
        prog='python zk_bootstrap.py',
        usage='%(prog)s [options]',
        description='Bootstrap script for the Zookeeper Ensemble.'
    )
    parser.add_argument(
        '--region',
        type=str,
        nargs=1,
        metavar=("<AWS_REGION>"),
        help='AWS Region.'
    )
    parser.add_argument(
        '--id-file',
        type=str,
        nargs=1,
        metavar=("<PATH-TO-ID-FILE>"),
        help='Path to the ID File.'
    )
    parser.add_argument(
        '--dynamic-file',
        type=str,
        nargs=1,
        metavar=("PATH-TO-DYNAMIC-FILE"),
        help='Path to the dynamic reconfig file.'
    )
    parser.add_argument(
        '--conf-dir',
        type=str,
        nargs=1,
        metavar=("PATH-TO-CONF-DIRECTORY"),
        help='Path to the conf directory.'
    )
    return parser


def main():
   ''' This program bootstraps the zookeeper cluster. If the cluster already
   exists and is functional, it will bootstrap this instance to join the
   cluster via dynamic reconfiguration.

   During the bootstrap, the zookeeper_id will be generated for this instance
   and saved to the ${ZOOKEEPER_DATA_DIR}/myid file.

   Also, the dynamic config will be generated for a fresh bootstrap if the
   cluster does not already exists otherwise the instance will join the
   existing cluster.

   To run bootstrap:

      zk_bootstrap --region <AWS-REGION> \
                   --id-file <PATH-TO-ID-FILE> \
                   --dynamic-file <PATH-TO-DYNAMIC-FILE> \
                   --conf-dir <PATH-TO-CONF-DIRECTORY>
   '''
   parser = _parse_args()
   args = vars(parser.parse_args())
   try:
      region = args['region'][0]
      id_file = args['id_file'][0]
      dynamic_file = args['dynamic_file'][0]
      conf_dir = args['conf_dir'][0]
   except:
      parser.print_help()
      raise

   print 'Doing a bootstrap'
   do_bootstrap(region, id_file, dynamic_file, conf_dir)
   print 'Bootstrap completed'


if __name__=='__main__':
   main()


# TODO
# Remove old zookeeper machine that was terminated
# Cron job for removing all inactive zookeeper ids
