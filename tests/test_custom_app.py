import os

from fabric.api import local

from pynb.notebook import Notebook


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
    output = local(cmd.format(os.path.realpath(__file__)), capture=True)
    assert '50005000' in output


#############################################################################
if __name__ == "__main__":
    main()
