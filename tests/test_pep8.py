import os

from pycodestyle import StyleGuide


def test_pep8():
    report = StyleGuide(ignore=['E501', 'E402']).check_files([os.path.dirname(os.path.abspath(__file__)) + '/../'])
    report.print_statistics()

    if report.messages:
        raise Exception("pep8")
