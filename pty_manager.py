"""PTY Manager: Spawns and manages pseudo-terminal sessions for the web UI."""

import os
import pty
import fcntl
import struct
import signal
import select
import subprocess
import termios
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "> /dev/sda",
]


class PTYSession:
    """A single pseudo-terminal session."""

    def __init__(self, pty_id: str, command: Optional[str] = None):
        self.pty_id = pty_id
        self.command = command
        self.created_at = datetime.now().isoformat()
        self.last_activity = time.time()
        self.master_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self.alive = False
        self._output_buffer = bytearray()
        self._lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None

    def start(self):
        """Spawn the PTY process."""
        master_fd, slave_fd = pty.openpty()
        self.master_fd = master_fd

        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        shell = os.environ.get('SHELL', '/bin/zsh')
        if self.command:
            args = [shell, '-c', self.command]
        else:
            args = [shell, '-l']

        self.pid = os.fork()
        if self.pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ,
                        struct.pack('HHHH', 24, 80, 0, 0))
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            os.execvp(args[0], args)
        else:
            # Parent process
            os.close(slave_fd)
            self.alive = True
            self._reader_thread = threading.Thread(
                target=self._read_loop, daemon=True
            )
            self._reader_thread.start()

    def _read_loop(self):
        """Continuously read from PTY master fd into buffer."""
        while self.alive and self.master_fd is not None:
            try:
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                if ready:
                    data = os.read(self.master_fd, 4096)
                    if data:
                        with self._lock:
                            self._output_buffer.extend(data)
                        self.last_activity = time.time()
                    else:
                        self.alive = False
                        break
            except OSError:
                self.alive = False
                break

    def read_output(self) -> str:
        """Read and drain the output buffer."""
        with self._lock:
            data = bytes(self._output_buffer)
            self._output_buffer.clear()
        return data.decode('utf-8', errors='replace')

    def read_output_bytes(self) -> bytes:
        """Read and drain the output buffer as raw bytes."""
        with self._lock:
            data = bytes(self._output_buffer)
            self._output_buffer.clear()
        return data

    def write_input(self, data: str):
        """Write to the PTY stdin."""
        if self.master_fd is not None and self.alive:
            os.write(self.master_fd, data.encode('utf-8'))
            self.last_activity = time.time()

    def write_input_bytes(self, data: bytes):
        """Write raw bytes to PTY stdin."""
        if self.master_fd is not None and self.alive:
            os.write(self.master_fd, data)
            self.last_activity = time.time()

    def resize(self, cols: int, rows: int):
        """Resize the PTY window."""
        if self.master_fd is not None:
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def kill(self):
        """Kill the PTY process and clean up."""
        self.alive = False
        if self.pid:
            try:
                os.kill(self.pid, signal.SIGTERM)
                time.sleep(0.1)
                try:
                    os.kill(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(self.pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            except ProcessLookupError:
                pass
            self.pid = None
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

    def get_exit_code(self) -> Optional[int]:
        """Check if process has exited and return exit code."""
        if self.pid is None:
            return None
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid != 0:
                self.alive = False
                return os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        except ChildProcessError:
            self.alive = False
            return -1
        return None


class PTYManager:
    """Manages multiple PTY sessions with safety limits."""

    def __init__(
        self,
        max_sessions: int = 3,
        idle_timeout: int = 600,
        log_file: Optional[str] = None,
    ):
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self.sessions: Dict[str, PTYSession] = {}
        self._lock = threading.Lock()

        if log_file:
            self.log_path = Path(log_file)
        else:
            self.log_path = Path.home() / ".disk-analyzer" / "terminal.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _check_blocked(self, command: str):
        """Reject dangerous commands."""
        normalized = command.strip().lower()
        for pattern in BLOCKED_PATTERNS:
            if pattern.lower() in normalized:
                raise ValueError(f"Blocked command pattern: {pattern}")

    def _log_command(self, pty_id: str, command: Optional[str]):
        """Log command execution."""
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] pty={pty_id} command={command or 'interactive shell'}\n"
        with open(self.log_path, 'a') as f:
            f.write(entry)

    def create_session(self, command: Optional[str] = None) -> str:
        """Create a new PTY session. Returns pty_id."""
        with self._lock:
            self._reap_dead()
            if len(self.sessions) >= self.max_sessions:
                raise RuntimeError(
                    f"Maximum {self.max_sessions} sessions reached. "
                    "Kill an existing session first."
                )
            if command:
                self._check_blocked(command)
            pty_id = uuid.uuid4().hex[:12]
            session = PTYSession(pty_id, command)
            session.start()
            self.sessions[pty_id] = session
            self._log_command(pty_id, command)
            return pty_id

    def read_output(self, pty_id: str) -> str:
        return self._get_session(pty_id).read_output()

    def read_output_bytes(self, pty_id: str) -> bytes:
        return self._get_session(pty_id).read_output_bytes()

    def write_input(self, pty_id: str, data: str):
        self._get_session(pty_id).write_input(data)

    def write_input_bytes(self, pty_id: str, data: bytes):
        self._get_session(pty_id).write_input_bytes(data)

    def resize(self, pty_id: str, cols: int, rows: int):
        self._get_session(pty_id).resize(cols, rows)

    def kill_session(self, pty_id: str):
        with self._lock:
            if pty_id not in self.sessions:
                raise KeyError(f"No session: {pty_id}")
            session = self.sessions.pop(pty_id)
        session.kill()

    def list_sessions(self) -> List[Dict]:
        with self._lock:
            self._reap_dead()
            return [
                {'pty_id': s.pty_id, 'command': s.command, 'created_at': s.created_at, 'alive': s.alive}
                for s in self.sessions.values()
            ]

    def cleanup_all(self):
        with self._lock:
            for session in list(self.sessions.values()):
                session.kill()
            self.sessions.clear()

    def cleanup_idle(self):
        now = time.time()
        with self._lock:
            for pty_id, session in list(self.sessions.items()):
                if now - session.last_activity > self.idle_timeout:
                    session.kill()
                    del self.sessions[pty_id]

    def _get_session(self, pty_id: str) -> PTYSession:
        with self._lock:
            if pty_id not in self.sessions:
                raise KeyError(f"No session: {pty_id}")
            return self.sessions[pty_id]

    def _reap_dead(self):
        for pty_id in list(self.sessions.keys()):
            session = self.sessions[pty_id]
            if not session.alive:
                session.kill()
                del self.sessions[pty_id]
