import json
import yaml
import argparse

import boto3
import botocore

from troposphere import (
    Parameter, Output, Ref, Select, Tags, Template, GetAZs
)
from troposphere.ec2 import (
    SecurityGroup,
    SecurityGroupRule
)
from troposphere.autoscaling import(
    LaunchConfiguration,
    AutoScalingGroup,
    Tag
)
from troposphere.policies import (
    AutoScalingReplacingUpdate,
    AutoScalingRollingUpdate,
    UpdatePolicy
)


template = Template()


### Inputs


keyname = template.add_parameter(
    Parameter(
        "KeyName",
        Description="Name of existing KeyPair for SSH access to instance",
        Type="String"
    )
)

vpcid = template.add_parameter(
    Parameter(
        "VpcId",
        Description="VpcId of your existing Virtual Private Cloud (VPC)",
        Type="String"
    )
)

subnetid_a = template.add_parameter(
    Parameter(
        "SubnetIdA",
        Description="Private Subnet Id in zone A",
        Type="String"
    )
)

subnetid_b = template.add_parameter(
    Parameter(
        "SubnetIdB",
        Description="Private Subnet Id in zone B",
        Type="String"
    )
)

subnetid_c = template.add_parameter(
    Parameter(
        "SubnetIdC",
        Description="Private Subnet Id in zone C",
        Type="String"
    )
)

zk_ssh_source = template.add_parameter(
    Parameter(
        "ZkSshSource",
        Description="The SecurityGroup source for SSH connections",
        Type="String",
        Default="0.0.0.0/0"
    )
)

zk_internal_source = template.add_parameter(
    Parameter(
        "ZkInternalSource",
        Description="The SecurityGroup source for internal connections",
        Type="String",
        Default="0.0.0.0/0"
    )
)

num_hosts = template.add_parameter(Parameter(
    "NumHosts",
    Default="3",
    Type="String",
    Description="Number of zookeepers servers to run",
))


environment = template.add_parameter(Parameter(
    "Environment",
    Type="String",
    Description="The environment being deployed into",
))

ami_id = template.add_parameter(Parameter(
    "AmiId",
    Type="String",
    Description="The AMI to use for Zookeeper instances",
))

instance_type = template.add_parameter(Parameter(
    "InstanceType",
    Type="String",
    Description="The instance type to use for Zookeeper instances",
))

instance_role = template.add_parameter(Parameter(
    "InstanceRole",
    Type="String",
    Description="The role the Zookeeper EC2 instance would assume",
))

### Resources


# Security Group for Zookeeper
security_group = template.add_resource(SecurityGroup(
    "ZkSecurityGroup",
    GroupDescription="Security group for access to Zookeeper",
    SecurityGroupIngress=[
        SecurityGroupRule(
                IpProtocol='tcp',
                FromPort='22',
                ToPort='22',
                SourceSecurityGroupId=Ref(zk_ssh_source)
        ),
        SecurityGroupRule(
                IpProtocol='tcp',
                FromPort='0',
                ToPort='0',
                SourceSecurityGroupId=Ref(zk_internal_source)
        )
    ],
    VpcId=Ref(vpcid),
    Tags=Tags(Name='zookeeper', Environment=Ref(environment))
))


# Launch Configuration for Zookeeper
launch_config = template.add_resource(LaunchConfiguration(
    "ZkLaunchConfig",
    KeyName=Ref(keyname),
    InstanceType=Ref(instance_type),
    SecurityGroups=[Ref(security_group)],
    ImageId=Ref(ami_id),
    IamInstanceProfile=Ref(instance_role)
))


# Autoscaling Group for Zookeeper
autoscaling_group = template.add_resource(AutoScalingGroup(
    "ZkAutoscalingGroup",
    LaunchConfigurationName=Ref(launch_config),
    MinSize=Ref(num_hosts),
    MaxSize=Ref(num_hosts),
    DesiredCapacity=Ref(num_hosts),
    AvailabilityZones=GetAZs(""),
    VPCZoneIdentifier=[
        Ref(subnetid_a),
        Ref(subnetid_b),
        Ref(subnetid_c)
    ],
    Tags=[
        Tag("Environment", Ref(environment), True),
        Tag("Name", "zookeeper", True)
    ],
    UpdatePolicy=UpdatePolicy(
        AutoScalingReplacingUpdate=AutoScalingReplacingUpdate(
            WillReplace=True,
        ),
        AutoScalingRollingUpdate=AutoScalingRollingUpdate(
            PauseTime='PT5M',
            MinInstancesInService="1",
            MaxBatchSize='1',
            WaitOnResourceSignals=True
        )
    )
))


### Outputs


template.add_output([
    Output(
        "ZkSecurityGroup",
        Value=Ref(security_group)
    ),
    Output(
        "ZkAutoscalingGroup",
        Value=Ref(autoscaling_group)
    ),
    Output(
        "ZkLaunchConfig",
        Value=Ref(launch_config)
    )
])


### Program to deploy the CloudFormation Stack


def _stack_exists(stack_name):
    """ Checks if the stack exists.
    Returns True if it exists and False if not.
    """
    cf = boto3.client('cloudformation')
    exists = False
    try:
        cf.describe_stacks(StackName=stack_name)
        exists = True
    except botocore.exceptions.ClientError as ex:
        if ex.response['Error']['Code'] == 'ValidationError':
            exists = False
        else:
            raise
    return exists


def create_stack(stack_name, template_body, params):
    """ Creates the stack given the template. """
    cf = boto3.client('cloudformation')
    resp = cf.create_stack(
        StackName=stack_name,
        TemplateBody=template_body,
        Parameters=params,
        Tags=[{'Key': 'Name', 'Value': 'zookeeper_stack'}]
    )
    return resp['StackId']


def update_stack(stack_name, template_body, params):
    """ Updates the stack with the updated template. """
    cf = boto3.client('cloudformation')
    resp = cf.update_stack(
        StackName=stack_name,
        TemplateBody=template_body,
        Parameters=params,
        Tags=[{'Key': 'Name', 'Value': 'zookeeper_stack'}]
    )
    return resp['StackId']


def create_or_update_stack(stack_name,
                           keyname,
                           vpcid,
                           subnets,
                           sshsource,
                           internalsource,
                           num_hosts,
                           environment,
                           ami,
                           instance_type,
                           instance_role):
    ''' Creates or updates the stack with required parameters '''

    # Generate the template
    template_body = yaml.safe_dump(
        json.loads(template.to_json()),
        None,
        allow_unicode=True
    )
    print template_body

    # Generate parameters
    params = [
        {'ParameterKey': 'KeyName', 'ParameterValue': keyname},
        {'ParameterKey': 'VpcId', 'ParameterValue': vpcid},
        {'ParameterKey': 'SubnetIdA', 'ParameterValue': subnets[0]},
        {'ParameterKey': 'SubnetIdB', 'ParameterValue': subnets[1]},
        {'ParameterKey': 'SubnetIdC', 'ParameterValue': subnets[2]},
        {'ParameterKey': 'ZkSshSource', 'ParameterValue': sshsource},
        {'ParameterKey': 'ZkInternalSource', 'ParameterValue': internalsource},
        {'ParameterKey': 'NumHosts', 'ParameterValue': num_hosts},
        {'ParameterKey': 'Environment', 'ParameterValue': environment},
        {'ParameterKey': 'AmiId', 'ParameterValue': ami},
        {'ParameterKey': 'InstanceType', 'ParameterValue': instance_type},
        {'ParameterKey': 'InstanceRole', 'ParameterValue': instance_role}
    ]

    # Create or Update the stack
    stack_id = None
    if _stack_exists(stack_name):
        stack_id = update_stack(stack_name, template_body, params)
    else:
        stack_id = create_stack(stack_name, template_body, params)
    print 'StackID=%s' % stack_id


def _parse_args():
    parser = argparse.ArgumentParser(
        prog='python Autoscaling_Zookeeper.py',
        usage='%(prog)s [options]',
        description='Script to generate the Zookeeper Autoscaling Group Stack.'
    )
    parser.add_argument(
        '--stackname',
        type=str,
        nargs=1,
        metavar=("<StackName>"),
        help='EC2 KeyName for SSH access to Zookeeper.'
    )
    parser.add_argument(
        '--keyname',
        type=str,
        nargs=1,
        metavar=("<KeyName>"),
        help='EC2 KeyName for SSH access to Zookeeper.'
    )
    parser.add_argument(
        '--vpcid',
        type=str,
        nargs=1,
        metavar=("<VPCID>"),
        help='Existing VPC Id to use.'
    )
    parser.add_argument(
        '--subnets',
        type=str,
        nargs=3,
        help='Subnets for the Zookeeper ensemble.'
    )
    parser.add_argument(
        '--sshsource',
        type=str,
        nargs=1,
        metavar=("<SSHSource>"),
        help='Incoming source SecurityGroup for SSH access.'
    )
    parser.add_argument(
        '--internalsource',
        type=str,
        nargs=1,
        metavar=("<InternalSource>"),
        help='Incoming source SecurityGroup for internal access.'
    )
    parser.add_argument(
        '--numhosts',
        type=str,
        nargs=1,
        metavar=("<NumHosts>"),
        help='Number of zookeeper servers to run.'
    )
    parser.add_argument(
        '--environment',
        type=str,
        nargs=1,
        metavar=("<Environment>"),
        help='The environment to deploy to.'
    )
    parser.add_argument(
        '--ami',
        type=str,
        nargs=1,
        metavar=("<AMI>"),
        help='AMI id to use for Zookeeper instances.'
    )
    parser.add_argument(
        '--instancetype',
        type=str,
        nargs=1,
        metavar=("<InstanceType>"),
        help='The instance type to use for Zookeeper instances.'
    )
    parser.add_argument(
        '--instancerole',
        type=str,
        nargs=1,
        metavar=("<InstanceRole>"),
        help='The instance role to use for Zookeeper instances.'
    )
    return parser


def main():
    ''' This program would generate the CloudFormation template and stack
    to setup Zookeeper Infrastructure for the Zookeeper ensemble.

    To run setup:
        Autoscaling_Zookeeper --stackname <STACKNAME> \
                              --keyname <KEYNAME> \
                              --vpcid <VPCID> \
                              --subnets <SUBNET-A> <SUBNET-B> <SUBNET-C> \
                              --sshsource <SecurityGroup> \
                              --internalsource <SecurityGroup> \
                              --numhosts <NUMHOSTS> \
                              --environment <ENVIRONMENT> \
                              --ami <AMI> \
                              --instancetype <INSTANCETYPE> \
                              --instancerole <INSTANCEROLE>

    '''
    parser = _parse_args()
    args = vars(parser.parse_args())

    try:
        # Get parameters
        stackname = args['stackname'][0]
        keyname = args['keyname'][0]
        vpcid = args['vpcid'][0]
        subnet_a = args['subnets'][0]
        subnet_b = args['subnets'][1]
        subnet_c = args['subnets'][2]
        sshsource = args['sshsource'][0]
        internalsource = args['internalsource'][0]
        numhosts = args['numhosts'][0]
        environment = args['environment'][0]
        ami = args['ami'][0]
        instancetype = args['instancetype'][0]
        instance_role = args['instancerole'][0]

    except:
        parser.print_help()
        raise

    # Create or update the stack
    create_or_update_stack(
        stackname,
        keyname,
        vpcid,
        [subnet_a, subnet_b, subnet_c],
        sshsource,
        internalsource,
        numhosts,
        environment,
        ami,
        instancetype,
        instance_role
    )


if __name__=='__main__':
   main()
