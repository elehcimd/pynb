# Jupyter Notebooks as Python with embedded Markdown

`pynb` builds on top of [nbconvert](https://github.com/jupyter/nbconvert) and lets you manage Jupyter notebooks as plain Python code with embedded Markdown text, enabling:

* **Python development environment**: Use your preferred IDE/editor, ensure style compliance, navigate, refactor, and test your notebooks as regular Python code.

* **Version control**: Track changes, review pull requests and merge conflicts as with regular Python code. The cell outputs are stored separately and don't interfere with versioning.

* **Consistent execution state**: Never lose track again of the execution state. Notebooks are always executed from clean iPython kernels and the cell execution is cached.

You also get parametrized notebooks with batch and programmatic execution.

## Installation

`pynb` is compatible with `Python >= 3.4` and can be installed with pip:

```
pip install pynb
```

## The `pynb` notebook format

A `pynb` notebook is a Python function that represents a sequence of cells whose type is either Python or Markdown:

```
# Contents of sum.py


def cells(a, b=3):
    '''
    # Sum
    '''

    a = int(a)
    b = int(b)

    '''
    '''

    a + b
```

The example above defines a notebook composed of three cells: *Markdown, Python, Python*.

Function parameters are mapped to notebook arguments and are injected as an additional cell at runtime. Lines whose content is `'''` serve as cell separators. Markdown cells are embedded in multi-line string blocks surrounded by `'''`. Consecutive Python cells are separated by `'''\n'''`. Empty cells are ignored and trailing spaces or empty lines within cells are stripped away.

The Python statement `return` has a special meaning and it instructs the parser to ignore the remaining content of the notebook.

A Python module can contain several functions defining multiple noetbooks. Examples can be found [notebooks](https://github.com/minodes/pynb/tree/master/notebooks) directory.

## Usage

The `pynb` command line tool is tailored for simplicity and is the fastest way to write & run a `pynb` notebook.
To run the `sum.py:cells` notebook reported above:

```
pynb notebooks/sum.py --param a=3 --param b=5
```

You can set a different logging level with the `--log-level` option. The default logging level is INFO.

By default, a Markdown cell is appended if exporting to Jupyter notebook format with details on the execution: location of Python notebook, execution time and complete command line. You can avoid the insertion of the footer cell with the `--disable-footer` option.

The default name of the function defining the notebook is `cells`. A different function name can be specified by appending `:func_name` to the module pathname. E.g., `sum.py:func_name`. `sum.py:cells` is therefore equivalent to `sum.py`. A Python module can contain multiple notebook definitions by using different function names.

### Notebook parameters

Parameters are passed from the command line with `--param` options, whose value is formatted as `name=value`. Names are separated from values at the first occurrence of character `=`. Values are strings and might require casting to their proper type inside the notebook.

Remark that pynb support also default parameter definitions, as it can be seen with `b` in the example. Those default parameters can be overwritten using the standard `--param` notation.


### Importing from Jupyter notebooks 

You can import a Jupyter notebook and export it as Python notebook as follows:

```
pynb --import-ipynb src.ipynb --export-pynb dst.py --no-exec
```

### Exporting to other formats 

The options `--export-html` and `--export-ipynb` let you export to `.html` and `.ipynb` file formats, respectively.
The special output pathname `-` points to standard output.
If you only want to convert the notebook without executing it, you can skip its execution using the `--no-exec` option.

### Execution cache

The caching system allows you to reuse transparently prior cell executions and it's enabled by default.
The option `--disable-cache` disables the cache.
You can force a complete new notebook execution by ignoring the existing cache with option `--ignore-cache`.
To clean the cache, remove manually the files `/tmp/pynb-cache-*`.

How does it work?
An hash is generated for each cell by using the full pathname of the file containing the notebook definition, runtime notebook parameters, cell content and position. After executing a cell for the first time, its output and iPython kernel state are cached. Subsequent executions of the same cell use the cached cell state and speed up significantly the notebook execution.

The iPython session is dumped using the [dill](https://github.com/uqfoundation/dill) package. It is not always possible to serialize objects. E.g., a variable representing an open file cannot be serialized. Other notable cases are database connections and iterators. In such situations, a warning `serialization failed` is reported and the cache is disabled for the current and subsequent cells. Serialization issues do not affect the outputs of the notebook execution.

How to fix serialization failures:

* First, enable the DEBUG logging with `--log-level DEBUG` to print the stack trace of the serialization error (multi-line and coloured). The stack trace will provide hints on which variables are causing the problem.

* Second, fix the code:

  * Move the problematic variables inside a [with statement](https://docs.python.org/3/reference/compound_stmts.html#the-with-statement). In general, the `with` statement ensures a clean & lean iPython kernel state.

  * Delete the problematic variables with the [del](https://docs.python.org/3/reference/simple_stmts.html#del) statement.

  * Reset the iPython session resolving any serialization issue with the iPython's [reset](http://ipython.readthedocs.io/en/stable/interactive/magics.html#magic-reset) built-in magic command:

    ``` 
    get_ipython().magic('reset -f')
    ```
  
## Class interface

The `pynb.Notebook` class interface provides a finer control on parametrization and execution.
To define a notebook, extend the `Notebook` class and use it as in the example below:

```
# Contents of sumapp.py

from pynb.notebook import Notebook


class SumNotebook(Notebook):
    def cells(self, a, b):
        a + b


if __name__ == "__main__":
    nb = SumNotebook()
    nb.add_argument('--a', default=5, type=int)
    nb.add_argument('--b', type=int)
    nb.add_argument('--print-ipynb', action="store_true", default=False)

    nb.run()

    if nb.args.print_ipynb:
        nb.export_ipynb('-')
```

To run it:

```
python3 notebooks/sumapp.py --b 3 --print-ipynb
```

Class `SumNotebook` extends `Notebook` and defines the notebook in method `cells`. Method `Notebook.add_argument` maps to [ArgumentParser.add_argument](https://docs.python.org/2/library/argparse.html#argparse.ArgumentParser.add_argument) and lets you define additional notebook parameters or custom options. Method `Notebook.run` takes care of executing the notebook taking into account the command line arguments. After running the notebook, the attribute `nb.args` contains the object returned by [ArgumentParser.parse_args](https://docs.python.org/2/library/argparse.html#argparse.ArgumentParser.parse_args) and can be used to handle additional user-defined options. E.g., `--print-ipynb`. 

### Command line arguments

If you want to handle user-defined parameters before calling `nb.run()`, you can call `nb.parse_args()` to initialize explicitly `nb.args`. There must be an exact match between the parameter names of the `cells` function and `argparse` attribute names.
All notebook parameter values that have no default value must be provided from the command line. E.g., parameter `b` in the example above.

All command line options available from the `pynb` command line tool are also available with the class interface.

## Credits and license

[Minodes](http://www.minodes.com) supports this and other Open Source projects.

The pynb project is released under the MIT license. Please see [LICENSE.txt](https://github.com/minodes/pynb/blob/master/LICENSE.txt).

## Known issues

On MacOS, ignore these warning messages `RuntimeWarning: Failed to set sticky bit on`. It's a known [bug](https://github.com/jupyter/jupyter_client/pull/201#issuecomment-314269710).

In case of errors, try to update the involved packages:

``` 
pip install pynb --upgrade --no-cache
```


## Development

Tests, builds and releases are managed with `Fabric`.
The build, test and release environment is managed with `Docker`.
Install Docker and Fabric in your system. To install Fabric:

```
pip install Fabric3
```

### Dependencies

For ease of development, the file `requirements.txt` includes the package dependencies.
Any changes to the package dependencies in `setup.py` must be reflected in `requirements.txt`.

### Jupyter server

The Jupyter server is reachable at [http://127.0.0.1:8889/tree](http://127.0.0.1:8889/tree) and
points to the `notebooks` directory.

### Building and publishing a new release

Create a file `secrets.py` in the project directory with the Pypi credentials in this format:

```
pypi_auth = {
    'user': 'youruser',
    'pass': 'yourpass'
}
```

To release a new version:

```
fab release
```


### Running the tests

To run the py.test tests:

```
fab test
```

To run a single test:

```
fab test:tests/test_class.py::test_custom_nbapp
```

To run tests printing output and stopping at first error:

```
fab test_sx
```

To run the pep8 test:

```
fab test_pep8
```

To fix some common pep8 errors in the code:

```
fab fix_pep8
```

To test the pip package after a new release (end-to-end test):
```
fab test_pip
```

### Docker container

To build the Docker image:

```
fab docker_build
```

To force a complete rebuild of the Docker image without using the cache:

```
fab docker_build:--no-cache
```

To start the daemonized Docker container:

```
fab docker_start
```

To stop the Docker container:

```
fab docker_stop
```

To open a shell in the Docker container:

```
fab docker_sh
```

## Contributing

1. Fork it
2. Create your feature branch: `git checkout -b my-new-feature`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin my-new-feature`
5. Create a new Pull Request
