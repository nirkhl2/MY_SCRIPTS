# The docker image is push to devops-images:base-1.0
FROM ubuntu:20.04 
ARG DEBIAN_FRONTEND=noninteractive #Avoid prompts during apt-get installations
ENV TZ=Etc/UTC

# Update and install base packages
RUN apt update -y
RUN apt install curl -y
RUN apt install unzip -y && apt install -y wget openjdk-17-jdk git jq openssh-client python3-pip vim

WORKDIR /app/

# Install yq from binary
RUN wget https://github.com/mikefarah/yq/releases/download/v4.40.5/yq_linux_amd64 -O /usr/bin/yq && chmod +x /usr/bin/yq

# Install AWSCLI + Kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && chmod +x /app/kubectl
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && unzip awscliv2.zip &&./aws/install

# Install Maven
RUN curl -fsSL https://archive.apache.org/dist/maven/maven-3/3.6.3/binaries/apache-maven-3.6.3-bin.tar.gz | tar xz -C /opt
RUN ln -s /opt/apache-maven-3.6.3 /opt/maven

# Install MySQL and Postgers tools
RUN apt-get update -y && \
    apt-get install -y apt-utils && \
    apt-get install -y lsb-release ca-certificates gnupg && \
    apt-get install -y unzip mysql-client postgresql-client && \
    apt-get install -y tree net-tools telnet bash-completion

RUN apt-get install -y python3 python3-pip && \
    pip3 install boto3

# Add the gcsfuse repository and public key (using focal for Ubuntu 20.04)
#RUN echo "deb http://packages.cloud.google.com/apt gcsfuse-focal main" | tee /etc/apt/sources.list.d/gcsfuse.list && \
#    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
# Add the gcsfuse repository and public key
RUN echo "deb http://packages.cloud.google.com/apt gcsfuse-$(lsb_release -c -s) main" | tee /etc/apt/sources.list.d/gcsfuse.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -

# Add the Google Cloud SDK repository and public key
RUN apt-get install -y gnupg2 && \
    curl -sSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    echo "deb https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list

# Update the package list and install gcsfuse and google-cloud-sdk
RUN apt-get update && apt-get install -y gcsfuse google-cloud-sdk

# Set environment variables for Maven
ENV MAVEN_HOME /opt/maven
ENV PATH $MAVEN_HOME/bin:$PATH

# Keep the container running
CMD ["tail", "-f", "/dev/null"]