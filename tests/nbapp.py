from nbpymd.notebook import Notebook


class MyTestNotebook(Notebook):
    def cells(self, N):
        '''
        # Sum

        ---
        '''

        int((N * (N + 1)) / 2)


def main():
    nb = MyTestNotebook()

    nb.add_argument('--N',
                    default=10,
                    type=int,
                    help='N to be considered')

    nb.run(params=['N'])

    nb.export_html('{cls}.html'.format(cls=nb.__class__.__name__))
    nb.export_ipynb('{cls}.ipynb'.format(cls=nb.__class__.__name__))


#############################################################################
if __name__ == "__main__":
    main()
#############################################################################
