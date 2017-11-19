# Contents of sumapp.py

from nbpymd.notebook import Notebook


class SumNotebook(Notebook):
    def cells(self, a, b):
        a + b


if __name__ == "__main__":
    nb = SumNotebook()
    nb.add_argument('--a', default=5, type=int)
    nb.add_argument('--b', type=int)
    nb.add_argument('--print-ipynb', action="store_true", default=False)

    args = nb.run()

    if args.print_ipynb:
        nb.export_ipynb('-')
