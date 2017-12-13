def cells():
    '''
    # Slow
    '''

    import time


    def query_db():
        time.sleep(5)
        return [1,2,3,4,5]

    def clean(data):
        time.sleep(2)
        return [x for x in data if x % 2 == 0]

    def myfilter(data):
        time.sleep(2)
        return [x for x in data if x >= 3]

    '''
    '''

    rows = query_db()

    '''
    '''

    data = myfilter(rows)

    '''
    '''

    data, len(data)
