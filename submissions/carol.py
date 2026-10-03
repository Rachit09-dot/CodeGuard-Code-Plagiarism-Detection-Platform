def average(data):
    if not data:
        return 0
    return sum(data) / len(data)


def demo():
    scores = [90, 85, 92]
    print(average(scores))


if __name__ == "__main__":
    demo()
