import ast
import json
import re

import pytest

from nbpymd.notebook import Notebook


class NotebookTest(Notebook):
    def cells(self):
        """
        This text is NOT rendered as Markdown.
        """

        '''
        # This is markdown.
        '''

        thisisunique = 100
        x = 10
        y = 3
        y

        '''
        # Title
        # Subtitle

        This text is rendered as Markdown

        * First
        * Second
        '''

        x + y

        # this-is-13

        # x+y is evaluated and printed

        # The following 'breaks' the code into two consecutive code cells.

        '''
        '''

        # this-returns-20
        z = x + x
        z

        # z is evaluated and printed


# Required to suppress erronous warning "jupyter_client/connect.py:157:
# RuntimeWarning: Failed to set sticky bit on '/var/folders [....]"

@pytest.mark.filterwarnings('ignore:Failed to set sticky bit')
def test_execute():
    # create notebook
    nb = NotebookTest()

    # execute notebook
    nb.execute()

    # json.loads fails to load JSON messages using character ' instead of ". ast doesnt.
    result = ast.literal_eval(str(nb.nb))
    print(json.dumps(result, indent=4, sort_keys=True))

    # list of test matches. left side is matched with re.search, right side with re.match.
    test_matches = {
        'thisisunique': '^3$',
        'this-returns-20': '^20$',
        'this-is-13': '^13$'
    }

    assert len(result['cells']) == 7

    for k, v in test_matches.items():
        found = False

        for cell in result['cells']:
            # make sure that there's output where we expect it:
            if 'outputs' not in cell:
                continue
            if 'data' not in cell["outputs"][0]:
                continue
            if 'text/plain' not in cell["outputs"][0]['data']:
                continue

            # check if the output matches the current selected pattern:
            if re.search(k, cell['source']):
                if re.match(v, cell["outputs"][0]['data']['text/plain']):
                    # mark pattern as found
                    found = True
                    continue
        if not found:
            raise Exception('Not found {}:{} in outputs'.format(k, v))
