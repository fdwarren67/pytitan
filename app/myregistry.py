
import yaml, json, os, time, typing as t
from pathlib import Path
from app.mysnowflake import _describe_view_snowflake

VIEWS_PATH = Path(os.getenv("VIEWS_FILE", "config/views.yaml"))
CACHE_PATH = Path(os.getenv("COLUMNS_CACHE_FILE", "config/columns_cache.json"))
GLOBAL_MAX_PAGE_SIZE = int(os.getenv("GLOBAL_MAX_PAGE_SIZE", "1000"))

class EntityMeta(t.TypedDict, total=False):
    view: str
    maxPageSize: int

class RegistryEntry(t.TypedDict):
    view: str
    columns: dict[str, str]  # NAME -> TYPE_CATEGORY
    loadedAt: str
    maxPageSize: int

class Registry:
    def __init__(self):
        self.entities_cfg: dict[str, EntityMeta] = {}
        self.columns_cache: dict[str, RegistryEntry] = {}

    def load_views(self) -> None:
        if not VIEWS_PATH.exists():
            raise RuntimeError(f"View mapping file not found: {VIEWS_PATH}")
        with VIEWS_PATH.open("r", encoding="utf-8") as f:
            if VIEWS_PATH.suffix.lower() in (".yaml", ".yml"):
                if not yaml:
                    raise RuntimeError("PyYAML not installed but a YAML views file was provided.")
                cfg = yaml.safe_load(f)
            else:
                cfg = json.load(f)
        ents = cfg.get("entities", {})
        norm: dict[str, EntityMeta] = {}
        for k, v in ents.items():
            if not isinstance(v, dict) or "view" not in v:
                raise RuntimeError(f"Bad entity mapping for {k}: {v}")
            item: EntityMeta = {"view": v["view"]}
            if "maxPageSize" in v:
                item["maxPageSize"] = int(v["maxPageSize"])
            norm[k] = item
        self.entities_cfg = norm

    def load_cache(self) -> None:
        if CACHE_PATH.exists():
            with CACHE_PATH.open("r", encoding="utf-8") as f:
                self.columns_cache = json.load(f)
        else:
            self.columns_cache = {}

    def save_cache(self) -> None:
        tmp = CACHE_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self.columns_cache, f, indent=2)
        tmp.replace(CACHE_PATH)

    def ensure_entity(self, name: str) -> RegistryEntry:
        if name not in self.entities_cfg:
            raise KeyError(f"Unknown entity: {name}")
        cfg = self.entities_cfg[name]
        cached = self.columns_cache.get(name)
        if cached and cached.get("view") == cfg["view"]:
            return cached
        cols = _describe_view_snowflake(cfg["view"])
        entry: RegistryEntry = {
            "view": cfg["view"],
            "columns": cols,
            "loadedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "maxPageSize": int(cfg.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE)),
        }
        self.columns_cache[name] = entry
        self.save_cache()
        return entry

    def refresh_all(self) -> dict[str, str]:
        """Re-read views file and re-discover all entities."""
        self.load_views()
        summaries: dict[str, str] = {}
        for name, meta in self.entities_cfg.items():
            try:
                cols = _describe_view_snowflake(meta["view"])
                self.columns_cache[name] = {
                    "view": meta["view"],
                    "columns": cols,
                    "loadedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "maxPageSize": int(meta.get("maxPageSize", GLOBAL_MAX_PAGE_SIZE)),
                }
                summaries[name] = f"ok ({len(cols)} cols)"
            except Exception as e:
                summaries[name] = f"error: {e}"
        self.save_cache()
        return summaries
    
