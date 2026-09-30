"""Core behavior tests: run with python3 -m unittest discover -s tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import node_radius, path_journey, scan_neighbourhood, search_files


class CoreTests(unittest.TestCase):
    def test_directory_graph_and_size(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Folder").mkdir()
            (root / "Folder" / "large.bin").write_bytes(b"x" * 65536)
            (root / "small.txt").write_text("small")
            nodes, hidden = scan_neighbourhood(temp)
            by_name = {node.name: node for node in nodes}
            self.assertEqual(hidden, 0)
            self.assertEqual(by_name["large.bin"].parent, str(root / "Folder"))
            self.assertGreater(node_radius(by_name["large.bin"]), node_radius(by_name["small.txt"]))

    def test_route_crosses_shared_ancestor(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "A" / "child"
            destination = Path(temp) / "B" / "target.txt"
            source.mkdir(parents=True)
            destination.parent.mkdir()
            destination.touch()
            self.assertEqual(path_journey(str(source), str(destination)),
                             [str(source.parent), temp, str(destination.parent)])

    def test_filename_search_uses_plocate_argument_vector(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "result.txt"
            path.touch()
            with patch("core.shutil.which", return_value="/usr/bin/plocate"), patch("core.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = os.fsencode(path) + b"\0"
                self.assertEqual(search_files("name; touch /tmp/unsafe"), [str(path)])
                self.assertEqual(run.call_args.args[0],
                                 ["plocate", "-0", "-i", "-l", "90", "--", "name; touch /tmp/unsafe"])


if __name__ == "__main__":
    unittest.main()
