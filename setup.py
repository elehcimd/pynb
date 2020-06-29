from setuptools import setup
from version import __version__

# Get the long description from the README file
with open('README.rst', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='pynb',
    version=__version__,
    author='Michele Dallachiesa',
    author_email='michele.dallachiesa@sigforge.com',
    packages=['pynb'],
    scripts=[],
    url='https://github.com/elehcimd/pynb',
    license='MIT',
    description='Manage Jupyter notebooks as Python code with embedded Markdown text.',
    long_description=long_description,
    python_requires=">=3.4",
    install_requires=[
        "jupyter",
        "nbconvert",
        "nbformat",
        "dill",
        "ipykernel",
        "ipython"
    ],
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 4 - Beta',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Intended Audience :: System Administrators',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: MIT License',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 3',
    ],
    entry_points={
        'console_scripts': [
            'pynb = pynb.notebook:main',
        ]
    },
)
