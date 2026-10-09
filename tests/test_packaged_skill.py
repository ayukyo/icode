"""Fixed CP resources: real detached packaging, no installer or model calls."""

from __future__ import annotations

import json
import importlib.util
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import textwrap
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from tests._support import REPO_ROOT
from icode.config import Settings
from icode.control import ControlPlane
from icode import config


PIN = "21566a589cbe98bd35372a04bbb6ca1c51d8eed2"
TOOLS = ("icode_control.py", "inspection_worklist.py", "lint_thinking_gate.py",
         "lint_mcp_coverage.py", "lint_workflow_contract.py")


def candidate_paths():
    vendor = REPO_ROOT / "vendor/icode-skill"
    paths = ["SKILL.md", "LICENSE", *(f"tools/{p}" for p in TOOLS),
             *(f"mcp/{p}/gates.json" for p in
               ("workflow-gate", "reasoning-gate", "cheap-research"))]
    for directory in ("steps", "references", "schemas"):
        paths.extend(p.relative_to(vendor).as_posix()
                     for p in (vendor / directory).iterdir() if p.is_file())
    return sorted(paths)


def clean_environment(home):
    # A disposable HOME prevents a user's Skill/index from satisfying the test.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("ICODE_", "PYTHON", "PIP_"))}
    env.update(HOME=str(home), USERPROFILE=str(home), PYTHONDONTWRITEBYTECODE="1")
    return env


def run(argv, *, cwd, env=None):
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=180)


class TestPackagedSkillInstallation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="icode-skill-package-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.source = cls.root / "detached source"
        cls.source.mkdir()
        for name in ("setup.py", "pyproject.toml", "MANIFEST.in", "README.md", "LICENSE"):
            shutil.copyfile(REPO_ROOT / name, cls.source / name)
        for name in ("src", "native"):
            shutil.copytree(REPO_ROOT / name, cls.source / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        # A stale generated fixture header must not become source distribution
        # input. Production generation belongs only in the CMake build tree.
        (cls.source / "native/windows/icode_windows_verifier_binding.h").write_bytes(
            b"synthetic stale binding header, never package this\n")
        (cls.source / "scripts").mkdir()
        shutil.copyfile(REPO_ROOT / "scripts/windows_wheel.py",
                        cls.source / "scripts/windows_wheel.py")
        shutil.copyfile(REPO_ROOT / "scripts/windows_bootstrap_binding.py",
                        cls.source / "scripts/windows_bootstrap_binding.py")
        for path in candidate_paths():
            target = cls.source / "vendor/icode-skill" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / "vendor/icode-skill" / path, target)
        cls.env = clean_environment(cls.root / "home")
        (cls.root / "home").mkdir()
        cls.dist = cls.root / "dist"
        cls.dist.mkdir()
        # Use the already installed backend; never install build dependencies.
        built = run([sys.executable, "-B", "-c",
            "import setuptools;assert int(setuptools.__version__.split('.')[0])>=80;"
            "from setuptools.build_meta import build_wheel; import sys; "
            "build_wheel(sys.argv[1])", str(cls.dist)], cwd=cls.source, env=cls.env)
        if built.returncode:
            raise AssertionError(f"wheel build failed: {built.stderr[-1500:]}")
        cls.wheel = next(cls.dist.glob("*.whl"))
        cls.venv = cls.root / "venv"
        created = run([sys.executable, "-m", "venv", str(cls.venv)], cwd=cls.root)
        if created.returncode:
            raise AssertionError(created.stderr[-1000:])
        cls.python = cls.venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        installed = run([str(cls.python), "-m", "pip", "install", "--no-index",
                         "--no-deps", str(cls.wheel)], cwd=cls.root, env=cls.env)
        if installed.returncode:
            raise AssertionError(installed.stderr[-1000:])

    def installed(self, program, *, python=None):
        result = run([str(python or self.python), "-I", "-B", "-X", "utf8", "-c", textwrap.dedent(program)],
                     cwd=self.root, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr[-1600:])
        return result.stdout

    def test_installed_default_uses_package_not_checkout_or_user_skill(self):
        program = (
            "import icode,sys;from pathlib import Path;"
            "from icode.config import load_settings; s=load_settings();"
            "p=Path(icode.__file__).resolve().parent;"
            "assert p in s.skill_root.parents;"
            "assert s.python==sys.executable;assert s.exists();"
            "print('installed-package-default PASS')"
        )
        result = run([str(self.python), "-I", "-B", "-c", program],
                     cwd=self.root, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr[-1200:])
        self.assertIn("installed-package-default PASS", result.stdout)

    def test_wheel_contains_exact_original_closure_and_manifest_not_ppt_assets(self):
        with zipfile.ZipFile(self.wheel) as wheel:
            prefix = "icode/skill_runtime/"
            members = sorted(p[len(prefix):] for p in wheel.namelist() if p.startswith(prefix))
            self.assertEqual(members, candidate_paths())
            self.assertFalse(any(p.endswith((".pptx", "preview.png")) for p in wheel.namelist()))
            manifest = json.loads(wheel.read("icode/skill_runtime_manifest.json"))
            self.assertEqual(manifest["source"]["commit"], PIN)
            for member in manifest["members"]:
                raw = wheel.read(prefix + member["path"])
                self.assertEqual(raw, (REPO_ROOT / "vendor/icode-skill" / member["path"]).read_bytes())
                self.assertEqual(hashlib.sha256(raw).hexdigest(), member["sha256"])

    def test_detached_sdist_rebuild_has_identical_resource_bytes_without_git_or_vendor(self):
        built = run([sys.executable, "-B", "-c",
            "from setuptools.build_meta import build_sdist;import sys;build_sdist(sys.argv[1])",
            str(self.dist)], cwd=self.source, env=self.env)
        self.assertEqual(built.returncode, 0, built.stderr[-1200:])
        archive = next(self.dist.glob("*.tar.gz"))
        detached = self.root / "sdist rebuild"; detached.mkdir()
        with tarfile.open(archive) as package:
            names = package.getnames()
            self.assertEqual(sum(name.endswith("/scripts/windows_bootstrap_binding.py") for name in names), 1)
            self.assertFalse(any(name.endswith("/icode_windows_verifier_binding.h") for name in names))
            for member in package.getmembers():
                self.assertFalse(member.name.startswith("/") or ".." in Path(member.name).parts)
                self.assertTrue(member.isfile() or member.isdir())
                target = detached / member.name
                if member.isdir(): target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with package.extractfile(member) as stream:
                        target.write_bytes(stream.read())
        source = next(detached.iterdir())
        self.assertFalse((source / ".git").exists())
        self.assertFalse((source / "vendor").exists())
        from scripts.run_windows_wheel_ci import _synthetic_pe
        verifier = self.root / "detached synthetic verifier.exe"
        verifier.write_bytes(_synthetic_pe(0x8664))
        generated = self.root / "detached generated binding.h"
        generator = run([sys.executable, "-I", "-B",
            str(source / "scripts/windows_bootstrap_binding.py"), "--verifier", str(verifier),
            "--architecture", "x64", "--output", str(generated)], cwd=source, env=self.env)
        self.assertEqual(generator.returncode, 0, generator.stderr[-1200:])
        self.assertIn(hashlib.sha256(verifier.read_bytes()).hexdigest(), generated.read_text(encoding="ascii"))
        rebuilt_dist = self.root / "rebuilt dist"; rebuilt_dist.mkdir()
        rebuilt = run([sys.executable, "-B", "-c",
            "from setuptools.build_meta import build_wheel;import sys;build_wheel(sys.argv[1])",
            str(rebuilt_dist)], cwd=source, env=self.env)
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr[-1500:])
        with zipfile.ZipFile(self.wheel) as original, \
             zipfile.ZipFile(next(rebuilt_dist.glob("*.whl"))) as rebuilt_wheel:
            for name in original.namelist():
                if name.startswith("icode/skill_runtime/") or name == "icode/skill_runtime_manifest.json":
                    self.assertEqual(original.read(name), rebuilt_wheel.read(name))
        rebuilt_venv = self.root / "rebuilt venv"
        created = run([sys.executable, "-m", "venv", str(rebuilt_venv)], cwd=self.root)
        self.assertEqual(created.returncode, 0, created.stderr[-1000:])
        python = rebuilt_venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        installed = run([str(python), "-m", "pip", "install", "--no-index", "--no-deps",
                         str(next(rebuilt_dist.glob("*.whl")))], cwd=self.root, env=self.env)
        self.assertEqual(installed.returncode, 0, installed.stderr[-1000:])
        # Execute the same real consumers after the independent sdist install;
        # equal wheel bytes alone are not installed-runtime evidence.
        self._control_consumers(python=python)
        self._workbench_consumers(python=python)

    def test_installed_doctor_steps_handshake_and_three_strict_gates_without_path(self):
        self._control_consumers()

    def _control_consumers(self, *, python=None):
        output = self.installed('''
            import hashlib,json,os,runpy,shutil,subprocess,sys,tempfile
            from pathlib import Path
            from icode.config import load_settings
            from icode.control import ControlPlane
            from icode.handshake import next_out_dir,run_handshake
            s=load_settings()
            assert Path(sys.prefix).resolve() in s.skill_root.resolve().parents
            os.environ.pop('PYTHONDONTWRITEBYTECODE',None)
            # Only this disposable installed bundle is cleaned. pip may have
            # compiled its Python data members before the runtime observation.
            for cache in s.skill_root.rglob('__pycache__'):
                shutil.rmtree(cache)
            before={p.relative_to(s.skill_root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in s.skill_root.rglob('*') if p.is_file()}
            env=dict(os.environ,PATH='',LC_ALL='C',PYTHONUTF8='0',PYTHONCOERCECLOCALE='0')
            for command in ('doctor','steps'):
                result=subprocess.run([sys.executable,'-I','-B','-X','utf8','-m','icode.cli',command],
                    env=env,capture_output=True,encoding='utf-8',timeout=30)
                assert result.returncode==0,result.stderr
                if command=='doctor':
                    assert '不代表完整阶段验收' in result.stdout
                    assert '自动模式仍拒绝外部命令' in result.stdout
                else:assert 'review' in result.stdout
            os.environ.update(PATH='',LC_ALL='C',PYTHONUTF8='0',PYTHONCOERCECLOCALE='0')
            with tempfile.TemporaryDirectory() as raw:
                report=run_handshake(s,workspace=Path(raw).resolve(),step='plan')
                assert report.ok,report.render()
                assert report.advance.status=='blocked',report.render()
                cp=ControlPlane(s)
                rejected=cp.run('transition','--dir',report.out_dir,'--to','plan_done',
                                '--request-id','installed-strict-negative',check=False)
                assert rejected.data.get('fail_closed'),rejected.data
                gates=rejected.data.get('failed_gates')
                assert {g['gate_id'] for g in gates}=={'thinking_gate','workflow_contract'},gates
                assert all(isinstance(json.loads(g['detail']),dict) for g in gates),gates
                rows=runpy.run_path(str(s.control_script))['run_gate_linters'](
                    Path(report.out_dir),step='plan')
                assert {g['gate_id'] for g in rows}=={'thinking_gate','mcp_coverage','workflow_contract'},rows
                assert all(isinstance(g.get('report'),dict) and g['cmd'][0]==sys.executable
                           for g in rows),rows
                assert not all(g['ok'] for g in rows),rows
                assert cp.trace(report.out_dir).ok
            with tempfile.TemporaryDirectory() as raw:
                workspace=Path(raw).resolve()
                (workspace/'sample.py').write_bytes(b'def answer():\\n    return 42\\n')
                out_dir=next_out_dir(workspace)
                cp=ControlPlane(s)
                cp.create(out_dir,ticket_id='RESOURCE-IMPORT',requirement='Inspect resource import',
                    metadata_json=json.dumps({'code_files':['sample.py']}))
                # These are declared input bytes, not a finalized-plan receipt.
                # No state transition, thinking/audit pass or model is invented.
                (out_dir/'03_plan_final.md').write_bytes(b'# Resource inspection input fixture\\n')
                attempt=cp.step_start(out_dir,'audit',ticket_id='RESOURCE-IMPORT')
                checked=cp.step_check(out_dir,'audit',attempt,'before_write',ticket_id='RESOURCE-IMPORT')
                assert checked.data.get('result')=='pass',checked.data
                prepared=cp.run('inspection','--dir',str(out_dir),'--step','audit',
                    '--attempt',attempt,'--phase','prepare','--request','resource-prepare')
                assert prepared.ok and prepared.data.get('output')=='inspection_worklist',prepared.data
                worklist=json.loads((out_dir/'audit_worklist.json').read_bytes())
                assert worklist['code_files']==['sample.py'],worklist
                assert worklist['attempt']==attempt and worklist['units'],worklist
                # We imported/prepared a declaration, not Read or understood it.
                status=cp.run('inspection','--dir',str(out_dir),'--step','audit',
                    '--attempt',attempt,'--phase','check',check=False)
                assert not status.ok and status.data.get('violations'),status.data
                assert 'FileNotFoundError' not in str(status.data) and 'ModuleNotFoundError' not in str(status.data)
                finished=cp.step_finish(out_dir,'audit',attempt,'failure',ticket_id='RESOURCE-IMPORT',
                    evidence=['resource-import-only; no completed inspection'])
                assert finished.data.get('outcome')=='failure',finished.data
                trace=cp.trace(out_dir)
                assert trace.ok and trace.data.get('status')=='init_in_progress',trace.data
                assert trace.data.get('open_steps')=={},trace.data
            with tempfile.TemporaryDirectory() as raw:
                root=Path(raw).resolve()
                control=root/'control';control.mkdir()
                code=root/'代码 空间';code.mkdir()
                ticket=next_out_dir(control)
                cp=ControlPlane(s)
                cp.create(ticket,ticket_id='INSTALLED-BINDING',requirement='Separate code and control')
                before_binding=json.loads((ticket/'.ico_metadata.json').read_bytes())
                bound=cp.bind_execution_root(ticket,ticket_id='INSTALLED-BINDING',execution_root=code)
                assert bound.ok,bound.data
                events=(ticket/'.ico_events.jsonl').read_bytes()
                replay=cp.bind_execution_root(ticket,ticket_id='INSTALLED-BINDING',execution_root=code)
                assert replay.data.get('already_applied'),replay.data
                assert (ticket/'.ico_events.jsonl').read_bytes()==events
                metadata=json.loads((ticket/'.ico_metadata.json').read_bytes())
                assert metadata['project_path']==before_binding['project_path']==str(control)
                projected=cp.run('action-policy','--dir',str(ticket))
                assert projected.data['execution_root']==str(code),projected.data
                assert metadata['execution_binding']['path']==str(code),metadata
                code.rmdir()
                assert cp.trace(ticket).ok
                print('installed-execution-binding PASS')
            after={p.relative_to(s.skill_root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in s.skill_root.rglob('*') if p.is_file()}
            assert before==after,('runtime modified installed resources',sorted(set(after)-set(before)))
            print('installed-control-consumers PASS')
        ''', python=python)
        self.assertIn("installed-control-consumers PASS", output)
        self.assertIn("installed-execution-binding PASS", output)

    def test_installed_workbench_creates_lists_finds_both_locales(self):
        self._workbench_consumers()

    def _workbench_consumers(self, *, python=None):
        output = self.installed('''
            import json,tempfile,urllib.request
            from pathlib import Path
            from icode.config import load_settings
            from icode.workbench import WorkbenchServer
            with tempfile.TemporaryDirectory() as raw:
                workspace=Path(raw).resolve()
                server=WorkbenchServer(settings=load_settings(),workspace=workspace,
                                       index_path=workspace/'index.json')
                try:
                    url=server.start()
                    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(url,timeout=10) as response:
                        assert response.status==200
                        cookie=response.headers['Set-Cookie'].split(';')[0]
                    def request(path,payload=None):
                        data=None if payload is None else json.dumps(payload).encode('utf-8')
                        req=urllib.request.Request(url+path,data=data,
                            headers={'Cookie':cookie,'Content-Type':'application/json'})
                        with opener.open(req,timeout=10) as response:
                            return json.load(response)
                    bootstrap=request('api/v1/bootstrap')
                    assert not bootstrap['capabilities']['autonomous']['enabled']
                    project=bootstrap['projects'][0]['project_id']
                    ids=[]
                    for locale in ('zh-CN','en-US'):
                        created=request('api/v1/tickets',{
                            'project_id':project,'title':'安装测试 '+locale,
                            'description':'真实控制面建单','expected_result':'可查找',
                            'priority':'normal','locale':locale,'execution_mode':'interactive',
                            'request_id':'installed-'+locale})
                        assert created['ok'],created
                        ticket=created['ticket'];ids.append(ticket['ticket_id'])
                        assert ticket['locale']==locale,ticket
                        detail=request('api/v1/tickets/'+ticket['ticket_id'])
                        assert detail['ticket']['ticket_id']==ticket['ticket_id']
                    listed=request('api/v1/tickets')
                    assert {t['ticket_id'] for t in listed['tickets']}==set(ids),listed
                    found=request('api/v1/tickets?query=en-US')
                    assert len(found['tickets'])==1,found
                    assert found['tickets'][0]['locale']=='en-US'
                finally:server.stop()
            print('installed-workbench PASS')
        ''', python=python)
        self.assertIn("installed-workbench PASS", output)

    def test_installed_missing_or_changed_bundle_cannot_use_valid_home_skill(self):
        output = self.installed('''
            import os,shutil
            from pathlib import Path
            from icode.config import ConfigError,load_settings
            s=load_settings();root=s.skill_root
            home=Path.home()/'icode-skill';shutil.copytree(root,home)
            member=root/'LICENSE';original=member.read_bytes()
            try:
                member.write_bytes(b'changed')
                try:load_settings()
                except ConfigError as error:assert '随包' in str(error)
                else:raise AssertionError('corruption fell back to HOME')
                member.unlink()
                try:load_settings()
                except ConfigError:pass
                else:raise AssertionError('missing member fell back to HOME')
            finally:member.write_bytes(original)
            hidden=root.with_name('resource-hidden');root.rename(hidden)
            try:
                try:load_settings()
                except ConfigError:pass
                else:raise AssertionError('missing bundle fell back to HOME')
            finally:hidden.rename(root)
            assert load_settings().skill_root==root
            print('installed-fail-closed PASS')
        ''')
        self.assertIn("installed-fail-closed PASS", output)


class TestPackagedSkillControlRuntime(unittest.TestCase):
    def test_outer_control_keeps_chinese_failure_json_in_c_locale(self):
        with tempfile.TemporaryDirectory(prefix="icode-cp-runtime-") as temporary:
            missing = Path(temporary) / "不存在 中文"
            settings = Settings(REPO_ROOT / "vendor/icode-skill")
            with patch.dict(os.environ, LC_ALL="C", PYTHONUTF8="0", PYTHONCOERCECLOCALE="0"):
                result = ControlPlane(settings).run("trace", "--dir", str(missing), check=False)
            self.assertIs(result.data.get("ok"), False, result.data)
            self.assertIn("error", result.data)


class TestFixedSkillResources(unittest.TestCase):
    def resources(self):
        spec = importlib.util.find_spec("icode.skill_resources")
        self.assertIsNotNone(spec, "fixed resource validator has not been implemented")
        from icode import skill_resources
        return skill_resources

    def fixture(self, root):
        for path in candidate_paths():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / "vendor/icode-skill" / path, target)

    def test_fixed_manifest_exact_pin_members_and_original_hashes(self):
        module = self.resources()
        manifest = module.read_manifest()
        self.assertEqual(manifest["source"]["commit"], PIN)
        self.assertEqual(manifest["source"]["license"], "MIT")
        self.assertEqual([m["path"] for m in manifest["members"]], candidate_paths())
        self.assertEqual(len(manifest["members"]), 72)
        self.assertEqual(sum(m["size"] for m in manifest["members"]), 1947268)
        for member in manifest["members"]:
            raw = (REPO_ROOT / "vendor/icode-skill" / member["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), member["sha256"])
        module.verify_resources(REPO_ROOT / "vendor/icode-skill")

    def test_manifest_duplicate_json_keys_and_oversize_rejected(self):
        module = self.resources()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            for raw in (b'{"schema_version":1,"schema_version":1}', b" " * 65537):
                path.write_bytes(raw)
                with self.assertRaises(module.SkillResourceError):
                    module.read_manifest(path)

    def test_manifest_unsafe_and_duplicate_members_rejected(self):
        module = self.resources()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            for unsafe in ("../outside", "/outside", "C:/outside", "tools\\outside", "./LICENSE"):
                data = module.read_manifest()
                data["members"][0]["path"] = unsafe
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(module.SkillResourceError):
                    module.read_manifest(path)
            data = module.read_manifest()
            data["members"][1] = data["members"][0]
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(module.SkillResourceError):
                module.read_manifest(path)

    def test_manifest_changed_pin_hash_size_or_unknown_fields_rejected(self):
        module = self.resources()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            for mutate in (lambda d: d["source"].update(commit="0" * 40),
                           lambda d: d["members"][0].update(sha256="0" * 64),
                           lambda d: d["members"][0].update(size=True),
                           lambda d: d.update(extra=True)):
                data = module.read_manifest(); mutate(data)
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(module.SkillResourceError):
                    module.read_manifest(path)

    def test_missing_and_hash_mismatched_resource_rejected(self):
        module = self.resources()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); self.fixture(root)
            (root / "LICENSE").write_bytes(b"changed")
            with self.assertRaises(module.SkillResourceError): module.verify_resources(root)
            (root / "LICENSE").unlink()
            with self.assertRaises(module.SkillResourceError): module.verify_resources(root)

    def test_resource_and_directory_symlinks_rejected_without_reading_outside(self):
        module = self.resources()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(); root = base / "resources"; root.mkdir()
            self.fixture(root)
            outside = base / "original-license"
            outside.write_bytes((root / "LICENSE").read_bytes())
            (root / "LICENSE").unlink()
            try: (root / "LICENSE").symlink_to(outside)
            except OSError: self.skipTest("symlink privilege unavailable; no conformance credit")
            with self.assertRaises(module.SkillResourceError): module.verify_resources(root)
            alias = base / "alias"; alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(module.SkillResourceError): module.verify_resources(alias)
            self.assertEqual(outside.read_bytes(), (REPO_ROOT / "vendor/icode-skill/LICENSE").read_bytes())
            (root / "LICENSE").unlink(); shutil.copyfile(outside, root / "LICENSE")
            (root / "tools").rename(base / "outside-tools")
            (root / "tools").symlink_to(base / "outside-tools", target_is_directory=True)
            with self.assertRaises(module.SkillResourceError): module.verify_resources(root)

    def test_staging_preserves_bytes_and_rejects_stale_extra_members(self):
        module = self.resources()
        with tempfile.TemporaryDirectory() as temporary:
            dest = Path(temporary).resolve() / "stage"
            module.stage_resources(REPO_ROOT / "vendor/icode-skill", dest)
            module.verify_resources(dest)
            self.assertEqual(sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()), candidate_paths())
            (dest / "forbidden.pptx").write_bytes(b"must not ship")
            with self.assertRaises(module.SkillResourceError):
                module.stage_resources(REPO_ROOT / "vendor/icode-skill", dest)

    def test_staging_symlink_destination_cannot_write_outside(self):
        module = self.resources()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(); outside = base / "outside"; outside.mkdir()
            dest = base / "alias"
            try: dest.symlink_to(outside, target_is_directory=True)
            except OSError: self.skipTest("symlink privilege unavailable; no conformance credit")
            with self.assertRaises(module.SkillResourceError):
                module.stage_resources(REPO_ROOT / "vendor/icode-skill", dest)
            self.assertEqual(list(outside.iterdir()), [])

    def test_staging_does_not_overwrite_an_outside_hardlink(self):
        module = self.resources()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(); dest = base / "stage"
            module.stage_resources(REPO_ROOT / "vendor/icode-skill", dest)
            outside = base / "outside-license"; outside.write_bytes(b"user file")
            (dest / "LICENSE").unlink()
            os.link(outside, dest / "LICENSE")
            module.stage_resources(REPO_ROOT / "vendor/icode-skill", dest)
            self.assertEqual(outside.read_bytes(), b"user file")
            module.verify_resources(dest)

    def test_installed_corruption_never_falls_back_to_home(self):
        module = self.resources()
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary).resolve() / "icode"; package.mkdir()
            shutil.copyfile(REPO_ROOT / "src/icode/skill_runtime_manifest.json",
                            package / "skill_runtime_manifest.json")
            root = package / "skill_runtime"; root.mkdir(); self.fixture(root)
            (root / "LICENSE").write_bytes(b"bad")
            # Only filesystem discovery is redirected; real validator runs.
            with patch.object(module, "PACKAGE_DIR", package), \
                 patch.object(config, "repo_root", return_value=package.parent), \
                 patch.object(config, "_load_local_config", return_value={}), \
                 patch.dict(os.environ, {"ICODE_SKILL_ROOT": ""}):
                with self.assertRaisesRegex(config.ConfigError, "随包"):
                    config.find_skill_root()

    def test_explicit_environment_and_local_sources_remain_advanced_overrides(self):
        self.resources()
        source = REPO_ROOT / "vendor/icode-skill"
        self.assertEqual(config.find_skill_root(source), source.resolve())
        with patch.dict(os.environ, ICODE_SKILL_ROOT=str(source)):
            self.assertEqual(config.find_skill_root(), source.resolve())
        with patch.dict(os.environ, ICODE_SKILL_ROOT=""), \
             patch.object(config, "_load_local_config", return_value={"skill_root": str(source)}):
            self.assertEqual(config.find_skill_root(), source.resolve())


if __name__ == "__main__":
    unittest.main()
