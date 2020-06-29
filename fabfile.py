import importlib
import os
import sys

from fabric import task

import version

# this must be before importing from secrets.
sys.path = ["."] + sys.path

from secrets import pypi_auth


# Initialise project directory and name
project_dir = os.path.abspath(os.path.dirname(__file__))
project_name = os.path.basename(project_dir)

# Change directory to directory containing this script
os.chdir(project_dir)


def local(ctx, *args, **kwargs):
    s = "Executing: {} {}".format(args, kwargs)
    if len(s) > 70:
        s = s[:70] + f".. ({len(s[70:])})"
    print(s)

    with ctx.prefix("PATH={}".format(os.environ["PATH"])):
        return ctx.run(*args, **kwargs)


@task
def test_pep8(ctx):
    """
    Run only pep8 test
    :return:
    """

    local(ctx, 'py.test tests/test_pep8.py')


@task
def test(ctx):
    """
    Run all tests
    :param params: parameters to py.test
    :return:
    """

    local(ctx, f'py.test tests')


@task
def test_sx(ctx):
    """
    Run all tests
    :param params: parameters to py.test
    :return:
    """

    local(ctx, f'py.test -sx tests')


@task
def test_single(ctx, f):
    """
    Run all tests
    :param params: parameters to py.test
    :return:
    """

    local(ctx, f'py.test -sx {f}')


@task
def fix_pep8(ctx):
    """
    Fix a few common and easy-to-fix PEP8 mistakes
    :return:
    """

    local(ctx,
          'autopep8 --select E265,E225,E302,E222,E251,E303,W293,W291,W391 --aggressive --in-place --recursive .')


def inc_version():
    """
    Increment micro release version (in 'major.minor.micro') in version.py and re-import it.
    Major and minor versions must be incremented manually in version.py.

    :return: list with current version numbers, e.g., [0,1,23].
    """

    new_version = version.__version__

    values = list(map(lambda x: int(x), new_version.split('.')))
    values[2] += 1

    with open("version.py", "w") as f:
        f.write(f'__version__ = "{values[0]}.{values[1]}.{values[2]}"\n')
        f.write(f'__pkgname__ = "{project_name}"\n')
    with open(f"{project_name}/version.py", "w") as f:
        f.write(f'__version__ = "{values[0]}.{values[1]}.{values[2]}"\n')
        f.write(f'__pkgname__ = "{project_name}"\n')

    importlib.reload(version)

    print(f'Package {version.__pkgname__} current version: {version.__version__}')

    return values


@task
def git_check(ctx):
    """
    Check that all changes , besides versioning files, are committed
    :return:
    """

    # check that changes staged for commit are pushed to origin
    output = local(ctx, f'git diff --name-only | egrep -v "^({project_name}/version.py)|(version.py)$" | tr "\\n" " "',
                   hide=True).stdout.strip()

    if output:
        fatal('Stage for commit and commit all changes first: {}'.format(output))

    output = local(ctx,
                   f'git diff --cached --name-only | egrep -v "^({project_name}/version.py)|(version.py)$" | tr "\\n" " "',
                   hide=True).stdout.strip()
    if output:
        fatal('Commit all changes first: {}'.format(output))


def fatal(msg):
    print("Fatal error: {}; exiting.".format(msg))
    sys.exit(1)


def git_push(ctx):
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
    local(ctx, f'git add {project_name}/version.py version.py')

    local(ctx, 'git commit -m "updated version"')
    local(ctx, f'git tag {values[0]}.{values[1]}.{values[2]}')
    local(ctx, 'git push origin --tags')
    local(ctx, 'git push')


@task
def release(ctx):
    """
    Release new package version to pypi
    :return:
    """

    # Check that all changes are committed before creating a new version
    git_check(ctx)

    # Test package
    test(ctx)

    # Increment version
    inc_version()

    # Commit new version, create tag for version and push everything to origin
    git_push(ctx)

    # Build and publish package
    pkgbuild(ctx)
    pathname = f'dist/{project_name}-{version.__version__}.tar.gz'

    local(ctx, f'twine upload -u {pypi_auth["user"]} -p {pypi_auth["pass"]} {pathname}')

    # Remove temporary files
    clean(ctx)


@task
def pkgbuild(ctx):
    """
    Build package in docker container
    :return:
    """
    local(ctx, 'python setup.py sdist bdist_wheel')


@task
def clean(ctx):
    """
    Rempove temporary files
    """
    local(ctx, 'rm -rf .cache .eggs build dist')
