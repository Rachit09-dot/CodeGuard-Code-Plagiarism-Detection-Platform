def compute_average(values):
    if len(values) == 0:
        return 0
    return sum(values) / len(values)


def main():
    marks = [90, 85, 92]
    print(compute_average(marks))


if __name__ == "__main__":
    main()
