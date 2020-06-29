import os

import subprocess
from pynb.notebook import Notebook


def local(args):
    cmd = ' '.join(args) if type(args) == list else args
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)


class MyTestNotebook(Notebook):
    def cells(self, N):
        int((N * (N + 1)) / 2)


def main():
    nb = MyTestNotebook()
    nb.add_argument('--N', default=10, type=int)
    nb.run()
    nb.export_ipynb('-')


def test_custom_nbapp():
    cmd = 'python3 {} --N 10000 --disable-cache'
    output = local(cmd.format(os.path.realpath(__file__)))
    assert b'50005000' in output


#############################################################################
if __name__ == "__main__":
    main()
