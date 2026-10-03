def total(nums):
    total = 0
    for value in nums:
        if value > 0:
            total += value * 2
    return total


def main():
    numbers = [1, 2, 3]
    print(total(numbers))


if __name__ == "__main__":
    main()
