"""Background agents that automate disk maintenance tasks."""

import asyncio
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

AGENTS_FILE = Path.home() / ".disk-analyzer" / "agents.json"
AGENTS_LOG = Path.home() / ".disk-analyzer" / "agents.log"


def _log(msg: str):
    """Append a line to the agents log. Best-effort: logging is a side
    observation of an operation, not a precondition for it, so any I/O
    failure here (e.g. agents.log left root-owned by a previous
    `sudo make web` run) is swallowed and reported as a warning instead of
    crashing the caller. Programming errors (TypeError, etc.) still raise
    normally -- only OSError (PermissionError, disk full, missing dir, ...)
    is treated as best-effort.
    """
    try:
        AGENTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat()
        with open(AGENTS_LOG, 'a') as f:
            f.write(f"[{timestamp}] {msg}\n")
    except OSError as e:
        print(f"Warning: could not write to agents log {AGENTS_LOG}: {e}")


AGENT_DEFINITIONS = {
    "cache_cleaner": {
        "name": "Cache Cleaner",
        "description": "Cleans system and app caches weekly",
        "interval_hours": 168,  # weekly
        "commands": [
            "rm -rf ~/Library/Caches/*",
            "rm -rf /tmp/*",
        ],
    },
    "docker_pruner": {
        "name": "Docker Pruner",
        "description": "Removes unused Docker images when space exceeds threshold",
        "interval_hours": 24,
        "commands": [
            "docker system prune -f",
        ],
    },
    "log_rotator": {
        "name": "Log Rotator",
        "description": "Compresses and removes old log files",
        "interval_hours": 168,
        "commands": [
            "find ~/Library/Logs -name '*.log' -mtime +7 -delete",
        ],
    },
    "downloads_watcher": {
        "name": "Downloads Watcher",
        "description": "Flags download files older than 30 days",
        "interval_hours": 24,
        "commands": [],  # This one just reports, doesn't delete
    },
    "node_scout": {
        "name": "Node Modules Scout",
        "description": "Cleans node_modules from projects inactive for 3+ months",
        "interval_hours": 168,
        "commands": [],  # Needs project scanning logic
    },
}


class AgentsManager:
    def __init__(self):
        self.agents_state: Dict = self._load_state()
        self._task: Optional[asyncio.Task] = None
        # Throttling bookkeeping for the scheduler's dry-run log line (see
        # start_scheduler()). Intentionally NOT persisted to AGENTS_FILE and
        # NOT the same field as agents_state[...]["last_run"] -- it only
        # controls log noise and must reset naturally on restart, whereas
        # last_run must stay unset forever for the permanent-dry-run policy
        # to keep working.
        self._last_dry_run_notice: Dict[str, datetime] = {}

    def _load_state(self) -> Dict:
        try:
            if AGENTS_FILE.exists():
                with open(AGENTS_FILE) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_state(self) -> bool:
        """Persist agents state to disk. Unlike _log(), a failure here is
        consequential (an agent run's bookkeeping would silently vanish), so
        it must not be pretended-successful. It still must not crash the
        caller mid-operation (e.g. after a real cleanup already ran) --
        instead it is caught, warned about, and reported back via the
        return value so callers can surface it to the user.
        Returns True on success, False if the state could not be written.
        """
        try:
            AGENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(AGENTS_FILE, 'w') as f:
                json.dump(self.agents_state, f, indent=2)
            return True
        except OSError as e:
            print(f"Warning: could not save agents state to {AGENTS_FILE}: {e}")
            return False

    def get_agents(self) -> list:
        """Return all agents with their status."""
        result = []
        for agent_id, defn in AGENT_DEFINITIONS.items():
            state = self.agents_state.get(agent_id, {})
            result.append({
                "id": agent_id,
                "name": defn["name"],
                "description": defn["description"],
                "interval_hours": defn["interval_hours"],
                "enabled": state.get("enabled", False),
                "last_run": state.get("last_run"),
                "last_freed": state.get("last_freed", 0),
                "total_freed": state.get("total_freed", 0),
                "run_count": state.get("run_count", 0),
            })
        return result

    def toggle_agent(self, agent_id: str, enabled: bool) -> dict:
        """Enable or disable an agent. Returns whether the change was
        actually persisted, so callers (the API endpoint) can tell the
        difference between "saved" and "lives only in memory until the next
        write or process restart" -- consistent with run_agent()'s
        state_saved/warning fields."""
        if agent_id not in AGENT_DEFINITIONS:
            raise ValueError(f"Unknown agent: {agent_id}")
        if agent_id not in self.agents_state:
            self.agents_state[agent_id] = {}
        self.agents_state[agent_id]["enabled"] = enabled
        state_saved = self._save_state()
        _log(f"Agent {agent_id} {'enabled' if enabled else 'disabled'}")
        return {"state_saved": state_saved}

    def run_agent(self, agent_id: str, dry_run: bool = True) -> dict:
        """Run an agent. dry_run=True (default) reports what WOULD run without
        executing anything -- no subprocess is invoked. Pass dry_run=False to
        actually execute the agent's commands."""
        if agent_id not in AGENT_DEFINITIONS:
            raise ValueError(f"Unknown agent: {agent_id}")

        defn = AGENT_DEFINITIONS[agent_id]

        if dry_run:
            _log(f"[dry-run] agent {agent_id}: would run {defn['commands']}")
            return {
                "agent_id": agent_id,
                "dry_run": True,
                "would_run": list(defn["commands"]),
                "freed": 0,
                "results": [],
            }

        usage_before = shutil.disk_usage("/").used

        results = []
        for cmd in defn["commands"]:
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=120
                )
                results.append({
                    "command": cmd,
                    "success": result.returncode == 0,
                    "output": result.stdout[:500] if result.stdout else "",
                    "error": result.stderr[:500] if result.stderr else "",
                })
            except subprocess.TimeoutExpired:
                results.append({"command": cmd, "success": False, "error": "Timeout"})
            except Exception as e:
                results.append({"command": cmd, "success": False, "error": str(e)})

        usage_after = shutil.disk_usage("/").used
        freed = max(0, usage_before - usage_after)

        # Update state
        if agent_id not in self.agents_state:
            self.agents_state[agent_id] = {}
        state = self.agents_state[agent_id]
        state["last_run"] = datetime.now().isoformat()
        state["last_freed"] = freed
        state["total_freed"] = state.get("total_freed", 0) + freed
        state["run_count"] = state.get("run_count", 0) + 1
        state_saved = self._save_state()

        _log(f"Agent {agent_id} ran: freed {freed} bytes, {len(results)} commands")

        response = {
            "agent_id": agent_id,
            "dry_run": False,
            "freed": freed,
            "results": results,
            "state_saved": state_saved,
        }
        if not state_saved:
            # Surface the persistence failure -- the cleanup itself already
            # ran, but its bookkeeping (last_run/total_freed/run_count) was
            # NOT recorded and may be lost.
            response["warning"] = (
                "La limpieza se ejecutó, pero no se pudo guardar el estado del "
                "agente (revisa permisos de ~/.disk-analyzer)."
            )
        return response

    async def start_scheduler(self):
        """Start the background scheduler loop."""
        _log("Agent scheduler started")
        while True:
            await asyncio.sleep(3600)  # Check every hour
            for agent_id, defn in AGENT_DEFINITIONS.items():
                state = self.agents_state.get(agent_id, {})
                if not state.get("enabled"):
                    continue
                last_run = state.get("last_run")
                if last_run:
                    elapsed = (datetime.now() - datetime.fromisoformat(last_run)).total_seconds() / 3600
                    if elapsed < defn["interval_hours"]:
                        continue
                # Time to run.
                # Design decision (Phase 2): the scheduler stays in permanent
                # dry-run -- it only logs what it would delete. Unattended
                # real deletion is a product decision deferred to a later
                # phase; users can trigger a real run on demand via
                # POST /api/agents/{id}/run?confirm=true.
                #
                # Throttling: dry-run intentionally never sets last_run (see
                # comment above), so the "time to run" branch above would
                # otherwise trip on *every* hourly tick forever once an agent
                # is enabled -- writing an identical "[dry-run] ..." line to
                # agents.log 24x/day (and drowning /api/digest's log tail in
                # noise), in a tool whose whole point is flagging runaway
                # disk usage. `_last_dry_run_notice` is separate, in-memory,
                # log-only throttling state: it limits the notice to once per
                # the agent's own interval_hours, without touching
                # `last_run`/agents_state (which must stay as-is for the
                # permanent-dry-run policy above and for persistence).
                last_notice = self._last_dry_run_notice.get(agent_id)
                if last_notice:
                    since_notice = (datetime.now() - last_notice).total_seconds() / 3600
                    if since_notice < defn["interval_hours"]:
                        continue
                self._last_dry_run_notice[agent_id] = datetime.now()
                _log(f"Scheduler running agent (dry-run): {agent_id}")
                try:
                    self.run_agent(agent_id, dry_run=True)
                except Exception as e:
                    _log(f"Scheduler error for {agent_id}: {e}")

    def start(self):
        """Start scheduler as an asyncio task."""
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self.start_scheduler())

    def stop(self):
        """Stop the scheduler."""
        if self._task:
            self._task.cancel()
