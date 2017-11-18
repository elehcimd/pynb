# Environment for running, testing and releasing nbpymd.

# Start from Alpine + Python 3.6
FROM frolvlad/alpine-python3

# Update package index
RUN apk add --update

# Install build environment and libraries required to install pip packages
RUN apk add bash bash-completion g++ gcc python3-dev musl-dev libffi-dev openssl-dev make

# Upgrade pip and install packages required for testing and packaging
RUN pip install --upgrade pip
ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Install nbpymd
#RUN pip install nbpymd --no-cache-dir --upgrade

# Set default working directory and run bash
WORKDIR /code
CMD ["/bin/bash"]