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
    AGENTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat()
    with open(AGENTS_LOG, 'a') as f:
        f.write(f"[{timestamp}] {msg}\n")


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

    def _load_state(self) -> Dict:
        try:
            if AGENTS_FILE.exists():
                with open(AGENTS_FILE) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_state(self):
        AGENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AGENTS_FILE, 'w') as f:
            json.dump(self.agents_state, f, indent=2)

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

    def toggle_agent(self, agent_id: str, enabled: bool):
        """Enable or disable an agent."""
        if agent_id not in AGENT_DEFINITIONS:
            raise ValueError(f"Unknown agent: {agent_id}")
        if agent_id not in self.agents_state:
            self.agents_state[agent_id] = {}
        self.agents_state[agent_id]["enabled"] = enabled
        self._save_state()
        _log(f"Agent {agent_id} {'enabled' if enabled else 'disabled'}")

    def run_agent(self, agent_id: str) -> dict:
        """Run an agent immediately. Returns result."""
        if agent_id not in AGENT_DEFINITIONS:
            raise ValueError(f"Unknown agent: {agent_id}")

        defn = AGENT_DEFINITIONS[agent_id]
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
        self._save_state()

        _log(f"Agent {agent_id} ran: freed {freed} bytes, {len(results)} commands")

        return {
            "agent_id": agent_id,
            "freed": freed,
            "results": results,
        }

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
                # Time to run
                _log(f"Scheduler running agent: {agent_id}")
                try:
                    self.run_agent(agent_id)
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
