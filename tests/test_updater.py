"""Exercise the updater against disposable installs, including failed writes."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import updater
from install_lock import LOCK_NAME, PENDING_NAME, lock_installation


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="orbit-update-test-")
        self.root = Path(self.temp.name)
        self.target = self.root / "installed Orbit"
        self.target.mkdir()
        self.old = {name:(f"old {name}\n").encode() for name in updater.LEGACY_FILES}
        self.old["README.md"] = b"# Orbit Explorer 0.3\n"
        for name, data in self.old.items():
            path = self.target / name
            path.parent.mkdir(exist_ok=True, parents=True); path.write_bytes(data)
        (self.target / "run.sh").chmod(0o755)
        self.custom = self.target / "my-notes.txt"; self.custom.write_text("keep this")
        self.settings = self.root / "config" / "orbit-explorer" / "settings.json"
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"favorites":["/home/me"],"preset":"Midnight Teal"}')
        self.environment = patch.dict(os.environ, {"XDG_CONFIG_HOME":str(self.settings.parent.parent)})
        self.environment.start()
        self.before = self.snapshot()

    def tearDown(self):
        self.environment.stop(); self.temp.cleanup()

    def snapshot(self):
        return {str(path.relative_to(self.target)):path.read_bytes()
                for path in self.target.rglob("*") if path.is_file()
                and not any(part.startswith(".") for part in path.relative_to(self.target).parts)
                and "__pycache__" not in path.parts}

    def package(self, version="0.3.1", prefix="Orbit-Explorer/", extra=None):
        files = {name:f"new {name}\n".encode() for name in updater.REQUIRED}
        files[LOCK_NAME] = b""
        files.update({"README.md":f"# Orbit Explorer {version}\n".encode(), "assets/orbit.svg":b"<svg/>",
                      "new-module.py":b"x = 123\n"})
        if extra: files.update(extra)
        info = {"application":"orbit-explorer", "format":1, "version":version, "files":{
            name:{"sha256":updater.digest(data),"size":len(data), "mode":0o755 if name.endswith(".sh") else 0o644}
            for name,data in sorted(files.items())}}
        archive = self.root / f"release-{version}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            output.writestr(prefix+updater.MANIFEST, json.dumps(info))
            for name,data in files.items(): output.writestr(prefix+name, data)
        return archive

    def apply(self, archive=None):
        return updater.apply_release(updater.Release.load(archive or self.package()), self.target, report=lambda _:None)

    def test_update_replaces_program_keeps_settings_and_does_not_nest(self):
        settings = self.settings.read_bytes()
        backup = self.apply()
        self.assertEqual((self.target/"app.py").read_bytes(), b"new app.py\n")
        self.assertFalse((self.target/"Orbit-Explorer").exists())
        self.assertFalse((self.target/"routing.py").exists())  # Obsolete owned file.
        self.assertEqual(self.custom.read_text(), "keep this")
        self.assertEqual(self.settings.read_bytes(), settings)
        self.assertEqual((backup/"files"/"app.py").read_bytes(), self.old["app.py"])
        self.assertEqual(stat.S_IMODE((self.target/"update.sh").stat().st_mode), 0o755)
        self.assertFalse((self.target/PENDING_NAME).exists())

    def test_repeated_update_is_noop_without_extra_backup(self):
        archive = self.package(); backup = self.apply(archive)
        self.assertIsNone(self.apply(archive))
        self.assertEqual(list((self.target/updater.BACKUPS).iterdir()), [backup])

    def test_rollback_restores_original_files_and_file_modes(self):
        backup = self.apply()
        updater.rollback(backup, self.target, report=lambda _:None)
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(stat.S_IMODE((self.target/"run.sh").stat().st_mode), 0o755)

    def test_failure_mid_update_restores_previous_install(self):
        write = updater.atomic_write
        failed = False
        def fail_once(path, *args, **kwargs):
            nonlocal failed
            if path == self.target/"core.py" and not failed:
                failed = True
                raise OSError("simulated disk full")
            return write(path, *args, **kwargs)
        with patch.object(updater, "atomic_write", side_effect=fail_once):
            with self.assertRaisesRegex(updater.UpdateError, "previous application files were restored"):
                self.apply()
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), self.before)
        self.assertFalse((self.target/PENDING_NAME).exists())

    def test_interrupted_update_blocks_launch_and_can_recover(self):
        backup = self.apply()
        (self.target/"app.py").write_text("interrupted partial application")
        (self.target/PENDING_NAME).write_text(json.dumps({"backup":backup.name}))
        with self.assertRaisesRegex(RuntimeError, "interrupted update"):
            lock_installation(self.target, shared=True)
        with updater.exclusive_installation(self.target):
            self.assertTrue(updater.recover_pending(self.target, report=lambda _:None))
        self.assertEqual(self.snapshot(), self.before)

    def test_next_update_recovers_then_installs(self):
        archive = self.package(); backup = self.apply(archive)
        (self.target/PENDING_NAME).write_text(json.dumps({"backup":backup.name}))
        self.apply(archive)
        self.assertEqual(updater.installed_info(self.target)[0], "0.3.1")
        self.assertFalse((self.target/PENDING_NAME).exists())

    def test_running_instance_prevents_changes(self):
        descriptor = lock_installation(self.target, shared=True)
        try:
            with self.assertRaisesRegex(RuntimeError, "Close every Orbit"):
                self.apply()
            self.assertEqual(self.snapshot(), self.before)
        finally: os.close(descriptor)

    def test_update_lock_blocks_new_app_instance(self):
        descriptor = lock_installation(self.target)
        try:
            with self.assertRaisesRegex(RuntimeError, "being updated"):
                lock_installation(self.target, shared=True)
        finally: os.close(descriptor)

    @unittest.skipUnless(Path("/proc/self/cmdline").exists(), "This test environment does not expose Linux /proc.")
    def test_old_app_process_is_detected_without_lock(self):
        (self.target/"app.py").write_text("import time\ntime.sleep(20)\n")
        process = subprocess.Popen([sys.executable,"app.py"], cwd=self.target)
        try:
            self.assertIn(process.pid, updater.legacy_processes(self.target))
            with self.assertRaisesRegex(updater.UpdateError, "Close Orbit"):
                self.apply()
        finally:
            process.terminate(); process.wait(timeout=5)

    def test_old_app_proc_records_resolve_relative_and_absolute_scripts(self):
        proc=self.root/"proc";proc.mkdir()
        for pid,script in ((12345,b"app.py"),(12346,os.fsencode(self.target/"app.py"))):
            entry=proc/str(pid);entry.mkdir()
            (entry/"cmdline").write_bytes(os.fsencode(sys.executable)+b"\0"+script+b"\0")
            (entry/"cwd").symlink_to(self.target,target_is_directory=True)
        self.assertEqual(set(updater.legacy_processes(self.target,proc)),{12345,12346})

    def test_flat_zip_and_extracted_bundle_both_work(self):
        archive = self.package(prefix="")
        release = updater.Release.load(archive)
        bundle = self.root/"extracted"; bundle.mkdir()
        for name, data in {**release.files,updater.MANIFEST:release.manifest}.items():
            path=bundle/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        self.assertEqual(updater.Release.load(bundle).files, release.files)
        self.apply(archive)

    def test_unrelated_filename_collision_is_refused(self):
        (self.target/"new-module.py").write_text("user extension")
        with self.assertRaisesRegex(updater.UpdateError,"unrelated file"):
            self.apply()
        self.assertEqual((self.target/"app.py").read_bytes(), self.old["app.py"])
        self.assertEqual((self.target/"new-module.py").read_text(), "user extension")

    def test_zip_traversal_symlinks_and_duplicates_are_refused(self):
        for kind in ("traversal", "symlink", "duplicate"):
            with self.subTest(kind=kind):
                archive=self.package()
                with zipfile.ZipFile(archive,"a") as output:
                    if kind=="traversal": output.writestr("../outside",b"no")
                    elif kind=="symlink":
                        member=zipfile.ZipInfo("Orbit-Explorer/link");member.create_system=3
                        member.external_attr=(stat.S_IFLNK|0o777)<<16;output.writestr(member,"/etc/passwd")
                    else:
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore");output.writestr("Orbit-Explorer/app.py",b"duplicate")
                with self.assertRaises(updater.UpdateError): self.apply(archive)
                self.assertEqual(self.snapshot(),self.before)

    def test_tampered_file_hash_is_refused_before_any_change(self):
        archive=self.package()
        with zipfile.ZipFile(archive) as source:
            files={m.filename:source.read(m) for m in source.infolist()}
        files["Orbit-Explorer/app.py"]=b"wrong contents"
        with zipfile.ZipFile(archive,"w") as output:
            for name,data in files.items():output.writestr(name,data)
        with self.assertRaisesRegex(updater.UpdateError,"Checksum mismatch"):self.apply(archive)
        self.assertEqual(self.snapshot(),self.before)

    def test_destination_symlinks_cannot_modify_external_files(self):
        outside=self.root/"outside.py";outside.write_text("keep safe")
        (self.target/"core.py").unlink();(self.target/"core.py").symlink_to(outside)
        with self.assertRaisesRegex(updater.UpdateError,"symbolic link"):self.apply()
        self.assertEqual(outside.read_text(),"keep safe")

    def test_old_backups_cannot_overwrite_a_newer_release(self):
        first=self.apply(self.package("0.3.1"));self.apply(self.package("0.3.2"))
        with self.assertRaisesRegex(updater.UpdateError,"currently installed release"):
            updater.rollback(first,self.target,report=lambda _:None)
        with self.assertRaisesRegex(updater.UpdateError,"older"):
            self.apply(self.package("0.3.1"))

    def test_same_second_python_caches_are_removed(self):
        cache=self.target/"__pycache__";cache.mkdir()
        compiled=cache/"app.cpython-314.pyc";compiled.write_bytes(b"stale cache")
        unrelated=cache/"custom.cpython-314.pyc";unrelated.write_bytes(b"keep")
        self.apply()
        self.assertFalse(compiled.exists());self.assertEqual(unrelated.read_bytes(),b"keep")


if __name__=="__main__":
    unittest.main()
