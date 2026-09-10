"""Minimal scene proposal builders for size and crash boundary tests."""

def layer():
    return dict(
        title="层",
        scope_label="域",
        summary="述",
        atmosphere="气",
        rules="规",
        entrance="门",
        objects=[],
        children=[],
    )


def scene(layers):
    return dict(
        schema_name="scene-tree-proposal",
        schema_version="scene-tree-proposal-v1",
        scene_name="景",
        scene_summary="述",
        selected_path=[0],
        scene_layers=layers,
    )

