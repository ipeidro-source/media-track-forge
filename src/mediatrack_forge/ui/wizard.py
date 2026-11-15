"""Sequential presentation navigation, independent of widgets and media policy."""

from enum import IntEnum


class Step(IntEnum):
    MEDIA = 1
    METADATA = 2
    OPERATION = 3
    REVIEW = 4
    EXECUTION = 5


class WizardState:
    def __init__(self) -> None:
        self.step = Step.MEDIA

    def next(self, *, inspected: bool, busy: bool) -> None:
        if busy or not inspected or self.step not in (Step.MEDIA, Step.METADATA):
            raise ValueError("Complete the current step before continuing.")
        self.step = Step(self.step + 1)

    def back(self, *, busy: bool, recovery_required: bool) -> None:
        if busy or recovery_required or self.step == Step.EXECUTION:
            raise ValueError("Wait for safe completion before navigating.")
        self.step = Step(max(Step.MEDIA, self.step - 1))

    def review(self, *, busy: bool) -> None:
        if busy or self.step != Step.OPERATION:
            raise ValueError("Configure the operation before reviewing it.")
        self.step = Step.REVIEW

    def executing(self) -> None:
        self.step = Step.EXECUTION

    def reset(self, *, safe: bool) -> None:
        if not safe:
            raise ValueError("Keep recovery information visible until cleanup is verified.")
        self.step = Step.MEDIA
