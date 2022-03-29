#!/bin/python3

import os
import subprocess
import sys
import argparse
from time import sleep
from datetime import datetime
import requests
import webbrowser
import json
import boto3

# Ref: Optional Named Arguments
# https://stackoverflow.com/questions/40001892/reading-named-command-arguments
# https://docs.python.org/2/howto/argparse.html#introducing-optional-arguments

# Setting up optional arguments with fallbacks
parser = argparse.ArgumentParser()
parser.add_argument('--key', help='Keypair name',
                    required=False, default='ubuntu_ag')
parser.add_argument('--tag', help='Tag name', required=False,
                    default='Demo Instance From Script')
parser.add_argument('--sec', help='Security group name',
                    required=False, default='launch-wizard-1')


IMAGEID = 'ami-033b95fb8079dc481'
MINCOUNT = 1
MAXCOUNT = 1
INSTANCE_TYPE = 't2.nano'
TAG_NAME = parser.parse_args().tag
KEYNAME = parser.parse_args().key
SECURITY_GROUP = parser.parse_args().sec

# Tag to be used for tagging instances
TAG_SPECS = [
    {
        'ResourceType': 'instance',
        'Tags': [
            {
                'Key': 'Name',
                'Value': TAG_NAME
            }
        ]
    }
]

# User data to be passed to the instance for execution on initialization
USERDATA = """
	#!/bin/bash
    yum update -y
	yum install httpd -y
	systemctl enable httpd
	systemctl start httpd
    echo "<html><h1>Hello World</h1></html>" > index.html
    echo "This instance is running in availability zone:" >> index.html
    curl http://169.254.169.254/latest/meta-data/placement/availability-zone >> index.html
    echo "<hr>The instance ID is: " >> index.html
    curl http://169.254.169.254/latest/meta-data/instance-id >> index.html
    echo "<hr>The instance type is: " >> index.html
    curl http://169.254.169.254/latest/meta-data/instance-type >> index.html
    sudo mv index.html /var/www/html/index.html
	"""

print('-' * 80)
print('Usage: python3 Assignment1.py --key=<KEYPAIR NAME> --tag=<TAG> --sec=<SECURITY GROUP>')
if(len(sys.argv) < 3):
    print('Some arguments unset, applying default values...')
print('-' * 80)
print('\nCreating EC2 instance with the following specifications:')
print('-' * 80)
print('Image ID: {}'.format(IMAGEID))
print('Instance Type: {}'.format(INSTANCE_TYPE))
print('Key Name: {}'.format(KEYNAME))
print('Security Group: {}'.format(SECURITY_GROUP))
print('Tag: {}'.format(TAG_NAME))
print('-' * 80)


# -------------------------------------------------- #
# ---- Create EC2 Instance with the above specs ---- #
# -------------------------------------------------- #

# Setting up the client/resource
try:
    ec2client = boto3.client('ec2')
    ec2resource = boto3.resource('ec2')
except Exception as e:
    print("Failed to initialize boto3 client and resource: ", e)
    sys.exit(1)

# Check if the keypair exists in AWS and locally, if not create it
try:
    keypairs = ec2client.describe_key_pairs()
    keypairs_list = keypairs['KeyPairs']
    keypair_exists = False
    for keypair in keypairs_list:
        if(keypair['KeyName'] == KEYNAME):
            keypair_exists = True
            break
    if(not keypair_exists):
        print('Keypair {} does not exist, creating...'.format(KEYNAME))
        keypair = ec2client.create_key_pair(KeyName=KEYNAME)
        keypair_file = open(KEYNAME + '.pem', 'w')
        keypair_file.write(keypair['KeyMaterial'])
        keypair_file.close()
        os.chmod(KEYNAME + '.pem', 0o400)
        print('Keypair {} created successfully'.format(KEYNAME))
    else:
        print('Keypair {} already exists'.format(KEYNAME))
except Exception as e:
    print("Failed to create keypair: ", e)


# Check if security group exists, and create if not

security_groups = ec2client.describe_security_groups()

# Use the provided (or default) security group name to check if it exists
if SECURITY_GROUP not in [sg['GroupName'] for sg in security_groups['SecurityGroups']]:
    try:

        print('Security group not found, creating new security group')
        response = ec2client.create_security_group(
            GroupName=SECURITY_GROUP,
            Description='Security group for EC2 instance: %s' % TAG_NAME)

        security_group_id = response['GroupId']
        ec2client.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 80,
                    'ToPort': 80,
                    'IpRanges': [
                        {
                            'CidrIp': '0.0.0.0/0'
                        }
                    ]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [
                        {
                            'CidrIp': '0.0.0.0/0'
                        }
                    ]
                }
            ]
        )

        print('Security Group %s added and configured successfully' %
              security_group_id)

    except Exception as e:
        print('Failed to create new Security Group, please review manually after script is complete: %s' % e)


# Create the instance with the above specs and await completion to get access to complete instance details

try:

    print('\nCreating new EC2 instance...\n')

    instances = ec2resource.create_instances(
        ImageId=IMAGEID,
        MinCount=MINCOUNT,
        MaxCount=MAXCOUNT,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEYNAME,
        SecurityGroups=[SECURITY_GROUP],
        TagSpecifications=TAG_SPECS,
        UserData=USERDATA
    )

    # create_instances returns a list of instances, grab the first one and assign it to the instance variable
    instance = instances[0]

    # Ref: https://stackoverflow.com/questions/34728477/retrieving-public-dns-of-ec2-instance-with-boto3
    # Need to wait for instance to be running to get the public dns

    print('Waiting for status to be updated to RUNNING...')

    instance.wait_until_running()
    instance.load()

    ec2_site = 'http://%s' % instance.public_dns_name

    print('New instance created successfully: %s' % instance.id)
    print('Site is accessible at %s' % ec2_site)

except Exception as e:
    print('Failed to create new instance, please review manually after script is complete: %s' % e)
    sys.exit(1)


# ----------------------------------------------- #
# ---- Create website hosted in an S3 bucket ---- #
# ----------------------------------------------- #

print('\nCreating S3 bucket for static website...\n')

s3 = boto3.client('s3')

WIT_IMAGE_FILE = 'assign1.jpg'
BUCKET_NAME = 'static-website-ag-%s' % datetime.now().strftime('%Y-%m-%d-%H-%M-%S')

try:
    s3.create_bucket(Bucket=BUCKET_NAME)
except Exception as e:
    print('Failed to create bucket, please review manually after script is complete: %s' % e)
    sys.exit(1)

# Public policy for the bucket to allow access from the internet
public_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            'Resource': f'arn:aws:s3:::{BUCKET_NAME}/*'
        },
    ],
}

# Jsonified policy
json_policy = json.dumps(public_policy)

s3.put_bucket_policy(Bucket=BUCKET_NAME, Policy=json_policy)

website_payload = {
    'IndexDocument': {
        'Suffix': 'index.html'
    }
}

bucket_website = s3.put_bucket_website(
    Bucket=BUCKET_NAME, WebsiteConfiguration=website_payload)

# Create index.html content with image linked

S3_CONTENT = """
<html>
<body>
<h1>Hello World - Static S3 Website</h1>
<p>This is a static website hosted in an S3 bucket</p>
<img src="%s" alt="Assignment 1 Image" />
</body>
</html>
""" % WIT_IMAGE_FILE

# Create the index.html file in the bucket
try:
    s3.put_object(Body=S3_CONTENT, Bucket=BUCKET_NAME,
                  ContentType='text/html', Key='index.html')
except Exception as e:
    print('Failed to create index.html in S3 bucket: %s' % e)


# Get image from WIT server and upload to S3

img = requests.get('http://devops.witdemo.net/%s' % WIT_IMAGE_FILE)
with open(WIT_IMAGE_FILE, 'wb') as f:
    print('Downloading %s from WIT server...' % WIT_IMAGE_FILE)
    f.write(img.content)

if img:
    s3.upload_file(WIT_IMAGE_FILE, BUCKET_NAME, WIT_IMAGE_FILE)
    print('Image uploaded to S3 bucket successfully')
else:
    print('Failed to upload image to S3 bucket')

s3_site = 'http://%s.s3-website-us-east-1.amazonaws.com' % BUCKET_NAME

print('Complete, site is hosted at %s' % s3_site)


# ------------------------------------------ #
# ---- Launch both sites in the browser ---- #
# ------------------------------------------ #

print('\nLaunching browser to view both sites...\n')

sleep(2)
webbrowser.open(ec2_site)
webbrowser.open(s3_site)
sleep(2)


# Upload monitoring script to EC2 instance with scp command

MONITORING_SCRIPT = 'monitor.sh'

# Ref: https://askubuntu.com/questions/123072/ssh-automatically-accept-keys
# Automatically accept the SSH key

print('\nUploading monitoring script to EC2 instance...\n')

try:
    scp_command = 'scp -o StrictHostKeyChecking=accept-new -i %s.pem %s ec2-user@%s:~/' % (
        KEYNAME, MONITORING_SCRIPT, instance.public_ip_address)

    os.system(scp_command)

    print('\nUploaded monitoring script successfully')
except Exception as e:
    print('Failed to upload monitoring script: %s' % e)

try:
    print('\nLaunching monitoring script in EC2 instance...\n')

    # SSH to EC2 instance, chmod script, and run script
    ssh_command = 'ssh -o StrictHostKeyChecking=accept-new -i %s.pem ec2-user@%s  "chmod +x %s && ./%s"' % (
        KEYNAME, instance.public_ip_address, MONITORING_SCRIPT, MONITORING_SCRIPT)

    os.system(ssh_command)

except Exception as e:
    print('\nFailed to launch monitoring script: %s' % e)


# --------------------------------- #
# ---- Create CloudWatch Alarm ---- #
# --------------------------------- #

print('\nCreating CloudWatch Alarm...\n')

try:
    cloudwatch = boto3.client('cloudwatch')

    cloudwatch.put_metric_alarm(
        AlarmName='MonitoringAlarm',
        AlarmDescription='Alarm when CPU exceeds 90%',
        ActionsEnabled=True,
        AlarmActions=['arn:aws:automate:us-east-1:ec2:reboot'],
        MetricName='CPUUtilization',
        Namespace='AWS/EC2',
        Statistic='Average',
        Dimensions=[
            {
                'Name': 'InstanceId',
                'Value': instance.id
            }
        ],
        Period=300,
        EvaluationPeriods=1,
        Threshold=90,
        ComparisonOperator='GreaterThanOrEqualToThreshold'
    )

    print('CloudWatch Alarm created successfully')
except Exception as e:
    print('Failed to create CloudWatch Alarm: %s' % e)


# ------------------------------------------ #
# ---- Install and configure a database ---- #
# ------------------------------------------ #

# print('\nCreating RDS instance...\n')

# try:
#     rds = boto3.client('rds')

#     response = rds.create_db_instance(
#         DBInstanceIdentifier='ag-db',
#         DBInstanceClass='db.t2.micro',
#         Engine='mysql',
#         MasterUsername='root',
#         MasterUserPassword='password',  # Hard coded for demonstration purposes
#         DBName='ag_db',
#         MultiAZ=False,
#         AllocatedStorage=5,
#         BackupRetentionPeriod=0,
#         StorageType='gp2',
#         PubliclyAccessible=True,
#     )

#     print('RDS instance created successfully')
# except Exception as e:
#     print('Failed to create RDS instance: %s' % e)


# ------------------------------------------ #
