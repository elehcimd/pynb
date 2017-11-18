#! /bin/bash

set -e

cd /tmp
rm -f *.html *.ipynb
python3 /code/tests/nbapp.py --N 10000

echo "Checking HTML export ..."
# Check that the resulting sum is present in the output file
grep 50005000 /tmp/MyTestNotebook.html

echo "Checking Jupyter export ..."
# Check that the resulting sum is present in the output file
grep 50005000 /tmp/MyTestNotebook.ipynb

# Check that the notebook is a valid Jupyter notebook
jupyter nbconvert --stdout --to html MyTestNotebook.ipynb >/tmp/MyTestNotebook2.html
grep 50005000 /tmp/MyTestNotebook2.html

# Check that the notebook contains what we expect in terms of cell sequence
cell_types=$(cat MyTestNotebook.ipynb | grep cell_type | cut -f4 -d\" | tr '\n' :)
echo $cell_types
test "$cell_types" = "markdown:code:code:markdown:"

