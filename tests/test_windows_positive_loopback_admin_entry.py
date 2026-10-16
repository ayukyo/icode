"""Real fixed entry.main control flow; modeled privileged consumers only."""
from __future__ import annotations
import importlib
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from tests.test_windows_positive_loopback_admin_binding import identity

NAME="scripts.windows_positive_loopback_admin_entry"
try:
    entry=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name!=NAME:raise
    entry=None


class Consumer:
    def __init__(self):
        self.events=[];self.fail_close=False;self.fail_cleanup=False;self.wait=0
        self.receipt={"stage":"cleaned","binding":"b"*64,"native_restoration_verified":True};self.first_error=None
        self.data={"phase":"prepared","parent":{"pid":1234,"process_created":5678}}
        self.snapshots=[self.snapshot(),self.snapshot()]
        self.store=N(w=N(k=N(WaitForSingleObject=self.wait_parent),close=self.close_handle),close=self.close_store)
        self.native=N(full_get=self.full_get,stop_parent_job=self.stop,reap_commands=self.reap,_process=self.process)
    @staticmethod
    def snapshot():
        return dict(schema=1,entries=[["S-1-15-2-99",7]],api_code=0,complete=True,
            sid_attempted=1,sid_freed=1,array_freed=True,library_freed=True,process_reaped=True)
    def attach_parent(self,pid):
        if pid!=1234:raise RuntimeError("wrong modeled parent")
        self.events.append("attach");self.data["phase"]="bound"
    def serve(self):self.events.append("serve");self.data["phase"]="cleaned";return dict(self.receipt)
    def cleanup(self,*,abnormal):
        self.events.append(("cleanup",abnormal))
        if self.fail_cleanup:raise RuntimeError("modeled cleanup failed")
        self.data["phase"]="cleaned"
    def _failure(self,error):self.first_error=self.first_error or error;self.events.append(("failure",error))
    def full_get(self,store):self.events.append("get");return self.snapshots.pop(0)
    def stop(self,store):self.events.append("stop_parent")
    def reap(self,store):self.events.append("reap_commands")
    def process(self,store,identity,*,allow_gone=False):self.events.append("held_parent");return 50
    def wait_parent(self,handle,milliseconds):self.events.append(("wait_parent",milliseconds));return self.wait
    def close_handle(self,handle):self.events.append(("close_handle",handle))
    def close_store(self):
        self.events.append("close_store")
        if self.fail_close:raise RuntimeError("modeled CloseHandle failed")


class TestAdminEntry(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(entry,"new fixed entry absent; expected facility RED")
        self.admin_module=importlib.import_module("scripts.windows_positive_loopback_admin")
        self.flags=N(isolated=1,no_site=1,dont_write_bytecode=1)
        self.root=Path(tempfile.gettempdir()).resolve(strict=True)/("icode-positive-admin-"+"1"*32);self.consumer=Consumer()
        b=identity()
        self.env=dict(GITHUB_ACTIONS="true",RUNNER_ENVIRONMENT="github-hosted",RUNNER_OS="Windows",
            GITHUB_REPOSITORY=b["repository"],GITHUB_SHA=b["source_sha"],GITHUB_RUN_ID=b["run_id"],
            GITHUB_RUN_ATTEMPT=str(b["run_attempt"]),GITHUB_JOB=b["job"],RUNNER_ARCH="X64",
            GITHUB_REF="refs/heads/main",GITHUB_WORKFLOW_REF="ayukyo/icode/.github/workflows/ci.yml@refs/heads/main",
            GITHUB_WORKFLOW_SHA=b["source_sha"],ICODE_CI_POSITIVE_LOOPBACK_ADMIN="1",
            ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER="1")
        test=self
        class AdminBoundary:
            @classmethod
            def freeze_before_user(cls,context,account):
                test.consumer.events.append(("freeze",account,context));return test.root
            @classmethod
            def prepare(cls,root,sid):
                if root!=test.root or sid!=b["account_sid"]:raise RuntimeError("modeled binding")
                test.consumer.events.append("prepare");return test.consumer
            @classmethod
            def recover(cls,root):
                if root!=test.root:raise RuntimeError("modeled recovery binding")
                test.consumer.events.append("recover");return dict(test.consumer.receipt)
        local_sys=N(platform="win32",version_info=(3,12,10),flags=self.flags,
            executable=str(self.root/"runtime/python.exe"),path=list(entry.sys.path),stdout=entry.sys.stdout,
            exception=entry.sys.exception)
        self.patches=[patch.object(self.admin_module,"Admin",AdminBoundary),patch.dict(entry.os.environ,self.env,clear=True),
            patch.object(entry,"sys",local_sys),
            patch.object(entry,"__file__",str(self.root/"trusted/scripts/windows_positive_loopback_admin_entry.py")),
            patch.object(Path,"resolve",lambda path,*args,**options:path)]
        for item in self.patches:item.start();self.addCleanup(item.stop)
        self.output=b""
    def invoke(self,argv):
        stream=N(buffer=io.BytesIO())
        try:
            with patch.object(entry.sys,"stdout",stream):return entry.main(argv)
        finally:self.output=stream.buffer.getvalue()
    def args(self,kind):
        result=[kind,"--root",str(self.root)]
        if kind in ("serve","readonly"):result += ["--account-sid",identity()["account_sid"],"--parent","1234"]
        return result
    def wrong_flags(self,**changed):return N(**{**vars(self.flags),**changed})

    def test_entry_actual_main_body_survives_parent_cleanup_and_store_close_failures(self):
        for owner in ("cleanup","store_close","parent_handle"):
            with self.subTest(owner=owner):
                self.consumer=Consumer();body=RuntimeError("modeled_entry_body")
                def fault(*args,**options):raise body
                def cleanup_fault(*args,**options):
                    self.consumer.events.append("cleanup_attempt");raise RuntimeError("modeled_entry_cleanup")
                def close_fault(*args):
                    self.consumer.events.append("close_attempt");raise RuntimeError("modeled_entry_close")
                if owner=="parent_handle":
                    self.consumer.store.w.k.WaitForSingleObject=fault
                    self.consumer.store.w.close=close_fault
                    operation="serve"
                else:
                    self.consumer.native.full_get=fault;operation="readonly"
                    if owner=="cleanup":self.consumer.cleanup=cleanup_fault
                    else:self.consumer.store.close=close_fault
                with self.assertRaises(RuntimeError) as caught:self.invoke(self.args(operation))
                self.assertIs(caught.exception,body)
                self.assertTrue("close_store" in self.consumer.events or "close_attempt" in self.consumer.events)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_freeze_only_from_original_checkout_before_private_restart(self):
        with patch.object(entry,"__file__","/model/checkout/scripts/windows_positive_loopback_admin_entry.py"):
            self.assertEqual(self.invoke(["freeze","--account","icodeprobe_a"]),0)
        self.assertEqual(json.loads(self.output)["stage"],"frozen")
        self.assertEqual(self.consumer.events[0][:2],("freeze","icodeprobe_a"))
        self.consumer.events.clear()
        with self.assertRaises(RuntimeError):self.invoke(["freeze","--account","icodeprobe_a"])
        self.assertEqual(self.consumer.events,[])

    def test_private_arguments_cross_root_wrong_python_and_client_handle_refuse(self):
        for argv in (["readonly","--root","/other","--account-sid",identity()["account_sid"],"--parent","1234"],
            ["recover","--root",str(self.root),"--parent","1234"],
            ["serve","--root",str(self.root)],self.args("serve")+["--handle","99"]):
            with self.subTest(argv=argv),self.assertRaises((RuntimeError,SystemExit)):self.invoke(argv)
        with patch.object(entry.sys,"executable","/external/python.exe"):
            with self.assertRaises(RuntimeError):self.invoke(self.args("readonly"))
        self.assertEqual(self.consumer.events,[])

    def test_platform_python_flags_and_unknown_operation_refuse(self):
        for key,value in (("platform","linux"),("version_info",(3,11,17)),
                ("flags",self.wrong_flags(isolated=0)),
                ("flags",self.wrong_flags(no_site=0)),
                ("flags",self.wrong_flags(dont_write_bytecode=0))):
            with patch.object(entry.sys,key,value):
                with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):self.invoke(self.args("readonly"))
        with self.assertRaises(SystemExit):self.invoke(["arbitrary-command"])
        self.assertEqual(self.consumer.events,[])

    def test_readonly_success_requires_complete_configuration_and_cleanup_close(self):
        self.assertEqual(self.invoke(self.args("readonly")),0)
        self.assertEqual(json.loads(self.output)["stage"],"readonly_ready")
        self.assertEqual(self.consumer.events,["prepare","attach","get","stop_parent","get",("cleanup",True),"close_store"])

    def test_readonly_configuration_delta_emits_no_ready_and_still_cleans(self):
        self.consumer.snapshots[1]["entries"][0][1]=8
        with self.assertRaises(RuntimeError):self.invoke(self.args("readonly"))
        self.assertEqual(self.output,b"")
        self.assertIn(("cleanup",True),self.consumer.events)
        self.assertEqual(self.consumer.events[-1],"close_store")

    def test_readonly_emitted_line_cannot_override_finally_failure(self):
        for failure in ("fail_cleanup","fail_close"):
            self.consumer=Consumer();setattr(self.consumer,failure,True)
            with self.subTest(failure=failure),self.assertRaises(RuntimeError):self.invoke(self.args("readonly"))
            self.assertEqual(json.loads(self.output)["stage"],"readonly_ready")
            self.assertEqual(self.consumer.events[-1],"close_store")
            # There was no successful main return/exit0: stdout alone grants nothing.

    def test_serve_waits_for_original_parent_finally_before_closing_owned_job(self):
        self.assertEqual(self.invoke(self.args("serve")),0)
        self.assertEqual(json.loads(self.output)["stage"],"completed")
        wait=self.consumer.events.index(("wait_parent",30000))
        self.assertLess(wait,self.consumer.events.index("close_store"))
        self.assertIn(("close_handle",50),self.consumer.events)
        self.assertNotIn("stop_parent",self.consumer.events)

    def test_serve_parent_finally_timeout_stops_and_refuses_completed(self):
        self.consumer.wait=258
        with self.assertRaises(RuntimeError):self.invoke(self.args("serve"))
        self.assertEqual(self.output,b"")
        self.assertEqual(self.consumer.first_error,"parent_failed")
        self.assertLess(self.consumer.events.index(("wait_parent",30000)),self.consumer.events.index("stop_parent"))
        self.assertEqual(self.consumer.events[-1],"close_store")

    def test_failure_receipt_reports_bounded_stage_and_never_details(self):
        for message,expected in (("entry_freeze_arguments","entry_freeze_arguments"),
            ("readonly_configuration_changed","readonly_configuration_changed"),
            ("create_directory","create_directory"),("","unknown"),("unknown","unknown"),
            ("C:\\Users\\runneradmin\\AppData\\Local\\Temp\\icode-positive-admin-x","unknown"),
            ("S-1-5-32-544","unknown"),("aA1!secret","unknown"),
            ("d6a7a3abbd2c2b29730d8ccc2d1a1c9f5a1c30fd","unknown"),
            ("gate_ledger_binding "+"x"*60,"unknown")):
            with self.subTest(message=message):
                self.assertEqual(entry.bounded_stage(RuntimeError(message)),expected)
        self.assertEqual(entry.failure_receipt(RuntimeError("entry_freeze_arguments")),
            dict(schema=1,stage="failed",state="unknown",error="entry_freeze_arguments"))
        self.assertEqual(entry.failure_receipt(FileNotFoundError(2,"C:\\a\\icode\\icode\\x.py")),
            dict(schema=1,stage="failed",state="unknown",error="unknown"))

    def test_recover_uses_only_exact_trusted_root_and_result_status(self):
        self.assertEqual(self.invoke(self.args("recover")),0)
        self.assertEqual(self.consumer.events,["recover"])
        self.consumer.receipt["native_restoration_verified"]=None
        self.assertEqual(self.invoke(self.args("recover")),4)
        self.assertEqual(json.loads(self.output)["stage"],"recovery")


if __name__=="__main__":unittest.main()
