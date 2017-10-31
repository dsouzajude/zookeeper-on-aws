import time
import logging
from datetime import datetime

import aws, utils


log = logging.getLogger(__name__)

ZK_PORT = 2181
ZK_ID_TAG = 'zookeeper_id'
ASGROUP_TAG = 'aws:autoscaling:groupName'
MAX_INSTANCES = 10
CLAIMABLE_ZK_IDS = [str(num) for num in range(1, MAX_INSTANCES)]


def _cmd_start_zookeeper(conf_dir):
   return utils.run_command(
      """zkServer.sh --config {conf_dir} start """.format(conf_dir=conf_dir)
   )


def _cmd_check_ensemble(ip):
   return utils.run_command(
      "echo stat | nc {ip} 2181 | grep Mode".format(ip=ip)
   )


def _cmd_reset_config(dynamic_file, conf_dir):
   return utils.run_command(
      """sed -i 's/dynamicConfigFile=.*/dynamicConfigFile={dynamic_file}/' {conf_dir}/zoo.cfg
      """.format(
         dynamic_file=dynamic_file.replace("/", "\/"),
         conf_dir=conf_dir
      )
   )


def _cmd_get_zookeeper_configuration(ensemble_ip):
   return utils.run_command(
      """zkCli.sh -server {ip}:{port} get /zookeeper/config|grep ^server
      """.format(ip=ensemble_ip, port=ZK_PORT)
   )


def _cmd_delete_old_state(data_dir):
   return utils.run_command(
      """rm -rf {data_dir}/version-2/*""".format(data_dir=data_dir)
   )


def _cmd_remove_zookeeper_ids(ensemble_ip, terminated_ids):
   return utils.run_command(
      """zkCli.sh \
            -server {ensemble_ip}:{port} \
            reconfig -remove {terminated_ids}
      """.format(
         ensemble_ip=ensemble_ip,
         port=ZK_PORT,
         terminated_ids=terminated_ids
      )
   )


def _cmd_add_zookeeper_id(ensemble_ip, zookeeper_ip, zookeeper_id):
   return utils.run_command(
      """zkCli.sh \
            -server {ensemble_ip}:{port} \
            reconfig -add "server.{id}={zk_ip}:2888:3888:participant;{port}"
      """.format(
         ensemble_ip=ensemble_ip,
         port=ZK_PORT,
         zk_ip=zookeeper_ip,
         id=zookeeper_id
      )
   )


def initialize(region, instance_id, id_file, log_group):
   ''' Initializes the zookeeper instance with a valid zookeeper id '''
   log.info('Initializing instance, instance_id=%s' % instance_id)
   zk_id = aws.get_tag(region, instance_id, ZK_ID_TAG)
   if not zk_id:
      zk_id = get_zookeeper_id(region, log_group)
      aws.set_tag(region, instance_id, ZK_ID_TAG, zk_id)
   utils.save_to_file(id_file, zk_id)
   log.info('Initialized with zookeeper_id=%s' % zk_id)
   return zk_id


def get_zookeeper_id(region, group_name):
   ''' Gets an unclaimed zookeeper id that is unique and which does not
   clash with any functional zookeeper id. It guarantees this property
   with the help of CloudWatch Logs.
   '''
   for zkid in CLAIMABLE_ZK_IDS:
      success = aws.create_log_stream(region, group_name, zkid)
      if success:
         return zkid
   raise Exception("No zookeeper id available")


def get_zookeeper_instances(region,
                            asgroup_tag,
                            asgroup_name,
                            zk_id_tag,
                            capacity):
   ''' Returns running instances of zookeeper.
   This method will continue to loop until we get all running instances
   in the cluster as set in the autoscaling group.
   '''
   # Loop indefinitely until we get a total of capacity
   # as setup in the autoscaling group. This is important because we need
   # to bootstrap the cluster with that many instances.
   # Not only should the instances be running but their `zookeeper_id`
   # tag should also be set.
   tag_value_pairs = [
      (asgroup_tag, [asgroup_name]),
      (zk_id_tag, CLAIMABLE_ZK_IDS)
   ]

   log.info('Getting all running zookeeper instances')
   instances = []
   while True:
      instances = aws.get_running_instances(region, tag_value_pairs)
      log.info('Found=%s, Actual=%s' % (len(instances), capacity))
      if len(instances) >= capacity:
         break
      else:
         log.info('Waiting for all ZK instances to be up and running ...')
         time.sleep(30) # seconds

   log.info('Got all running, count=%s' % len(instances))
   return instances


def get_terminated_zookeeper_ids(region, running_ids, log_group):
   ''' Gets the zookeeper_ids of terminated EC2 instances.
   This is the difference from the list of ids in the LogGroup with
   already running ids.
   '''
   streams = aws.get_log_streams(region, log_group)
   ids = [s['logStreamName'] for s in streams]
   terminated_ids = set(ids) - set(running_ids)
   return list(terminated_ids)


def start_zookeeper(conf_dir):
   ''' Starts zookeeper server. '''
   log.info('Starting Zookeeper server')
   try:
      _cmd_start_zookeeper(conf_dir)
   except utils.CommandError as ex:
      log.error(ex.stderr)
      if 'JMX' not in str(ex):
         raise
   log.info(ex.stdout)
   log.info('Zookeeper started.')


def check_ensemble(ips):
   ''' Checks if there is a zookeeper ensemble up and running
   by using the 4 letter word command.

   Note that other ZK nodes can fail in the cluster but if we are able
   to connect successfully to one instance and run the 4letter word
   command we have atleast a majority running and therefore a
   functional ensemble.

   Returns a valid ip if there is a functional ensemble otherwise None.

   If there is no quorum, the ensemble will not be functional.
   '''
   log.info('Checking for existing ensemble')
   for ip in ips:
      log.info('Trying to connect with %s' % ip)
      retry_count = 3
      while retry_count > 0:
         try:
            stdout = _cmd_check_ensemble(ip)
            is_functional = 'leader' in stdout or 'follower' in stdout
            if is_functional:
               log.info('Ensemble is functional. Connected to %s' % (ip))
               return ip
         except utils.CommandError as ex:
            log.error('Failed to connect to %s with error' % (ip, str(ex)))
         retry_count -= 1
         time.sleep(3)
   log.info('Ensemble is not functional')


def is_leader(ip="localhost"):
   ''' Returns True if node is the leader and False if otherwise. '''
   return "leader" in _cmd_check_ensemble(ip)


def add_zookeeper_node(ensemble_ip, zookeeper_ip, zookeeper_id):
   ''' Adds a zookeeper node to the ensemble. '''
   return _cmd_add_zookeeper_id(ensemble_ip, zookeeper_ip, zookeeper_id)


def remove_zookeeper_nodes(region, ensemble_ip, running_ids, log_group):
   ''' Removes zookeeper nodes from the ensemble.
   Also removes the log streams associated with them.

   We need to retry this logic due to race conditions from other
   Zookeeper EC2 instances booting up at the same time and running this code.
   '''
   retry_count = 3
   while retry_count > 0:
      terminated_ids = get_terminated_zookeeper_ids(
                           region,
                           running_ids,
                           log_group
                        )
      if terminated_ids:
         terminated_ids = ",".join(terminated_ids)
         try:
            log.info('Removing ids=%s' % terminated_ids)
            _cmd_remove_zookeeper_ids(ensemble_ip, terminated_ids)
            log.info('Removing log streams=%s' % terminated_ids)
            aws.delete_log_streams(region, log_group, terminated_ids)
            return terminated_ids
         except utils.CommandError as ex:
            log.error('Retrying.. %s' % ex)
            time.sleep(3)
      else:
         log.info("No terminations found, terminated_ids=%s" % terminated_ids)
         return terminated_ids
      retry_count -= 1
   raise Exception("Terminated zookeeper_ids not removed correctly.")


def reconfigure_ensemble(region, zookeeper_id, zookeeper_ip, running_ids,
                         ensemble_ip, dynamic_file, conf_dir, log_group):
   ''' Reconfigures the zookeeper ensemble by adding a new server to it. '''

   # Get and reset the static configuration
   # The static file changes the path of the dynamic file location.
   log.info('Resetting static configuration')
   _cmd_reset_config(dynamic_file, conf_dir)

   # Add host as an observer to the ensemble configuration
   log.info('Resetting dynamic configuration')
   config = _cmd_get_zookeeper_configuration(ensemble_ip)
   config += "\nserver.{id}={ip}:2888:3888:observer;{port}".format(
      id=zookeeper_id,
      ip=zookeeper_ip,
      port=ZK_PORT
   )
   utils.save_to_file(dynamic_file, config)
   start_zookeeper(conf_dir)

   # Wait a bit for Zookeeper to initialize itself
   # For some reason it crashes the moment we try to reconfigure it
   time.sleep(30)

   # Remove ids from the ensemble
   log.info('Reconfiguration by removing')
   remove_zookeeper_nodes(region, ensemble_ip, running_ids, log_group)

   # Add host as participant to the ensemble with "add" command
   log.info('Reconfiguration by adding')
   log.info('Adding id %s' % zookeeper_id)
   add_zookeeper_node(ensemble_ip, zookeeper_ip, zookeeper_id)
   log.info('Ensemble Reconfigured.')


def configure_ensemble(zk_id_ip_pairs, dynamic_file, conf_dir, data_dir):
   '''Configures zookeeper ensemble with zookeeper instances.
   After configuration, it starts the zookeeper server.
   '''
   log.info('Doing a fresh Zookeeper ensemble configuration')
   log.info('Wiping out old state')
   _cmd_delete_old_state(data_dir)

   log.info('Resetting static configuration')
   _cmd_reset_config(dynamic_file, conf_dir)

   # Add hosts as participants to the ensemble configuration
   log.info('Resetting dynamic configuration')
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
   utils.save_to_file(dynamic_file, ensemble_config)
   start_zookeeper(conf_dir)
   log.info('Ensemble Configured.')


def do_bootstrap(region, id_file, dynamic_file,
                 conf_dir, data_dir, log_group):
   ''' Bootstraps the zookeeper cluster if it does not exists
   otherwise it bootstraps this instance to join the cluster
   via dynamic reconfiguration.
   '''
   log.info('Bootstrapping ...')

   # Initialize Zookeeper instance
   instance_id = aws.get_instance_id()
   zookeeper_id = initialize(region, instance_id, id_file, log_group)

   # Get the autoscaling group
   asgroup = aws.get_autoscaling_group(region, ASGROUP_TAG, instance_id)
   asgroup_name = asgroup['AutoScalingGroupName']
   capacity = asgroup['DesiredCapacity']

   # Get all zookeeper instances in the autoscaling group
   zk_instances = get_zookeeper_instances(
      region,
      ASGROUP_TAG,
      asgroup_name,
      ZK_ID_TAG,
      capacity
   )

   # Getting running zookeeper ids and ips to to formulate
   # or join an existing ensemble.
   zk_ip = None
   zk_other_ips = []
   zk_all_ips = []
   zk_all_ids = []
   zk_id_ip_pairs = []
   log.info('Getting (id, ip) pairs')
   for i in zk_instances:
      ip = i['NetworkInterfaces'][0]['PrivateIpAddress']
      if i['InstanceId'] == instance_id:
         zk_ip = ip
         zk_id_ip_pairs.append((zookeeper_id, ip))
         zk_all_ids.append(zookeeper_id)
         log.info('My zookeeper_id=%s zookeeper_ip=%s' % (zookeeper_id, zk_ip))
      else:
         zk_other_ips.append(ip)
         tags = i['Tags']
         tags = [t for t in tags if t['Key']==ZK_ID_TAG]
         zk_other_id = tags[0]['Value']
         log.info('Other zookeeper_id=%s zookeeper_ip=%s' % (zk_other_id, ip))
         zk_id_ip_pairs.append((zk_other_id, ip))
         zk_all_ids.append(zk_other_id)
      zk_all_ips.append(ip)

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

   # Check for valid ensemble then decide to freshly configure
   # a new ensemble or dynamically reconfigure the existing one
   valid_ip = check_ensemble(zk_other_ips)
   if valid_ip:
      log.info('Reconfiguring ensemble with new server')
      reconfigure_ensemble(
         region,
         zookeeper_id,
         zk_ip,
         zk_all_ids,
         valid_ip,
         dynamic_file,
         conf_dir,
         log_group
      )
   else:
      log.info('Configuring ensemble with all servers')
      configure_ensemble(
         zk_id_ip_pairs,
         dynamic_file,
         conf_dir,
         data_dir
      )

   # Set bootstrap finished tag
   log.info('Setting `bootstrap_finished_time` tag')
   now = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
   aws.set_tag(region, instance_id, "bootstrap_finished_time", now)
   log.info('Bootstrap completed')
