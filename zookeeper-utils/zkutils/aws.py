import boto3
import botocore
import requests


def get_instance_id():
   ''' Returns the current EC2's instance id. '''
   resp = requests.get('http://169.254.169.254/latest/meta-data/instance-id')
   instance_id = resp.text
   return instance_id


def get_tag(region, instance_id, tag_key):
   ''' Gets the current EC2 tag for an EC2 instance
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
   ''' Sets the EC2 tag on the current instance. '''
   ec2 = boto3.resource('ec2', region)
   tag = ec2.create_tags(
            Resources=[instance_id],
            Tags=[
               {
                  'Key': tag_key,
                  'Value': tag_value
               }
            ]
         )


def create_log_stream(region, group_name, stream_name):
   cwlogs = boto3.client('logs', region)
   try:
      cwlogs.create_log_stream(
         logGroupName=group_name,
         logStreamName=stream_name
      )
      return True
   except botocore.exceptions.ClientError as ex:
      if ex.response['Error']['Code'] == "ResourceAlreadyExistsException":
         return False
      else:
         raise


def get_log_streams(region, group_name):
   cwlogs = boto3.client('logs', region)
   response = cwlogs.describe_log_streams(logGroupName=group_name)
   streams = response['logStreams']
   return streams


def delete_log_streams(region, log_group, stream_names):
   ''' Deletes log streams. '''
   cwlogs = boto3.client('logs', region)
   for name in stream_names:
      cwlogs.delete_log_stream(
         logGroupName=log_group,
         logStreamName=name
      )
      print 'Deleted stream=%s' % name


def get_running_instances(region, tag_value_pairs):
   ''' Returns running EC2 instances that have the desired tags. '''
   ec2 = boto3.client('ec2', region)
   filters = [
      {
         'Name': 'tag:%s' % key,
         'Values': values
      } for key,values in tag_value_pairs
   ]
   filters += [
      {
         'Name': 'instance-state-name',
         'Values': ['pending', 'running']
      }
   ]
   response = ec2.describe_instances(Filters=filters)
   reservations = response['Reservations']
   instances = [r['Instances'][0] for r in reservations]
   return instances


def get_autoscaling_group(region, autoscaling_tag, instance_id):
   ''' Returns the autoscaling group of the current EC2 instance '''
   ec2 = boto3.client('ec2', region)
   response = ec2.describe_instances(InstanceIds=[instance_id])
   instance = response['Reservations'][0]['Instances'][0]
   tags = instance['Tags']
   asgroup_name = None
   for tag in tags:
      if tag["Key"] == autoscaling_tag:
         asgroup_name = tag["Value"]
         break

   autoscaling = boto3.client('autoscaling', region)
   response = autoscaling.describe_auto_scaling_groups(
      AutoScalingGroupNames=[asgroup_name]
   )
   asgroup = response['AutoScalingGroups'][0]
   return asgroup
