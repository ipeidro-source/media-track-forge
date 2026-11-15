"""Controlled packet-scan failures shared by validation and read-only diagnosis."""

from mediatrack_forge.application.inspection import (
    ExecutableError,
    InspectionError,
    ProbeFailedError,
    ProbeOutputLimitError,
    ProbeResponseError,
    ProbeTimeoutError,
)


class PacketScanError(ValueError):
    """Fixed code and safe explanation; never format an underlying exception."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


def probe_failure(exc: InspectionError) -> PacketScanError:
    if isinstance(exc, ProbeTimeoutError):
        return PacketScanError(
            "TIMEOUT",
            "Full packet scan exceeded the configured time limit. "
            "Measure with the read-only packet diagnostic using an explicit bounded limit; "
            "a timeout alone does not identify media corruption or an SMB fault.",
        )
    if isinstance(exc, ProbeOutputLimitError):
        channel = "STDOUT" if exc.channel == "stdout" else "STDERR"
        return PacketScanError(
            f"{channel}_LIMIT",
            f"Packet probe exceeded the bounded {channel.lower()} limit. "
            "Check the tool and media locally; raw probe logs are intentionally withheld.",
        )
    if isinstance(exc, ExecutableError):
        return PacketScanError("EXECUTABLE", "Select an available native ffprobe executable.")
    if isinstance(exc, ProbeFailedError):
        return PacketScanError(
            "PROBE_FAILED",
            "ffprobe returned a nonzero exit status. Check the scanned file's availability, "
            "permissions and media readability; this does not establish a transport failure.",
        )
    if isinstance(exc, ProbeResponseError):
        return PacketScanError("RESPONSE", "The bounded probe response could not be obtained.")
    return PacketScanError("INSPECTION", "Packet probing failed; check the selected file and tool.")
