import argparse
import datetime
import hashlib
import inspect
import logging
import os
import sys
import time
import warnings

import dill
import nbformat as nbf
from nbconvert import HTMLExporter
from nbconvert.preprocessors import ExecutePreprocessor

from nbpymd.utils import get_func, fatal
from nbpymd.version import __version__

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
        self.kwargs = {}
        self.nb_name = None

    def cell_hash(self, cell, cell_index):
        """
        Compute cell hash based on cell index and cell content
        :param cell: cell to be hashed
        :param cell_index: cell index
        :return: hash string
        """
        s = '{cls} {kwargs} {cell} {index}'.format(cls=self.nb_name,
                                                   kwargs=self.kwargs,
                                                   cell=str(cell.source),
                                                   index=cell_index).encode('utf-8')
        hash = hashlib.sha1(s).hexdigest()[:8]
        return hash

    def run_cell(self, cell, cell_index=0):
        """
        Run cell with caching
        :param cell: cell to run
        :param cell_index: cell index (optional)
        :return:
        """

        hash = self.cell_hash(cell, cell_index)
        fname_session = '/tmp/nbpymd-cache-{}-session.dill'.format(hash)
        fname_value = '/tmp/nbpymd-cache-{}-value.dill'.format(hash)
        cell_snippet = str(" ".join(cell.source.split())).strip()[:40]

        if self.disable_cache:
            logging.info('Cell {}: Running: "{}"'.format(hash, cell_snippet))
            return super().run_cell(cell, cell_index)

        if not self.ignore_cache:
            if self.cache_valid and os.path.isfile(fname_session) and os.path.isfile(fname_value):
                logging.info('Cell {}: Loading: "{}"'.format(hash, cell_snippet))
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

        logging.info('Cell {}: Running: "{}"'.format(hash, cell_snippet))

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
        cached = self.session_dump(hash, fname_session)

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

    def session_dump(self, hash, fname_session):
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

        errors = len(list(filter(lambda out: out.output_type == 'error', outputs)))
        if errors:
            logging.info('Cell {}: Warning: serialization failed, cache disabled'.format(hash))

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

        self.parser = argparse.ArgumentParser(
            description='nbapp v{} running on Python v{}.{}.{}'.format(__version__, *sys.version_info[:3]))
        self.nb = nbf.v4.new_notebook()
        self.nb['cells'] = []
        self.first_markdown = True

    def add(self, func, **kwargs):
        """
        Parse func's function source code as Python and Markdown cells.
        :param func: Python function to parse
        :param kwargs: variables to inject as first Python cell
        :return:
        """

        if len(kwargs) > 0:
            self.add_cell_params(kwargs)

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

            if line.strip() == "'''":  # if md block begin or end..
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

    def add_cell_params(self, params):
        """
        Add cell of Python parameters
        :param params: parameters to add
        :return:
        """

        self.params = params
        cell_str = '# Parameters:\n'
        for k, v in params.items():
            cell_str += "{} = {}\n".format(k, repr(v))
        self.add_cell_code(cell_str)

    def add_cell_footer(self):
        """
        Add footer cell
        """

        m = """

            ---
            * **Notebook class name**: {class_name}
            * **Execution time**: {exec_begin}
            * **Execution duration**: {exec_time:.2f}s
            * **Arguments vector**: {argv}
            """
        self.add_cell_markdown(
            m.format(exec_time=self.exec_time, exec_begin=self.exec_begin_dt, class_name=self.__class__.__name__,
                     argv=str(sys.argv)))

    def add_cell_markdown(self, cell_str):
        """
        Add a markdown cell
        :param cell_str: markdown text
        :return:
        """

        logging.debug("add_cell_markdown: {}".format(cell_str))
        # drop spaces and taps at beginning and end of all lines
        cell = '\n'.join(map(lambda x: x.strip(), cell_str.split('\n')))
        cell = nbf.v4.new_markdown_cell(cell)

        if self.first_markdown:
            self.nb['cells'].insert(0, cell)
            self.first_markdown = False
        else:
            self.nb['cells'].append(cell)

    def add_cell_code(self, cell_str):
        """
        Add Python cell
        :param cell_str: cell content
        :return:
        """
        logging.debug("add_cell_code: {}".format(cell_str))
        cell = nbf.v4.new_code_cell(cell_str)
        self.nb['cells'].append(cell)

    def execute(self, kwargs={}, disable_cache=False, ignore_cache=False):
        """
        Execute notebook
        :return: self
        """

        self.exec_begin = time.perf_counter()
        self.exec_begin_dt = datetime.datetime.now()

        self.add(self.cells, **kwargs)

        ep = CachedExecutePreprocessor(timeout=None, kernel_name='python3')
        ep.disable_cache = disable_cache
        ep.ignore_cache = ignore_cache
        ep.kwargs = kwargs
        ep.nb_name = self.__class__.__name__

        # Execute the notebook

        with warnings.catch_warnings():
            # On MacOS, annoying warning "RuntimeWarning: Failed to set sticky bit on"
            # Let's suppress it.
            warnings.simplefilter("ignore")
            ep.preprocess(self.nb, {'metadata': {'path': '.'}})

        self.exec_time = time.perf_counter() - self.exec_begin

        self.add_cell_footer()

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
            with open(pathname, 'w') as f:
                nbf.write(self.nb, f)

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

    def add_argument(self, *args, **kwargs):
        """
        Add application argument
        :param args: see parser.add_argument
        :param kwargs: see parser.add_argument
        :return:
        """
        self.parser.add_argument(*args, **kwargs)

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

        try:
            self.cells = get_func(func_name, pathname)
        except:
            fatal("Function '{}' not found in '{}' or synthax issues".format(func_name, pathname))

    def run(self, params=[]):
        """
        Run notebook as an application
        :param params: parameters to inject in the notebook
        :return:
        """

        self.parser.add_argument('cells', help='Cells. Format: pathname.py[:cells_func]', nargs="?", default=None)

        self.parser.add_argument('--disable-cache', action="store_true", default=False,
                                 help='Disable execution cache')

        self.parser.add_argument('--ignore-cache', action="store_true", default=False,
                                 help='Ignore existing cache')

        self.parser.add_argument('--debug', action="store_true", default=False,
                                 help='Enable debug logging')

        self.parser.add_argument('--param', action='append', help='Cells param. Format: name=value')

        self.add_argument('--export-html', help='Pathname to export to HTML format')
        self.add_argument('--export-ipynb', help='Pathname to export to Jupyter notebook format')

        args = self.parser.parse_args()

        if len(sys.argv) == 1:
            self.parser.print_help()
            print()
            sys.exit(0)

        if args.debug:
            logging.basicConfig(level=logging.DEBUG)

        # Process parameters
        kwargs = {}
        for param in params:
            kwargs[param] = getattr(args, param)

        # Process parameters passed with --param
        if args.param:
            for param in args.param:
                k, v = param.split('=', 1)
                kwargs[k] = v

        self.kwargs = kwargs

        logging.info('nbpymd:nbapp v{} running on Python v{}.{}.{}'.format(__version__, *sys.version_info[:3]))

        if args.cells:
            # module and function name passed with args.cells parameter
            self.set_cells(args.cells)
            logging.info('Running cells from {}'.format(args.cells))
        else:
            # Notebook class extended, .cells method contains the target cell
            # Let's make sure that this is the case...
            if self.__class__ == Notebook:
                fatal('Notebook not extended and cells parameter is missing')
            logging.info('Running notebook {}'.format(self.__class__.__name__))

        logging.info('Disable cache: {}'.format(args.disable_cache))
        logging.info('Ignore cache: {}'.format(args.ignore_cache))
        logging.info('Parameters: {}'.format(kwargs))

        self.execute(kwargs=kwargs, disable_cache=args.disable_cache, ignore_cache=args.ignore_cache)

        if args.export_html:
            self.export_html(args.export_html)

        if args.export_ipynb:
            self.export_ipynb(args.export_ipynb)

        return args


def main():
    """
    Entry point for nbapp command
    :return:
    """

    nb = Notebook()
    nb.run()


if __name__ == "__main__":
    main()
