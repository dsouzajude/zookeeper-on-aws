import logging

import nose.tools as nt
from mock import patch, ANY, Mock

from zkutils import zk, aws


class TestZkRemoveTerminated(object):
    ''' Tests that removing terminated zookeeper nodes functionality works '''

    @patch('zkutils.aws.get_log_streams')
    @patch('zkutils.zk._cmd_remove_zookeeper_ids')
    @patch('zkutils.aws.delete_log_streams')
    def test_removal_for_no_terminated_nodes(self,
                                             mock_delete_log_streams,
                                             mock_cmd_remove_zookeeper_ids,
                                             mock_get_log_streams):
        all_nodes = [str(i) for i in range(1, 3, 1)]
        running_nodes = [str(i) for i in range(1, 3, 1)]
        mock_get_log_streams.return_value = [
            {
                'logStreamName': str(i)
            } for i in all_nodes
        ]
        terminated_ids = zk.remove_zookeeper_nodes('eu-west-1',
                        '127.0.0.1', running_nodes, 'test-log-group')
        nt.assert_equals(mock_cmd_remove_zookeeper_ids.call_count, 0)
        nt.assert_equals(mock_delete_log_streams.call_count, 0)
        nt.assert_equals(terminated_ids, [])

    @patch('zkutils.aws.get_log_streams')
    @patch('zkutils.zk._cmd_remove_zookeeper_ids')
    @patch('zkutils.aws.delete_log_streams')
    def test_removal_for_one_terminated_node(self,
                                             mock_delete_log_streams,
                                             mock_cmd_remove_zookeeper_ids,
                                             mock_get_log_streams):
        all_nodes = [str(i) for i in range(1, 3, 1)]
        running_nodes = [str(i) for i in range(2, 4, 1)]
        mock_get_log_streams.return_value = [
            {'logStreamName': str(i)} for i in all_nodes
        ]
        terminated_ids = zk.remove_zookeeper_nodes('eu-west-1',
                        '127.0.0.1', running_nodes, 'test-log-group')
        nt.assert_equals(mock_cmd_remove_zookeeper_ids.call_count, 1)
        nt.assert_equals(mock_delete_log_streams.call_count, 1)
        nt.assert_equals(terminated_ids, '1')


class TestZkBootstrap(object):
    ''' Tests that Zookeeper bootstrap functionality works '''

    def setup(self):
        self.test_instance_id = 'i-abc111'
        self.num_instances = 3

    @patch('zkutils.aws.get_instance_id')
    @patch('zkutils.aws.get_tag')
    @patch('zkutils.aws.get_autoscaling_group')
    @patch('zkutils.aws.get_running_instances')
    @patch('zkutils.aws.set_tag')
    @patch('zkutils.utils.save_to_file')
    @patch('zkutils.zk._cmd_check_ensemble')
    @patch('zkutils.zk._cmd_start_zookeeper')
    @patch('zkutils.zk._cmd_delete_old_state')
    @patch('zkutils.zk._cmd_reset_config')
    def test_fresh_bootstrap_is_successful(self,
                                     mock_cmd_reset_config,
                                     mock_cmd_delete_old_state,
                                     mock_cmd_start_zookeeper,
                                     mock_cmd_check_ensemble,
                                     mock_save_to_file,
                                     mock_set_tag,
                                     mock_get_running_instances,
                                     mock_get_asgroup,
                                     mock_get_tag,
                                     mock_instance_id):
        mock_cmd_check_ensemble.return_value = '' # fresh bootstrap
        mock_get_tag.return_value = '1'
        mock_instance_id.return_value = self.test_instance_id
        mock_get_asgroup.return_value = {
            'AutoScalingGroupName': 'myAutoscalingGroup',
            'DesiredCapacity': self.num_instances
        }
        mock_running_instances = [
            {
                'InstanceId': 'i-abc11%s' % i,
                'NetworkInterfaces': [{'PrivateIpAddress': '127.0.0.%s' % i}],
                'Tags': [{'Key': zk.ZK_ID_TAG, 'Value': str(i)}]
            } for i in range(1, self.num_instances+1, 1)
        ]
        mock_running_instances[0]['InstanceId'] = self.test_instance_id
        mock_get_running_instances.return_value = mock_running_instances
        bootstrap_type = zk.do_bootstrap('eu-west-1',
                        'testdata/myid',
                        'testconf/zoo.cfg.dynamic',
                        'testconf',
                        'testdata',
                        'test-log-group')
        nt.assert_equals(mock_cmd_start_zookeeper.call_count, 1)
        nt.assert_equals(mock_set_tag.call_count, 1)
        nt.assert_equals(bootstrap_type, zk.BOOTSTRAP_TYPE_FRESH)

    @patch('zkutils.aws.get_instance_id')
    @patch('zkutils.aws.get_tag')
    @patch('zkutils.aws.set_tag')
    @patch('zkutils.aws.get_autoscaling_group')
    @patch('zkutils.aws.get_running_instances')
    @patch('zkutils.aws.get_log_streams')
    @patch('zkutils.utils.save_to_file')
    @patch('zkutils.zk._cmd_check_ensemble')
    @patch('zkutils.zk._cmd_start_zookeeper')
    @patch('zkutils.zk._cmd_delete_old_state')
    @patch('zkutils.zk._cmd_reset_config')
    @patch('zkutils.zk._cmd_get_zookeeper_configuration')
    @patch('zkutils.zk._cmd_add_zookeeper_id')
    def test_reconfigured_bootstrap_is_successful(self,
                                     mock_cmd_add_zookeeper_id,
                                     mock_cmd_get_zookeeper_configuration,
                                     mock_cmd_reset_config,
                                     mock_cmd_delete_old_state,
                                     mock_cmd_start_zookeeper,
                                     mock_cmd_check_ensemble,
                                     mock_save_to_file,
                                     mock_get_log_streams,
                                     mock_get_running_instances,
                                     mock_get_asgroup,
                                     mock_set_tag,
                                     mock_get_tag,
                                     mock_instance_id):
        mock_cmd_check_ensemble.return_value = 'follower' # Reconfig req.
        mock_instance_id.return_value = self.test_instance_id
        mock_get_tag.return_value = '1'
        mock_cmd_get_zookeeper_configuration.return_value = ''
        mock_get_log_streams.return_value = []
        mock_get_asgroup.return_value = {
            'AutoScalingGroupName': 'myAutoscalingGroup',
            'DesiredCapacity': self.num_instances
        }
        mock_running_instances = [
            {
                'InstanceId': 'i-abc11%s' % i,
                'NetworkInterfaces': [{'PrivateIpAddress': '127.0.0.%s' % i}],
                'Tags': [{'Key': zk.ZK_ID_TAG, 'Value': str(i)}]
            } for i in range(1, self.num_instances+1, 1)
        ]
        mock_running_instances[0]['InstanceId'] = self.test_instance_id
        mock_get_running_instances.return_value = mock_running_instances
        bootstrap_type = zk.do_bootstrap('eu-west-1',
                        'testdata/myid',
                        'testconf/zoo.cfg.dynamic',
                        'testconf',
                        'testdata',
                        'test-log-group')
        nt.assert_equals(mock_cmd_add_zookeeper_id.call_count, 1)
        nt.assert_equals(mock_cmd_start_zookeeper.call_count, 1)
        nt.assert_equals(mock_set_tag.call_count, 1)
        nt.assert_equals(bootstrap_type, zk.BOOTSTRAP_TYPE_RECONFIGURED)
