#!/bin/bash
instance=$1
zone=$2
project_name=$3
gcloud auth activate-service-account --key-file=/opt/gcp/service-account-file-should-be-here.json
gcloud --project "${project_name}" compute instances describe "${instance}" --zone="${zone}" --format='get(networkInterfaces[0].networkIP)'