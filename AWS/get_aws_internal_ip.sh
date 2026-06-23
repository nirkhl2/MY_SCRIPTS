#!/bin/bash
instance=$1
awsRegion=$2
awsAccessKeyId=$3
awsAccessSecretKeyId=$4

export AWS_ACCESS_KEY_ID=$awsAccessKeyId
export AWS_SECRET_ACCESS_KEY=$awsAccessSecretKeyId
export AWS_DEFAULT_REGION=$awsRegion
aws ec2 describe-instances --filters Name=instance-id,Values="${instance}" | jq ".Reservations[0].Instances[0].NetworkInterfaces[0].PrivateIpAddress" | sed 's/"//g'
