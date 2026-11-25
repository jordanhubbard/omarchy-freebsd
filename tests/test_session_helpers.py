"""Native process-supervision controls; every signal stays in an owned subtree."""
import contextlib
import ctypes
import errno
import json
import os
from pathlib import Path
import pwd
import select
import signal
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
HERE = str(Path(__file__).resolve())
PYTHON = sys.executable


@contextlib.contextmanager
def deadline(seconds=12):
    def expired(_sig, _frame):
        raise TimeoutError("owned process did not complete")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def reap(pid):
    with deadline():
        got, status = os.waitpid(pid, 0)
    assert got == pid
    return os.waitstatus_to_exitcode(status)


def ready(fd):
    assert select.select([fd], [], [], 8)[0], "child did not become ready"
    assert os.read(fd, 1) == b"R", "child exited before becoming ready"


def pipe():
    return os.pipe()


def hold(fd, stubborn=False):
    if stubborn:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    else:
        for sig in [signal.SIGHUP, signal.SIGINT, signal.SIGTERM, signal.SIGUSR1]:
            signal.signal(sig, lambda number, _frame: os._exit(100 + number))
    os.write(fd, b"R")
    os.close(fd)
    while True:
        signal.pause()


def sibling():
    read, write = pipe()
    child = subprocess.Popen([PYTHON, "-I", "-B", HERE, "--payload", "hold", str(write)],
                             pass_fds=(write,))
    os.close(write)
    ready(read)
    os.close(read)
    return child


class Scope:
    """An outer native reaper makes even failed controls reclaimable."""
    def __init__(self, directory):
        values = json.loads((Path(directory) / "abi.json").read_text())
        id_types = {(4, False): ctypes.c_uint32, (4, True): ctypes.c_int32,
                    (8, False): ctypes.c_uint64, (8, True): ctypes.c_int64}
        id_type = id_types[(values["id_size"], bool(values["id_signed"]))]
        self.values = values
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.procctl.argtypes = [ctypes.c_int, id_type, ctypes.c_int, ctypes.c_void_p]
        self.libc.procctl.restype = ctypes.c_int

    def __enter__(self):
        assert os.geteuid() != 0, "runtime controls must be unprivileged"
        if self.libc.procctl(self.values["P_PID"], os.getpid(), self.values["acquire"], None):
            raise OSError(ctypes.get_errno(), "acquire owned reaper")
        return self

    def __exit__(self, *_error):
        request = ctypes.create_string_buffer(self.values["kill_size"])
        ctypes.c_int.from_buffer(request, self.values["signal_offset"]).value = signal.SIGKILL
        result = self.libc.procctl(self.values["P_PID"], os.getpid(), self.values["kill"], request)
        if result and ctypes.get_errno() != errno.ESRCH:
            raise OSError(ctypes.get_errno(), "clean up owned reaper descendants")
        with deadline():
            while True:
                try:
                    os.waitpid(-1, 0)
                except ChildProcessError:
                    break


def parent_death(directory, name, sig):
    read, write = pipe()
    gate_read, gate_write = pipe()
    pid_read, pid_write = pipe()
    os.set_inheritable(write, True)
    launcher = os.fork()
    if launcher == 0:
        child = os.fork()
        if child == 0:
            os.execv(str(Path(directory) / "pdeathsig"),
                     ["pdeathsig", name, PYTHON, "-I", "-B", HERE,
                      "--payload", "hold", str(write)])
        os.write(pid_write, (str(child) + "\n").encode())
        os.read(gate_read, 1)
        os._exit(0)
    os.close(write)
    os.close(pid_write)
    os.close(gate_read)
    with os.fdopen(pid_read) as stream:
        child = int(stream.readline())
    ready(read)
    os.close(read)
    os.write(gate_write, b"G")
    os.close(gate_write)
    assert reap(launcher) == 0
    expected = -int(sig) if sig == signal.SIGKILL else 100 + int(sig)
    assert reap(child) == expected, "parent-death signal was lost or changed"


def session_payload(ready_fd, gate_fd, report_fd, stubborn):
    workers = []
    read, write = pipe()
    cooperative = os.fork()
    if cooperative == 0:
        hold(write)
    workers.append(cooperative)
    ready(read)
    if stubborn:
        pid_read, pid_write = pipe()
        intermediate = os.fork()
        if intermediate == 0:
            orphan = os.fork()
            if orphan == 0:
                os.setsid()  # Cleanup must follow ancestry, not a process group.
                hold(write, stubborn=True)
            os.write(pid_write, (str(orphan) + "\n").encode())
            os._exit(0)
        assert reap(intermediate) == 0
        with os.fdopen(pid_read) as stream:
            workers.append(int(stream.readline()))
        ready(read)
    os.write(report_fd, (json.dumps(workers) + "\n").encode())
    os.write(ready_fd, b"R")
    os.read(gate_fd, 1)
    os._exit(37)


def session_cleanup(directory, stubborn):
    read, write = pipe()
    gate_read, gate_write = pipe()
    report_read, report_write = pipe()
    helper = subprocess.Popen([str(Path(directory) / "session-reaper"),
                               PYTHON, "-I", "-B", HERE, "--payload", "session",
                               str(write), str(gate_read), str(report_write), str(int(stubborn))],
                              pass_fds=(write, gate_read, report_write))
    os.close(write)
    os.close(gate_read)
    os.close(report_write)
    ready(read)
    os.close(read)
    with os.fdopen(report_read) as stream:
        workers = json.loads(stream.readline())
    os.write(gate_write, b"G")
    os.close(gate_write)
    assert helper.wait(timeout=12) == 37, "session exit status changed"
    for pid in workers:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        raise AssertionError(f"session descendant {pid} survived or was not reaped")


def forward(directory, sig):
    read, write = pipe()
    helper = subprocess.Popen([str(Path(directory) / "session-reaper"), PYTHON,
                               "-I", "-B", HERE, "--payload", "hold", str(write)],
                              pass_fds=(write,))
    os.close(write)
    ready(read)
    os.close(read)
    helper.send_signal(sig)
    assert helper.wait(timeout=12) == 100 + sig, "forwarded signal or exit status changed"


def worker(kind, directory, arguments):
    with Scope(directory):
        sentinel = sibling()
        if kind == "parent":
            parent_death(directory, arguments[0], int(arguments[1]))
        elif kind == "cleanup":
            session_cleanup(directory, bool(int(arguments[0])))
        elif kind == "forward":
            forward(directory, int(arguments[0]))
        else:
            raise ValueError(kind)
        assert sentinel.poll() is None, "unrelated same-user sibling was signalled"
        sentinel.terminate()
        assert sentinel.wait(timeout=8) == 100 + signal.SIGTERM
    print(json.dumps({"kind": kind, "arguments": arguments, "status": "pass",
                      "unrelated_sibling_preserved": True}))


@unittest.skipUnless(sys.platform.startswith("freebsd"), "requires native FreeBSD procctl")
class SessionHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        artifacts = os.environ.get("OMARCHY_TEST_ARTIFACTS")
        if artifacts:
            cls.build = Path(tempfile.mkdtemp(prefix="session-helpers-", dir=artifacts))
            print(f"session-helper artifacts: {cls.build}", file=sys.stderr)
        else:
            cls.temporary = tempfile.TemporaryDirectory(prefix="omarchy-session-helpers-")
            cls.addClassCleanup(cls.temporary.cleanup)
            cls.build = Path(cls.temporary.name)
        cls.build.chmod(0o755)
        # A root-run suite may live under /root, which nobody cannot traverse.
        cls.fixture = cls.build / "fixture.py"
        cls.fixture.write_bytes(Path(__file__).read_bytes())
        for name in ["pdeathsig", "session-reaper"]:
            subprocess.run(["cc", "-O2", "-pipe", "-fstack-protector-strong",
                            "-fno-strict-aliasing", "-o", str(cls.build / name),
                            str(ROOT / (name + ".c"))], check=True)
        probe = cls.build / "abi.c"
        probe.write_text(r'''#include <sys/types.h>
#include <sys/procctl.h>
#include <stddef.h>
#include <stdio.h>
int main(void) {
 printf("{\"P_PID\":%d,\"acquire\":%d,\"kill\":%d,"
        "\"kill_size\":%zu,\"signal_offset\":%zu,\"id_size\":%zu,"
        "\"id_signed\":%d}\n",
        P_PID, PROC_REAP_ACQUIRE, PROC_REAP_KILL,
        sizeof(struct procctl_reaper_kill),
        offsetof(struct procctl_reaper_kill, rk_sig), sizeof(id_t),
        (id_t)-1 < (id_t)0);
 return 0;
}
''')
        subprocess.run(["cc", "-o", str(cls.build / "abi"), str(probe)], check=True)
        (cls.build / "abi.json").write_bytes(subprocess.check_output([str(cls.build / "abi")]))

    def unprivileged(self):
        if os.geteuid() == 0:
            account = pwd.getpwnam("nobody")
            os.setgroups([])
            os.setgid(account.pw_gid)
            os.setuid(account.pw_uid)

    def record(self, label, completed):
        if os.environ.get("OMARCHY_TEST_ARTIFACTS"):
            cls = type(self)
            cls.case_number = getattr(cls, "case_number", 0) + 1
            def text(value):
                return value.decode(errors="replace") if isinstance(value, bytes) else value
            (self.build / f"case-{cls.case_number:03d}.json").write_text(json.dumps({
                "test": self.id(), "label": label, "argv": completed.args,
                "exit": completed.returncode, "stdout": text(completed.stdout),
                "stderr": text(completed.stderr),
            }, indent=2) + "\n")

    def scenario(self, kind, *arguments):
        completed = subprocess.run([PYTHON, "-I", "-B", str(self.fixture), "--worker", kind,
                                    str(self.build), *map(str, arguments)],
                                   capture_output=True, text=True, timeout=35,
                                   preexec_fn=self.unprivileged)
        self.record(f"{kind}:{arguments}", completed)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["unrelated_sibling_preserved"])

    def test_parent_death_signal_delivery(self):
        for name, sig in [("term", signal.SIGTERM), ("SIGTERM", signal.SIGTERM),
                          (str(signal.SIGTERM.value), signal.SIGTERM),
                          ("USR1", signal.SIGUSR1), ("KILL", signal.SIGKILL)]:
            with self.subTest(signal=name):
                self.scenario("parent", name, sig.value)

    def test_session_descendant_cleanup(self):
        for stubborn in [False, True]:
            with self.subTest(detached_stubborn_orphan=stubborn):
                self.scenario("cleanup", int(stubborn))

    def test_session_signal_forwarding(self):
        for sig in [signal.SIGHUP, signal.SIGINT, signal.SIGTERM]:
            with self.subTest(signal=sig.name):
                self.scenario("forward", sig.value)

    def test_command_status_and_invalid_invocations(self):
        cases = [("pdeathsig", [], 2), ("session-reaper", [], 2),
                 ("pdeathsig", ["TERM", "/does-not-exist/omarchy-test"], 127),
                 ("session-reaper", ["/does-not-exist/omarchy-test"], 127)]
        for bad in ["", "0", "999999", "TERM-junk"]:
            cases.append(("pdeathsig", [bad, "/usr/bin/true"], 2))
        for helper, arguments, expected in cases:
            with self.subTest(helper=helper, arguments=arguments):
                completed = subprocess.run([str(self.build / helper), *arguments],
                                           capture_output=True, timeout=12,
                                           preexec_fn=self.unprivileged)
                self.record(f"{helper}:{arguments}", completed)
                self.assertEqual(completed.returncode, expected, completed.stderr)
        for helper, arguments in [("pdeathsig", ["TERM"]), ("session-reaper", [])]:
            with self.subTest(helper=helper, exit_status=7):
                completed = subprocess.run([str(self.build / helper), *arguments,
                                            "/bin/sh", "-c", "exit 7"],
                                           capture_output=True, timeout=12,
                                           preexec_fn=self.unprivileged)
                self.record(f"{helper}:exit7", completed)
                self.assertEqual(completed.returncode, 7, completed.stderr)
        for helper, arguments, expected in [
                ("pdeathsig", ["TERM"], -signal.SIGTERM),
                ("session-reaper", [], 128 + signal.SIGTERM)]:
            with self.subTest(helper=helper, signalled_child=True):
                completed = subprocess.run([str(self.build / helper), *arguments,
                                            PYTHON, "-I", "-B", str(self.fixture), "--payload", "die"],
                                           capture_output=True, timeout=12,
                                           preexec_fn=self.unprivileged)
                self.record(f"{helper}:{arguments}", completed)
                self.assertEqual(completed.returncode, expected, completed.stderr)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--payload":
        if sys.argv[2] == "hold":
            hold(int(sys.argv[3]))
        elif sys.argv[2] == "die":
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGTERM)
        elif sys.argv[2] == "session":
            session_payload(*map(int, sys.argv[3:6]), bool(int(sys.argv[6])))
        else:
            raise ValueError(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        unittest.main()
