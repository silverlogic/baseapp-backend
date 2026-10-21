import io
import subprocess
from pathlib import Path

from pypdf import PdfWriter


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def option(command: list[str], name: str) -> str | None:
    """The value of a `--name=value` Chrome option in `command`, if present."""
    prefix = f"--{name}="
    for argument in command:
        if argument.startswith(prefix):
            return argument[len(prefix) :]
    return None


class FakeChrome:
    """
    Stands in for `baseapp_pdf.utils.run_chrome` so renders can be tested without Chrome.

    Like the real thing it answers `--version`, writes a PDF to `--print-to-pdf` and leaves a
    `scoped_dir*` folder under `TMPDIR`. Every call is recorded, with the HTML source it was
    asked to print when that is a local file.
    """

    def __init__(self, write_pdf: bool = True) -> None:
        self.write_pdf = write_pdf
        self.calls: list[dict] = []

    @property
    def renders(self) -> list[dict]:
        return [call for call in self.calls if "--version" not in call["command"]]

    def __call__(self, command: list[str], *args, **kwargs) -> subprocess.CompletedProcess:
        call = {"command": list(command), "kwargs": kwargs, "html": None}
        self.calls.append(call)
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, stdout=b"Chromium 1.0", stderr=b"")

        source = Path(command[-1])
        if source.is_file():
            call["html"] = source.read_bytes()
        scoped_dir = Path(kwargs["env"]["TMPDIR"]) / f"scoped_dir{len(self.calls)}"
        scoped_dir.mkdir()
        (scoped_dir / "SingletonCookie").write_text("in use")
        call["scoped_dir"] = scoped_dir
        if self.write_pdf:
            Path(option(command, "print-to-pdf")).write_bytes(blank_pdf())
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
