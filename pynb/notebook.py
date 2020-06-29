import argparse
import codecs
import datetime
import hashlib
import inspect
import logging
import os
import sys
import time
import traceback
import warnings

import dill
import nbformat as nbf
from jupyter_client.kernelspec import KernelSpecManager
from nbconvert import HTMLExporter
from nbconvert.preprocessors import ExecutePreprocessor
from nbconvert.preprocessors.execute import CellExecutionError

from pynb.utils import get_func, fatal, check_isfile
from pynb.version import __version__

logging.basicConfig(level=logging.INFO)


class CachedExecutePreprocessor(ExecutePreprocessor):
    """
    Extends .run_cell to support cached execution of cells
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.cache_valid = True
        self.prev_fname_session = None
        self.prev_fname_session_loaded = None
        self.disable_cache = False
        self.ignore_cache = False
        self.uid = None

    def cell_hash(self, cell, cell_index):
        """
        Compute cell hash based on cell index and cell content
        :param cell: cell to be hashed
        :param cell_index: cell index
        :return: hash string
        """
        s = '{uid} {cell} {index}'.format(uid=self.uid,
                                          cell=str(cell.source),
                                          index=cell_index).encode('utf-8')

        hash = hashlib.sha1(s).hexdigest()[:8]
        return hash

    def run_cell(self, cell, cell_index=0, store_history=True):
        """
        Run cell with caching
        :param cell: cell to run
        :param cell_index: cell index (optional)
        :param store_history: ignored but required because expected from Jupyter executor (optional)
        :return:
        """

        hash = self.cell_hash(cell, cell_index)
        fname_session = '/tmp/pynb-cache-{}-session.dill'.format(hash)
        fname_value = '/tmp/pynb-cache-{}-value.dill'.format(hash)
        cell_snippet = str(" ".join(cell.source.split())).strip()[:40]

        if self.disable_cache:
            logging.info('Cell {}: Running: "{}.."'.format(hash, cell_snippet))
            return super().run_cell(cell, cell_index)

        if not self.ignore_cache:
            if self.cache_valid and os.path.isfile(fname_session) and os.path.isfile(fname_value):
                logging.info('Cell {}: Loading: "{}.."'.format(hash, cell_snippet))
                self.prev_fname_session = fname_session
                with open(fname_value, 'rb') as f:
                    value = dill.load(f)
                    return value

        # If cache does not exist or not valid:
        #
        # 1) Invalidate subsequent cell caches
        # 2) Load session from previous cached cell (if existing)
        # 3) Run cell
        # 4) Cache cell session
        # 5) Cache cell value

        logging.info('Cell {}: Running: "{}.."'.format(hash, cell_snippet))

        # 1) Invalidate subsequent cell caches
        self.cache_valid = False

        # 2) Load session from previous cached cell (if existing and required)
        if self.prev_fname_session:
            if self.prev_fname_session_loaded != self.prev_fname_session:
                self.session_load(hash, self.prev_fname_session)

        # 2) Run cell
        value = super().run_cell(cell, cell_index)

        # We make sure that injected cells do not interfere with the cell index...
        # value[0]['content']['execution_count'] = cell_index

        # 3) Cache cell session
        cached = self.session_dump(cell, hash, fname_session)

        # 4) Cache cell value, if no errors while dumping the cell session in 3).

        if cached:
            self.prev_fname_session_loaded = fname_session
            self.prev_fname_session = fname_session

            logging.debug('Cell {}: dumping value to {}'.format(hash, fname_value))

            with open(fname_value, 'wb') as f:
                dill.dump(value, f)

            logging.debug('Cell {}: cached'.format(hash))

        return value

    def session_load(self, hash, fname_session):
        """
        Load ipython session from file
        :param hash: cell hash
        :param fname_session: pathname to dumped session
        :return:
        """

        logging.debug('Cell {}: loading session from {}'.format(hash, fname_session))

        # 'dill.settings["recurse"] = True',
        # 'dill.settings["byref"] = True',

        inject_code = ['import dill',
                       'dill.load_session(filename="{}")'.format(fname_session),
                       ]

        inject_cell = nbf.v4.new_code_cell('\n'.join(inject_code))
        super().run_cell(inject_cell)

    def session_dump(self, cell, hash, fname_session):
        """
        Dump ipython session to file
        :param hash: cell hash
        :param fname_session: output filename
        :return:
        """

        logging.debug('Cell {}: Dumping session to {}'.format(hash, fname_session))

        inject_code = ['import dill',
                       'dill.dump_session(filename="{}")'.format(fname_session),
                       ]

        inject_cell = nbf.v4.new_code_cell('\n'.join(inject_code))
        reply, outputs = super().run_cell(inject_cell)

        errors = list(filter(lambda out: out.output_type == 'error', outputs))
        if len(errors):
            logging.info('Cell {}: Warning: serialization failed, cache disabled'.format(hash))
            logging.debug(
                'Cell {}: Serialization error: {}'.format(hash, CellExecutionError.from_cell_and_msg(cell, errors[0])))

            # disable attempts to retrieve cache for subsequent cells
            self.disable_cache = True

            # remove partial cache for current cell
            os.remove(fname_session)

            return False

        return True

        # fname_session has been created in the filesystem of the system running the kernel,
        # which is the same of the system that is managing the execution of the notebook.


class Notebook:
    """
    Manage Jupyter notebook as Python class/application.
    """

    def __init__(self):
        """
        Initialize notebook.
        """

        self.long_name = 'pynb v{} running {} on Python v{}.{}.{}'.format(__version__, self.__class__.__name__,
                                                                          *sys.version_info[:3])

        self.parser = argparse.ArgumentParser(description=self.long_name)
        self.nb = nbf.v4.new_notebook()
        self.nb['cells'] = []
        self.cells_name = None
        self.args = None

    def add(self, func, **kwargs):
        """
        Parse func's function source code as Python and Markdown cells.
        :param func: Python function to parse
        :param kwargs: variables to inject as first Python cell
        :return:
        """

        params = set(kwargs.keys())
        func_params = set(inspect.getargspec(func).args)

        # ignore self, which is present when extending Notebook.
        if 'self' in func_params:
            func_params.remove('self')

        if params != func_params:
            fatal('Params {} not matching cells function params {}'.format(list(params), list(func_params)))

        lines = inspect.getsourcelines(func)[0][1:]

        buffer = ""
        indent_count = None
        inside_markdown = False
        return_found = False

        for line in lines:

            # remove base indentation of function 'func'
            if len(line.strip()) > 0:
                if not indent_count:
                    indent_count = 0
                    for c in line:
                        if c not in [' ', '\t']:
                            break
                        else:
                            indent_count += 1
                line = line[indent_count:]

            if not inside_markdown and line.strip() == "return":
                logging.info('Encountered "return" statement, ignoring the rest of the notebook.')
                break

            if line.strip() == "'''":  # if md block begin/end, or new cell...
                if len(buffer.strip()) > 0:
                    if not inside_markdown:  # if md block begin: new markdown block! flush buffer
                        self.add_cell_code(buffer)
                    else:  # if md block end: markdown block completed! flush buffer
                        self.add_cell_markdown(buffer)
                buffer = ""
                inside_markdown = not inside_markdown
            else:
                buffer += line

        if len(buffer.strip()) > 0:
            if not inside_markdown:
                self.add_cell_code(buffer)
            else:
                self.add_cell_markdown(buffer)

        if len(kwargs) > 0:
            # We have parameters to inject into the notebook.
            # If the first cell is Markdown, assume that is the title and
            # insert parameters as 2nd cell. Otherwise, as 1st cell.
            if len(self.nb['cells']) > 0 and self.nb['cells'][0].cell_type == 'markdown':
                self.add_cell_params(kwargs, 1)
            else:
                self.add_cell_params(kwargs, 0)

    def add_cell_params(self, params, pos=None):
        """
        Add cell of Python parameters
        :param params: parameters to add
        :return:
        """

        self.params = params
        cell_str = '# Parameters:\n'
        for k, v in params.items():
            cell_str += "{} = {}\n".format(k, repr(v))
        self.add_cell_code(cell_str, pos)

    def add_cell_footer(self):
        """
        Add footer cell
        """

        # check if there's already a cell footer... if true, do not add a second cell footer.
        # this situation happens when exporting to ipynb and then importing from ipynb.

        logging.info('Adding footer cell')

        for cell in self.nb['cells']:
            if cell.cell_type == 'markdown':
                if 'pynb_footer_tag' in cell.source:
                    logging.debug('Footer cell already present')
                    return

        m = """

            ---
            * **Notebook class name**: {class_name}
            * **Notebook cells name**: {cells_name}
            * **Execution time**: {exec_begin}
            * **Execution duration**: {exec_time:.2f}s
            * **Command line**: {argv}
            [//]: # (pynb_footer_tag)
            """
        self.add_cell_markdown(
            m.format(exec_time=self.exec_time, exec_begin=self.exec_begin_dt, class_name=self.__class__.__name__,
                     argv=str(sys.argv), cells_name=self.cells_name))

    def add_cell_markdown(self, cell_str):
        """
        Add a markdown cell
        :param cell_str: markdown text
        :return:
        """

        logging.debug("add_cell_markdown: {}".format(cell_str))
        # drop spaces and taps at beginning and end of all lines
        # cell = '\n'.join(map(lambda x: x.strip(), cell_str.split('\n')))
        cell = '\n'.join(cell_str.split('\n'))
        cell = nbf.v4.new_markdown_cell(cell)

        self.nb['cells'].append(cell)

    def add_cell_code(self, cell_str, pos=None):
        """
        Add Python cell
        :param cell_str: cell content
        :return:
        """

        cell_str = cell_str.strip()

        logging.debug("add_cell_code: {}".format(cell_str))
        cell = nbf.v4.new_code_cell(cell_str)

        if pos is None:
            self.nb['cells'].append(cell)
        else:
            self.nb['cells'].insert(pos, cell)

    def process(self, uid, add_footer=False, no_exec=False, disable_cache=False, ignore_cache=False):
        """
        Execute notebook
        :return: self
        """

        self.exec_begin = time.perf_counter()
        self.exec_begin_dt = datetime.datetime.now()

        ep = CachedExecutePreprocessor(timeout=None, kernel_name='python3')
        ep.disable_cache = disable_cache
        ep.ignore_cache = ignore_cache
        ep.uid = uid

        # Execute the notebook

        if not no_exec:
            with warnings.catch_warnings():
                # On MacOS, annoying warning "RuntimeWarning: Failed to set sticky bit on"
                # Let's suppress it.
                warnings.simplefilter("ignore")
                ep.preprocess(self.nb, {'metadata': {'path': '.'}})

        self.exec_time = time.perf_counter() - self.exec_begin

        if add_footer:
            self.add_cell_footer()

        if not no_exec:
            logging.info('Execution time: {0:.2f}s'.format(self.exec_time))

        return self

    def export_ipynb(self, pathname):
        """
        Export notebook to .ipynb file
        :param pathname: output filename
        :return:
        """

        if pathname == '-':
            nbf.write(self.nb, sys.__stdout__)
        else:
            with codecs.open(pathname, 'w', encoding='utf-8') as f:
                ret = nbf.write(self.nb, f)
                pass

        logging.info("Jupyter notebook exported to '{}'".format(pathname))

    def export_html(self, pathname):
        """
        Export notebook to .html file
        :param pathname: output filename
        :return:
        """

        html_exporter = HTMLExporter()

        (body, resources) = html_exporter.from_notebook_node(self.nb)

        if pathname == '-':
            sys.__stdout__.write(body)
        else:
            with open(pathname, 'w') as f:
                f.write(body)

        logging.info("HTML notebook exported to '{}'".format(pathname))

    def export_pynb_str(self):

        s = 'def cells():\n'

        for cell in self.nb['cells']:
            if cell.cell_type == 'markdown':
                s += "    '''\n"
                for line in cell.source.splitlines():
                    s += '    {}\n'.format(line)
                s += "    '''\n"
            elif cell.cell_type == 'code':
                for line in cell.source.splitlines():
                    s += '    {}\n'.format(line)
            else:
                raise Exception('Unknown cell type: {}'.format(cell.cell_type))

            s += "\n    '''\n    '''\n\n"

        return s

    def export_pynb(self, pathname):

        s = self.export_pynb_str()

        if pathname == '-':
            sys.__stdout__.write(s)
        else:
            with open(pathname, 'w') as f:
                f.write(s)

        logging.info("Python notebook exported to '{}'".format(pathname))

    def add_argument(self, *args, **kwargs):
        """
        Add application argument
        :param args: see parser.add_argument
        :param kwargs: see parser.add_argument
        :return:
        """
        self.parser.add_argument(*args, **kwargs)

    def cells(self, *args, **kwargs):
        pass

    def set_cells(self, cells_location):
        """
        Set self.cells to function :cells in file pathname.py
        :param cells_location: cells location, format 'pathname.py:cells'
        :return:
        """

        if ':' in cells_location:
            pathname, func_name = cells_location.split(':')
        else:
            pathname = cells_location
            func_name = 'cells'

        check_isfile(pathname)

        try:
            self.cells = get_func(func_name, pathname)
        except SyntaxError as e:
            fatal(traceback.format_exc(limit=1))

        return pathname, func_name

    def parse_args(self, **kwargs):
        """
        Parse arguments
        :param kwargs: optional params
        :return:
        """

        self.parser.add_argument('cells', help='path to cells function. Format: PATHNAME.PY[:FUNCTION_NAME]', nargs='?')
        self.parser.add_argument('--disable-cache', action="store_true", default=False, help='disable execution cache')
        self.parser.add_argument('--ignore-cache', action="store_true", default=False, help='ignore existing cache')
        self.parser.add_argument('--no-exec', action="store_true", default=False, help='do not execute notebook')
        self.parser.add_argument('--param', action='append', help='notebook parameter. Format: NAME=VALUE')
        self.add_argument('--import-ipynb', help='import from Jupyter notebook')
        self.add_argument('--export-html', help='export to HTML format')
        self.add_argument('--export-ipynb', help='export to Jupyter notebook')
        self.add_argument('--export-pynb', help='export to Python notebook')
        self.add_argument('--kernel', default=None, help='set kernel')
        self.add_argument('--log-level', help='set log level')
        self.add_argument('--check-syntax', action="store_true", default=False, help='check Python syntax')
        self.add_argument('--disable-footer', action="store_true", default=False,
                          help='do not append Markdown footer to Jupyter notebook')

        if len(sys.argv) == 1 and self.__class__ == Notebook:
            # no parameters and Notebook class not extended:
            # print help and exit.
            self.parser.print_help()
            print()
            sys.exit(1)

        self.args = self.parser.parse_args()

    def load_cells_params(self):

        if self.args.cells:
            # module and function name passed with args.cells parameter
            pathname, func_name = self.set_cells(self.args.cells)
            logging.info('Loading cells from {}'.format(self.args.cells))
            uid = '{}:{}'.format(os.path.abspath(pathname), func_name)
            self.cells_name = self.args.cells
        else:
            # Notebook class extended, .cells method contains the target cell
            # Let's make sure that this is the case...
            if self.__class__ == Notebook:
                fatal('Notebook class not extended and cells parameter is missing')
            logging.info('Loading notebook {}'.format(self.__class__.__name__))
            uid = '{}:{}'.format(os.path.abspath(inspect.getfile(self.__class__)), self.__class__.__name__)

        # Process parameters passed by custom arguments
        arg_spec = inspect.getargspec(self.cells)
        func_params = arg_spec.args
        # Get default parameters
        default_params = arg_spec.defaults

        self.kwargs = {}

        if default_params:
            default_args_with_value = dict(zip(func_params[-len(default_params):], default_params))
            logging.debug('Found default values {}'.format(default_args_with_value))
            # Add default values to kwargs
            self.kwargs.update(default_args_with_value)

        if not self.args.cells:
            # self is always present in case of subclassed Notebook, since cells(self, ...) is a method.
            func_params.remove('self')
            for param in func_params:
                self.kwargs[param] = getattr(self.args, param, None)

        # Process parameters passed with --param
        if self.args.param:
            for param in self.args.param:
                k, v = param.split('=', 1)
                self.kwargs[k] = v

        # Check parameters completeness
        for param in func_params:
            if self.kwargs[param] is None:
                fatal('Notebook parameter {} required but not found'.format(param))

        logging.info('Parameters: {}'.format(self.kwargs))

        self.add(self.cells, **self.kwargs)

        return uid

    def get_kernelspec(self, name):
        """Get a kernel specification dictionary given a kernel name
        """
        ksm = KernelSpecManager()
        kernelspec = ksm.get_kernel_spec(name).to_dict()
        kernelspec['name'] = name
        kernelspec.pop('argv')
        return kernelspec

    def set_kernel(self, name):

        kernelspec = self.get_kernelspec(name)

        metadata = {'language': 'python',
                    'kernelspec': kernelspec}

        self.nb.update(metadata=metadata)

    def run(self):
        """
        Run notebook as an application
        :param params: parameters to inject in the notebook
        :return:
        """

        if not self.args:
            self.parse_args()

        if self.args.log_level:
            logging.getLogger().setLevel(logging.getLevelName(self.args.log_level))
            logging.debug('Enabled {} logging level'.format(self.args.log_level))

        if self.args.import_ipynb:
            check_isfile(self.args.import_ipynb)
            logging.info('Loading Jupyter notebook {}'.format(self.args.import_ipynb))
            self.nb = nbf.read(self.args.import_ipynb, as_version=4)
            uid = self.args.import_ipynb
        else:
            uid = self.load_cells_params()

        logging.debug("Unique id: '{}'".format(uid))
        logging.info('Disable cache: {}'.format(self.args.disable_cache))
        logging.info('Ignore cache: {}'.format(self.args.ignore_cache))

        if self.args.export_pynb and not self.args.no_exec:
            fatal('--export-pynb requires --no-exec')

        if self.args.kernel:
            self.set_kernel(self.args.kernel)

        self.process(uid=uid,
                     add_footer=not self.args.disable_footer,
                     no_exec=self.args.no_exec,
                     disable_cache=self.args.disable_cache,
                     ignore_cache=self.args.ignore_cache)

        if self.args.export_html:
            self.export_html(self.args.export_html)

        if self.args.export_ipynb:
            self.export_ipynb(self.args.export_ipynb)

        if self.args.export_pynb:
            self.export_pynb(self.args.export_pynb)


def main():
    """
    Entry point for pynb command
    :return:
    """

    nb = Notebook()
    nb.run()


if __name__ == "__main__":
    main()
