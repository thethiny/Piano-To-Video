from multiprocessing.pool import ThreadPool

pool = ThreadPool(4)

def get_int(string):
    return int(string)

results = pool.map(get_int, range(100), 4)

print(results)