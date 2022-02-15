import boto3
ec2 = boto3.resource('ec2')

new_instance = ec2.create_instances(
				ImageId='ami-033b95fb8079dc481',
				MinCount=1,
				MaxCount=1,
				InstanceType='t2.nano',
				KeyName='ubuntu_ag',
				SecurityGroups=[
						'launch-wizard-1'],
				TagSpecifications=[{
						'ResourceType': 'instance',
						'Tags': [{
							'Key': 'Name',
							'Value': 'Demo Python Generated Instance'}]}],
				UserData="""
					#!/bin/bash
					yum update -y
					yum install httpd -y
					systemctl enable httpd
					systemctl start httpd
					""")

print(new_instance[0].id)
