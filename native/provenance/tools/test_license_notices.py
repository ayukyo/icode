import tempfile
import hashlib
import unittest
from pathlib import Path

from license_notices import collect_notices, validate_review


class LicenseClosureTests(unittest.TestCase):
    def test_missing_reviewed_root_notice_is_a_distribution_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            license_path = root / "LICENSE"
            license_path.write_text("Original license\n")
            modules = {("example.org/reviewed", "v1.0.0"): (root, {license_path})}
            for missing in ("NOTICE", "PATENTS"):
                review = {"modules": [{"path": "example.org/reviewed", "version": "v1.0.0", "licenses": {
                    "LICENSE": hashlib.sha256(license_path.read_bytes()).hexdigest(),
                    missing: hashlib.sha256(b"Missing reviewed original\n").hexdigest(),
                }}]}
                with self.subTest(missing=missing), self.assertRaises(ValueError):
                    validate_review(modules, review)

    def test_unknown_module_is_a_distribution_blocker(self):
        with self.assertRaises(ValueError):
            validate_review({("example.org/unreviewed", "v1.0.0"): (Path("unused"), set())}, {"modules": []})

    def test_missing_nested_notice_blocks_only_when_its_ancestry_is_linked(self):
        for linked in (True, False):
            with self.subTest(linked=linked), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                go_root, project, module = root / "go", root / "project", root / "module"
                for directory in (go_root, project, module, module / "pkg"):
                    directory.mkdir()
                texts = {go_root / "LICENSE": b"Go original\n",
                         project / "LICENSE.sigstore": b"Trust anchor original\n",
                         module / "LICENSE": b"Dependency original\n"}
                for path, content in texts.items():
                    path.write_bytes(content)
                nested = "pkg/NOTICE" if linked else "unlinked/NOTICE"
                review = {"go_license_sha256": hashlib.sha256(texts[go_root / "LICENSE"]).hexdigest(),
                          "trust_anchor_license_sha256": hashlib.sha256(texts[project / "LICENSE.sigstore"]).hexdigest(),
                          "modules": [{"path": "example.org/dep", "version": "v1.2.3", "licenses": {
                              "LICENSE": hashlib.sha256(texts[module / "LICENSE"]).hexdigest(),
                              nested: hashlib.sha256(b"Required original notice\n").hexdigest(),
                          }}]}
                packages = [{"Dir": str(module / "pkg"), "Module": {
                    "Path": "example.org/dep", "Version": "v1.2.3", "Dir": str(module)}}]
                if linked:
                    with self.assertRaises(ValueError):
                        collect_notices(packages, go_root, project, review)
                else:
                    self.assertIn("Dependency original", collect_notices(packages, go_root, project, review))

    def test_changed_notice_bytes_are_a_distribution_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "LICENSE"
            original = b"Permissive original license\n"
            path.write_bytes(original)
            modules = {("example.org/reviewed", "v1.0.0"): (root, {path})}
            review = {"modules": [{"path": "example.org/reviewed", "version": "v1.0.0", "licenses": {"LICENSE": hashlib.sha256(original).hexdigest()}}]}
            validate_review(modules, review)
            path.write_bytes(b"Unreviewed terms\n")
            with self.assertRaises(ValueError):
                validate_review(modules, review)

    def test_symlink_license_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "LICENSE"
            target = root / "original"
            target.write_text("Original\n")
            try:
                path.symlink_to(target)
            except OSError:
                self.skipTest("symlink privilege unavailable on this host")
            review = {"modules": [{"path": "example.org/reviewed", "version": "v1.0.0", "licenses": {"LICENSE": hashlib.sha256(target.read_bytes()).hexdigest()}}]}
            with self.assertRaises(ValueError):
                validate_review({("example.org/reviewed", "v1.0.0"): (root, {path})}, review)

    def test_collects_linked_modules_and_go_license_without_duplicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            goroot = root / "go"
            goroot.mkdir()
            (goroot / "LICENSE").write_bytes(b"Go original license\n")
            project = root / "project"
            project.mkdir()
            (project / "LICENSE.sigstore").write_bytes(b"Trust anchor original license\n")
            module = root / "module"
            module.mkdir()
            (module / "LICENSE").write_bytes(b"Dependency original license\n")
            package = module / "pkg"
            package.mkdir()
            (package / "NOTICE").write_bytes(b"Nested package notice\n")
            meta = {"Path": "example.org/dep", "Version": "v1.2.3", "Dir": str(module)}
            packages = [{"Dir": str(package), "Module": meta}] * 2
            result = collect_notices(packages, goroot, project)
            self.assertIn("Go original license\n", result)
            self.assertIn("Trust anchor original license\n", result)
            self.assertIn("example.org/dep v1.2.3", result)
            self.assertEqual(result.count("Dependency original license\n"), 1)
            self.assertEqual(result.count("Nested package notice\n"), 1)


if __name__ == "__main__":
    unittest.main()
