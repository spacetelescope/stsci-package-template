from packagename.example_mod import primes


def test_primes():
    assert primes(10) == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
