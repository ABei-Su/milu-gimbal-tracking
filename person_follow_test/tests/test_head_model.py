import tempfile
import unittest
from pathlib import Path
from milu.head_model import resolve_face_model


class HeadModelTests(unittest.TestCase):
    def test_accept_ax_face_reject_person_and_wrong_platform(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "n.axmodel").write_bytes(b"test")
            (p / "v.axmodel").write_bytes(b"test")
            mud = p / "face.mud"
            text = "[basic]\ntype=axmodel\nmodel_npu=n.axmodel\nmodel_vnpu=v.axmodel\n[extra]\nmodel_type=yolov8\nlabels=face\n"
            mud.write_text(text)
            self.assertEqual(resolve_face_model(str(mud))[1], "yolov8")
            mud.write_text(text.replace("labels=face", "labels=person"))
            with self.assertRaises(ValueError):
                resolve_face_model(str(mud))
            mud.write_text(text.replace("type=axmodel", "type=cvimodel"))
            with self.assertRaises(ValueError):
                resolve_face_model(str(mud))

    def test_auto_missing_is_actionable(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(FileNotFoundError, "FACE_MODEL_REQUIRED"):
                resolve_face_model("auto:face", folder)
