import json
import tempfile
import unittest
from pathlib import Path
from core import drive_inventory,drive_graph,scan_neighbourhood,transfer_files,transfer_plan

class RevisionTests(unittest.TestCase):
    def test_only_physical_disks_have_sidebar_records(self):
        drives=drive_inventory({"blockdevices":[
            {"name":"nvme0n1","path":"/dev/nvme0n1","type":"disk","children":[
                {"name":"nvme0n1p1","path":"/dev/nvme0n1p1","type":"part","mountpoint":"/","fstype":"btrfs"}]},
            {"name":"zram0","path":"/dev/zram0","type":"disk","fstype":"swap"},
            {"name":"loop0","path":"/dev/loop0","type":"loop"}]})
        self.assertEqual(len(drives),1)
        nodes,devices=drive_graph(drives[0])
        self.assertEqual({n.kind for n in nodes},{"drive","partition"})
        self.assertEqual(devices["/dev/nvme0n1p1"]["mount"],"/")
    def test_graph_budget_preserves_direct_children(self):
        with tempfile.TemporaryDirectory() as temp:
            for i in range(20):
                folder=Path(temp)/str(i);folder.mkdir()
                for j in range(10):(folder/str(j)).touch()
            nodes,_=scan_neighbourhood(temp,limit=50)
            self.assertLessEqual(len(nodes),50)
            self.assertEqual(sum(n.depth==1 for n in nodes),20)
    def test_batch_move_and_collision_preflight(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);target=root/"target";target.mkdir()
            a=root/"a.txt";b=root/"b.txt";a.write_text("a");b.write_text("b")
            (target/"b.txt").write_text("existing")
            with self.assertRaises(FileExistsError):transfer_files([str(a),str(b)],str(target))
            self.assertTrue(a.exists());self.assertEqual((target/"b.txt").read_text(),"existing")
            (target/"b.txt").unlink()
            moved,error=transfer_files([str(a),str(b)],str(target))
            self.assertFalse(error);self.assertEqual(len(moved),2);self.assertFalse(a.exists())
    def test_parent_and_child_selection_moves_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/"folder";source.mkdir();child=source/"file";child.touch();target=root/"target";target.mkdir()
            self.assertEqual(len(transfer_plan([str(source),str(child)],str(target))),1)
            with self.assertRaises(ValueError):transfer_plan([str(source)],str(source))

if __name__=="__main__":unittest.main()
