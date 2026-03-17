from functools import total_ordering
from typing import Any


@total_ordering
class Base64:
    """
    This class allows converting integers (base10) into a custom-made b64 format.
    """

    def __init__(self, in_number: int | str, is_in_base: bool = False, autodetect: bool = False) -> None:
        self.alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_"

        if autodetect:
            try:
                self.value = self.encode(int(in_number))
            except ValueError:
                assert isinstance(in_number, str)
                self.value = in_number
        else:
            if is_in_base:
                assert isinstance(in_number, str)
                self.value = in_number
            else:
                assert isinstance(in_number, int)
                self.value = self.encode(in_number)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.decode()

    def __sub__(self, other: int | str | float) -> Base64:
        return Base64(int(self) - int(other))

    def __add__(self, other: int | str | float) -> Base64:
        return Base64(int(self) + int(other))

    def __mul__(self, other: int | str | float) -> Base64:
        return Base64(int(self) * int(other))

    def __floordiv__(self, other: int | str | float) -> Base64:
        return Base64(int(self) // int(other))

    def __truediv__(self, other: int | str | float) -> None:
        raise TypeError("no truedivision (a / b) possible without floatnumbers (this class only supports integers). try floordiv (a // b) instead.")

    def __lt__(self, other: int | str | float) -> bool:
        return int(self) < int(other)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Base64):
            return self.value == other.value
        elif isinstance(other, int | str | float):
            return str(self.value) == str(other)
        return False

    def encode(self, number: int) -> str:
        "Converts Base10 number to a custom Base64 number"
        base = ""
        sign = ""

        if number < 0:
            sign = "-"
            number = -number

        if 0 <= number < len(self.alphabet):
            return sign + self.alphabet[number]

        while number != 0:
            number, i = divmod(number, len(self.alphabet))
            base = self.alphabet[i] + base

        return sign + base

    def decode(self) -> int:
        "Converts custom Base64 number back to Base 10 integer"
        number = self.value
        negative = False
        base10 = len(self.alphabet)

        if number[0] == "-":
            number = number[1:]
            negative = True

        result = 0

        for i in reversed(range(len(number))):
            val = number[0:1]

            result += self.alphabet.index(val) * pow(base10, i)
            number = number[1:]

        if negative:
            result = -result

        return int(result)
