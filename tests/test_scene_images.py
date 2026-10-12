from __future__ import annotations

import base64
import io

from PIL import Image

from src.webui.services import scene_images


def _image_data(size: tuple[int, int] = (640, 360), fmt: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, (24, 78, 110)).save(output, format=fmt)
    return output.getvalue()


class _Api:
    def __init__(self, tmp_path):
        self.world = None
        self.rule = None
        self.scene_images = scene_images.SceneImageService(
            scene_images.SceneImageDependencies(
                images_dir=tmp_path / "scene-images",
                load_world_template=lambda _world_id: self.world,
                get_rule_template=lambda _rule_id: (
                    {"rule": self.rule} if self.rule else {}
                ),
                generated_image_file=lambda _asset_id: None,
                plugin_asset_path=self.plugin_asset_path,
            )
        )

    def plugin_asset_path(self, _plugin_id, _relative_path):
        raise KeyError("not installed")


def test_upload_normalizes_and_deduplicates_scene_image(tmp_path):
    api = _Api(tmp_path)
    encoded = base64.b64encode(_image_data()).decode("ascii")

    first = api.scene_images.save_upload(encoded, "cover.png")
    second = api.scene_images.save_upload(encoded, "cover-copy.png")

    assert first["ok"] is True
    assert first["scene_image"] == second["scene_image"]
    path = api.scene_images.file(first["scene_image"]["asset_id"])
    assert path is not None
    with Image.open(path) as image:
        assert image.size == (1600, 900)
        assert image.format == "WEBP"


def test_default_precedence_is_world_then_rule_then_builtin(tmp_path):
    api = _Api(tmp_path)
    api.rule = {"scene_image": {"kind": "builtin", "id": "freeform_coc"}}
    api.world = {
        "default_rule": "freeform_coc",
        "scene_image": {"kind": "builtin", "id": "freeform_wuxia"},
    }

    assert api.scene_images.resolve_default("world", "dnd5e") == {
        "kind": "builtin", "id": "freeform_wuxia",
    }
    api.world.pop("scene_image")
    assert api.scene_images.resolve_default("world", "dnd5e") == {
        "kind": "builtin", "id": "freeform_coc",
    }
    api.world = None
    api.rule = None
    assert api.scene_images.resolve_default("", "dnd5e") == {
        "kind": "builtin", "id": "dnd5e",
    }


def test_package_scene_image_writes_portable_asset_reference(tmp_path):
    api = _Api(tmp_path)
    upload = api.scene_images.save_upload(
        base64.b64encode(_image_data()).decode("ascii")
    )["scene_image"]
    files = {}

    packaged = api.scene_images.package(upload, files)

    assert packaged and packaged["kind"] == "asset"
    assert packaged["path"].startswith("assets/scenes/")
    assert packaged["path"] in files
