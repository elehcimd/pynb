import importlib
import os
import sys
import time
from fabric.api import local
from fabric.decorators import task

import version


def fatal(msg):
    print("Fatal error: {}; exiting.".format(msg))
    sys.exit(1)


def docker_exec(cmdline):
    """
    Execute command in running docker container
    :param cmdline: command to be executed
    """
    local('docker exec -ti pynb {}'.format(cmdline))


@task
def inc_version():
    """
    Increment micro release version (in 'major.minor.micro') in version.py and re-import it.
    Major and minor versions must be incremented manually in version.py.

    :return: list with current version numbers, e.g., [0,1,23].
    """

    new_version = version.__version__

    values = list(map(lambda x: int(x), new_version.split('.')))
    values[2] += 1

    with open('version.py', 'w') as f:
        f.write('__version__ = "{}.{}.{}"\n'.format(values[0], values[1], values[2]))
    with open('pynb/version.py', 'w') as f:
        f.write('__version__ = "{}.{}.{}"\n'.format(values[0], values[1], values[2]))

    importlib.reload(version)

    print('Current version: {}'.format(version.__version__))

    return values


@task
def git_check():
    """
    Check that all changes , besides versioning files, are committed
    :return:
    """

    # check that changes staged for commit are pushed to origin
    output = local('git diff --name-only | egrep -v "^(pynb/version.py)|(version.py)$" | tr "\\n" " "', capture=True).strip()
    if output:
        fatal('Stage for commit and commit all changes first: {}'.format(output))

    output = local('git diff --cached --name-only | egrep -v "^(pynb/version.py)|(version.py)$" | tr "\\n" " "', capture=True).strip()
    if output:
        fatal('Commit all changes first: {}'.format(output))



@task
def git_push():
    """
    Push new version and corresponding tag to origin
    :return:
    """


    # get current version
    new_version = version.__version__
    values = list(map(lambda x: int(x), new_version.split('.')))

    # Push to origin new version and corresponding tag:
    # * commit new version
    # * create tag
    # * push version,tag to origin
    local('git add pynb/version.py version.py')

    local('git commit -m "updated version"')
    local('git tag {}.{}.{}'.format(values[0], values[1], values[2]))
    local('git push origin --tags')


@task
def docker_build(options=''):
    """
    Build docker image
    """
    local('docker build {} -t pynb .'.format(options))


@task
def docker_start(develop=True):
    """
    Start docker container
    """
    curr_dir = os.path.dirname(os.path.realpath(__file__))
    local('docker run --rm --name pynb -d -ti -p 127.0.0.1:8889:8888  -v {}:/code -t pynb'.format(curr_dir))

    if develop:
        # Install package in develop mode: the code in /code is mapped to the installed package.
        docker_exec('python3 setup.py develop')

    print('Jupyter available at http://127.0.0.1:8889')


@task
def docker_stop():
    """
    Stop docker container
    """
    local('docker stop pynb || true')


@task
def docker_sh():
    """
    Execute command in docker container
    """
    docker_exec('/bin/bash')


@task
def test_pip(cleancontainer=True):
    """
    Run all tests in docker container
    :param params: parameters to py.test
    """

    if cleancontainer:
        docker_stop()
        # sometimes, Docker returns too early and then docker_start fails.
        time.sleep(1)
        docker_start(develop=False)
    # WE have now a fresh container as defined in Dockerfile

    docker_exec('pip install pynb')
    test()

    # restart with develop package install
    docker_stop()
    docker_start()

    print("All tests passed!")


@task
def test(params=''):
    """
    Run all tests in docker container
    :param params: parameters to py.test
    """
    docker_exec('py.test {}'.format(params))


@task
def test_sx(params=''):
    """
    Execute all tests in docker container printing output and terminating tests at first failure
    :param params: parameters to py.test
    """
    docker_exec('py.test -sx {}'.format(params))


@task
def test_pep8():
    """
    Execute  only pep8 test in docker container
    """
    docker_exec('py.test tests/test_pep8.py')


@task
def fix_pep8():
    """
    Fix a few common and easy PEP8 mistakes in docker container
    """
    docker_exec('autopep8 --select E251,E303,W293,W291,W391,W292,W391,E302 --aggressive --in-place --recursive .')


@task
def build():
    """
    Build package in docker container
    :return:
    """
    docker_exec('python3 setup.py sdist bdist_wheel')


@task
def release():
    """
    Release new package version to pypi
    :return:
    """

    from secrets import pypi_auth

    # Check that all changes are committed before creating a new version
    git_check()

    # Increment version
    inc_version()

    # Test package
    test()

    # Commit new version, create tag for version and push everything to origin
    git_push()

    # Build and publish package
    build()
    pathname = 'dist/pynb-{}.tar.gz'.format(version.__version__)
    docker_exec('twine upload -u {user} -p {pass} {pathname}'.format(pathname=pathname, **pypi_auth))

    # Remove temporary files
    clean()


@task
def clean():
    """
    Rempove temporary files
    """
    local('rm -rf .cache .eggs build dist')
