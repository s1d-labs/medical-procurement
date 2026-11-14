"""Put this family's projects in the pool and register its health checks. Run by the Setup workflow (GitHub Actions: the hub
trusts this repo, s1d-labs/<family>, through its OIDC token). Safe to run again: queue items that exist are kept."""
from scrape_hub_client import register_project, seed_queue, set_pool, set_probes

from family import FAMILY, PROBES, PROJECTS, queue

print("health checks:", set_probes(FAMILY, PROBES))
for p in PROJECTS:
    register_project(p["name"], title=p["title"], unit_label=p["unit_label"], record_label=p["record_label"],
                     expected_units=len(queue(p)), expected_records=sum(i["payload"].get("expected", 0) for i in queue(p)))  # this round
    set_pool(p["name"], FAMILY, p["task"], target=p["target"], env=p["env"], probe=p["probe"], max_workers=p.get("max_workers"), pool=p.get("pool", True),
             threads=p.get("threads"), delay_ms=p.get("delay_ms"), proxy=p.get("proxy"),
             proxy_only=p.get("proxy_only"))
    print(p["name"], "queue:", seed_queue(p["name"], queue(p)))
