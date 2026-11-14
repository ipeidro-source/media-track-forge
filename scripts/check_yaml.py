"""Parse repository YAML, rejecting duplicate keys instead of silently replacing them."""

from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def construct_mapping(loader: UniqueKeyLoader, node: MappingNode) -> dict[Any, Any]:
    """Construct a mapping only if all keys are unique."""
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)


def main() -> int:
    """Validate workflow and Dependabot YAML syntax from the repository root."""
    for path in sorted(Path(".github").rglob("*.yml")):
        yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        print(f"Valid YAML: {path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
