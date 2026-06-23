#Usage: ./build.sh <TAG>
#Usage example: chmod +x ./build.sh && ./build.sh base-1.0
TAG=$1
if [ -z "${TAG}" ];then
    echo "No tag as input, exiting"
	exit 1
fi
sudo docker build -f Dockerfile -t devops-base-image .
sudo docker tag devops-base-image:latest somewhere/devops-images:${TAG}
sudo docker push somewhere/devops-images:${TAG}
sudo docker rmi -f devops-base-image:latest # remove it from the loacl server and keep the tagged image