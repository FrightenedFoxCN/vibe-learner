"""Public model-owned scene proposal samples."""


def scene_proposal_payload() -> dict[str, object]:
    return {
        "schema_name": "scene-tree-proposal",
        "schema_version": "scene-tree-proposal-v1",
        "scene_name": "Study room",
        "scene_summary": "A bounded study room.",
        "selected_path": [0],
        "scene_layers": [scene_layer_payload(title="Room")],
    }



def scene_layer_payload(*, title: str) -> dict[str, object]:
    return {
        "title": title,
        "scope_label": "room",
        "summary": "A room for focused study.",
        "atmosphere": "Quiet.",
        "rules": "Keep the room organized.",
        "entrance": "Enter through the door.",
        "tags": ["room", "study"],
        "reuse_hint": "Reusable as a study room.",
        "objects": [
            {
                "name": "Board",
                "description": "A writing board.",
                "interaction": "Write on the board.",
                "tags": ["board"],
                "reuse_hint": "Reusable as a board.",
            }
        ],
        "children": [],
    }

