"""
Utility functions
"""

import logging
import os
import sys


def get_func(func_name, module_pathname):
    """
    Get function from module
    :param func_name: function name
    :param module_pathname:  pathname to module
    :return:
    """

    if sys.version_info[0] >= 3:
        if sys.version_info[1] >= 6:
            import importlib.util
            spec = importlib.util.spec_from_file_location('module_name', module_pathname)
            cells_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cells_module)
            return getattr(cells_module, func_name)
        elif sys.version_info[1] >= 4:
            import importlib.machinery
            module = importlib.machinery.SourceFileLoader('module_name', module_pathname).load_module()
            return getattr(module, func_name)

    fatal('Python version {} not supported'.format(sys.version))


def fatal(msg):
    """
    Print message and exit
    :param msg: message to print
    :return:
    """
    logging.fatal('{}; exiting.'.format(msg))
    print()
    sys.exit(1)


def check_isfile(pathname):
    if not os.path.isfile(pathname):
        fatal("File '{}' does not exist or not regular file".format(pathname))


def print_console(m):
    with open('/dev/stdout', 'w') as f:
        f.write('{}\n'.format(m))
