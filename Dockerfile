# Environment for running, testing and releasing pynb.

# Start from Alpine + Python 3.6
FROM frolvlad/alpine-python3

# Update package index
RUN apk add --update

# Install build environment and libraries required to install pip packages
RUN apk add bash bash-completion g++ gcc python3-dev musl-dev libffi-dev openssl-dev make vim

# Upgrade pip and install packages required for testing and packaging
RUN pip install --upgrade pip

# required, otherwise installation of requirements.txt fails
RUN pip install cffi

ADD requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# Set default working directory
WORKDIR /code

# Run Jupiter
CMD ["jupyter", "notebook", "--allow-root", "--ip=0.0.0.0", "--NotebookApp.token=", "./notebooks"]
