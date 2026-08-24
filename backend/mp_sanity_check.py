import os
import time
from concurrent.futures import ProcessPoolExecutor


def worker(n):
    return (n, os.getpid())


if __name__ == "__main__":
    print("Parent PID:", os.getpid())
    print("Starting ProcessPoolExecutor with 4 workers...")
    start = time.time()

    with ProcessPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(worker, range(4)))

    print("Finished in", round(time.time() - start, 2), "seconds")
    for n, pid in results:
        print(f"  task {n} ran in child PID {pid}")
