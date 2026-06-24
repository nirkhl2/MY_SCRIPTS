#!/bin/bash
# Adds every EKS cluster found across all general-* profiles in ~/.aws/config
# into ~/.kube/config, aliased as "<profile>:<cluster>".
# Requires: aws cli v2, jq. Run AFTER `aws sso login --sso-session general`.

AWS_CONFIG_PATH="$HOME/.aws/config"

__EKS_Clusters_config_update(){
    for account in $(cat ${AWS_CONFIG_PATH} | grep profile | grep -v "bash\|terraform" | awk '{print $2}' | sed 's/.$//'); do
        regions="eu-west-1 eu-central-1 us-west-2 ap-northeast-1";
        for region in ${regions}; do
            for cluster in $(aws eks list-clusters --region=${region} --profile ${account} | jq -r .clusters[]); do
                aws eks update-kubeconfig --name ${cluster} --profile ${account} --region ${region} --alias "${account}:${cluster}"
            done
        done;
    done
}

__EKS_Clusters_config_update
