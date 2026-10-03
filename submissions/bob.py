# Similar logic with different identifiers


def compute(items):
    running = 0
    for item in items:
        if item > 0:
            running += item * 2
    return running


def starter():
    vals = [1, 2, 3]
    print(compute(vals))


if __name__ == "__main__":
    starter()
