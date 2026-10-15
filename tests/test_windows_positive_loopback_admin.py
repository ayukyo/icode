"""Real coordinator over durable stateful model; no Windows authority."""
from __future__ import annotations
import copy
from dataclasses import asdict
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from icode import windows_positive_loopback_policy as policy
from tests.test_windows_positive_loopback_admin_binding import identity, manifest

NAME="scripts.windows_positive_loopback_admin"
try:
    admin=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name != NAME: raise
    admin=None


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")


class ModelStore:
    def __init__(self, model):
        self.model=model
        self.data=dict(phase="prepared",session=model.boot["session"],first_error=None,
            cleanup_error=None,owned_intent=False,observations={},target_attributes=None)
        self.durable=b""
        self.closed=False
        self.flush()

    def flush(self):
        if self.model.fail_flush:
            raise RuntimeError("modeled flush failure")
        self.durable=canonical(self.data)
        self.model.events.append(("flush",json.loads(self.durable)))

    def close(self):
        self.closed=True


class ModelNative:
    def __init__(self):
        self.boot=identity(); self.clock=180999; self.op=None
        self.events=[]; self.fail_flush=False; self.fail_get=False
        self.fail_delete=False; self.unreaped=False; self.parent_alive=True
        self.parent_pids=(1234,); self.created_consumed=False; self.finished_consumed=False
        self.foreign="S-1-15-2-99"; self.config={self.foreign:0x80000004}
        self.results={"add":dict(pid=11,process_created=12,exit_code=0,timed_out=False,reaped=True),
            "delete":dict(pid=13,process_created=14,exit_code=0,timed_out=False,reaped=True)}
        self.store=ModelStore(self); self.closed=False

    def freeze(self, context, account):
        self.events.append(("freeze",context,account)); return Path("/model/admin")
    def prepare(self, root, account_sid):
        if root!=Path("/model/admin") or account_sid!=self.boot["account_sid"]:
            raise RuntimeError("modeled identity mismatch")
        return self.store
    def reopen(self, root):
        if root!=Path("/model/admin"): raise RuntimeError("modeled wrong root")
        self.store.data=json.loads(self.store.durable)
        return self.store
    def verify_store(self, store):
        if store is not self.store or not store.durable: raise RuntimeError("bad store")
    def attach_parent(self, store, pid):
        if pid!=self.boot["pid"]: raise RuntimeError("wrong pid")
        self.events.append(("attach",pid))
    def publish_manifest(self, store): self.events.append(("bootstrap_published",))
    def bootstrap(self, store): return copy.deepcopy(self.boot)
    def manifest(self, store):
        if self.op is None: raise RuntimeError("no operation")
        return self.op
    def freeze_operation(self, store):
        if self.op is not None: raise RuntimeError("operation already frozen")
        self.op=manifest(self.boot,self.clock); self.events.append(("operation",self.op.digest))
        return self.op
    def now_ms(self): return self.clock
    def verify_parent(self, store):
        if not self.parent_alive: raise RuntimeError("parent exited")
    def consume_request(self, store, kind):
        attribute="created_consumed" if kind=="profile_created" else "finished_consumed"
        if getattr(self,attribute): raise RuntimeError("consumed")
        setattr(self,attribute,True)
        self.events.append(("consume",kind))
        return (admin.encode_bootstrap_request(self.boot) if kind=="profile_created" else
                admin.encode_operation_request(self.op,self.boot["session"]))
    def full_get(self, store):
        if self.fail_get: raise RuntimeError("modeled Get failure")
        rows=[[sid,value] for sid,value in self.config.items()]
        return dict(schema=1,entries=rows,api_code=0,complete=True,
            sid_attempted=len(rows),sid_freed=len(rows),array_freed=True,
            library_freed=True,process_reaped=True)
    def command(self, store, op):
        saved=json.loads(store.durable)
        if not saved["owned_intent"] or saved["phase"] not in ("add_intent","cleanup_intent"):
            raise AssertionError("command before persisted intent")
        self.events.append(("command",op,copy.deepcopy(saved)))
        if op=="add": self.config[self.boot["positive_sid"]]=7
        elif op=="delete" and not self.fail_delete: self.config.pop(self.boot["positive_sid"],None)
        else:
            if op!="delete": raise AssertionError("nonfixed operation")
        result=copy.deepcopy(self.results[op]); self.unreaped=not result["reaped"]
        return result
    def parent_only(self, store):
        return self.parent_alive and self.parent_pids==(self.boot["pid"],)
    def reap_commands(self, store):
        if self.unreaped: raise RuntimeError("late add may still write")
        self.events.append(("commands_reaped",))
    def has_add_attempt(self, store):
        return any(event[:2]==("command","add") for event in self.events)
    def stop_parent_job(self, store):
        self.parent_pids=(); self.parent_alive=False; self.events.append(("outer_empty",))
    def publish(self, store, kind, data):
        self.events.append(("receipt",kind,copy.deepcopy(data))); return copy.deepcopy(data)
    def wait_request(self, store, kind, timeout_ms):
        self.events.append(("wait",kind,timeout_ms))


class TestAdminCoordinator(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(admin,"new admin coordinator absent; expected facility RED")
        self.model=ModelNative()
        self.patch=patch.object(admin,"Native",lambda: self.model); self.patch.start()
        self.addCleanup(self.patch.stop)
        root=admin.Admin.freeze_before_user({"candidate":"model"},"temporary-model")
        self.controller=admin.Admin.prepare(root,self.model.boot["account_sid"])
        self.controller.attach_parent(self.model.boot["pid"])

    def added(self):
        self.controller.created()
        self.assertIn(self.model.boot["positive_sid"],self.model.config)
        return self.controller

    def commands(self):
        return [event[1] for event in self.model.events if event[0]=="command"]

    def test_normal_nonempty_foreign_configuration_exactly_restored_and_intent_precedes_add(self):
        before=dict(self.model.config); self.added()
        receipt=self.controller.finished()
        self.assertEqual(self.model.config,before)
        self.assertEqual(self.commands(),["add","delete"])
        self.assertTrue(receipt["native_restoration_verified"])
        self.assertEqual(receipt["domain"],"icode_positive_operation_v1")
        command=next(event for event in self.model.events if event[:2]==("command","add"))
        self.assertEqual(command[2]["phase"],"add_intent")
        self.assertEqual(command[2]["observations"]["baseline"]["entries"],
                         [[self.model.foreign,0x80000004]])

    def test_preexisting_positive_or_reviewer_is_never_deleted_or_taken_over(self):
        for key in ("positive_sid","reviewer_sid"):
            self.setUpModelForSubcase()
            sid=self.model.boot[key]; self.model.config[sid]=0xabcdef01
            before=dict(self.model.config)
            with self.assertRaises(admin.AdminError): self.controller.created()
            receipt=self.controller.cleanup(abnormal=True)
            self.assertEqual(self.model.config,before); self.assertEqual(self.commands(),[])
            self.assertEqual(receipt["stage"],"not_owned")
            self.assertIsNone(receipt["native_restoration_verified"])

    def setUpModelForSubcase(self):
        self.model=ModelNative()
        self.controller=admin.Admin.prepare(Path("/model/admin"),self.model.boot["account_sid"])
        self.controller.attach_parent(self.model.boot["pid"])

    def test_durable_flush_failure_prevents_any_add(self):
        self.model.fail_flush=True
        with self.assertRaises(Exception): self.controller.created()
        self.assertEqual(self.commands(),[])
        self.assertNotIn(self.model.boot["positive_sid"],self.model.config)

    def test_unstable_baseline_and_incomplete_get_never_add(self):
        first=self.model.full_get(self.model.store)
        second=copy.deepcopy(first); second["entries"][0][1]=9
        with patch.object(self.model,"full_get",side_effect=[first,second]):
            with self.assertRaises(admin.AdminError): self.controller.created()
        self.assertEqual(self.commands(),[])
        self.assertEqual(self.controller.data["first_error"],"baseline_delta")
        self.setUpModelForSubcase(); self.model.fail_get=True
        with self.assertRaises(admin.AdminError): self.controller.created()
        self.assertEqual(self.commands(),[])
        self.assertEqual(self.controller.data["first_error"],"get_failed")

    def test_consumed_session_cannot_issue_second_add_or_delete(self):
        self.added()
        with self.assertRaises(admin.AdminError): self.controller.created()
        self.controller.finished()
        with self.assertRaises(admin.AdminError): self.controller.finished()
        self.assertEqual(self.commands(),["add","delete"])

    def test_add_failure_after_write_keeps_first_error_and_still_owned_cleanup(self):
        self.model.results["add"]["exit_code"]=5
        with self.assertRaises(admin.AdminError): self.controller.created()
        self.assertEqual(self.controller.data["first_error"],"add_failed")
        receipt=self.controller.cleanup(abnormal=True)
        self.assertNotIn(self.model.boot["positive_sid"],self.model.config)
        self.assertFalse(receipt["native_restoration_verified"])
        self.assertEqual(self.controller.data["first_error"],"add_failed")

    def test_unreaped_late_add_blocks_delete_until_recovery_observes_exit(self):
        self.model.results["add"]["reaped"]=False
        with self.assertRaises(admin.AdminError): self.controller.created()
        with self.assertRaises(admin.AdminError): self.controller.cleanup(abnormal=True)
        self.assertEqual(self.commands(),["add"])
        self.assertIn(self.model.boot["positive_sid"],self.model.config)
        self.model.unreaped=False
        admin.Admin.recover(Path("/model/admin"))
        self.assertEqual(self.commands(),["add","delete"])
        self.assertNotIn(self.model.boot["positive_sid"],self.model.config)
        self.assertTrue(self.model.store.closed)

    def test_foreign_change_preserved_owned_target_removed_but_restore_unknown(self):
        self.added(); self.model.config[self.model.foreign]=0xdeadbeef
        self.model.config["S-1-15-2-100"]=0x80000001
        receipt=self.controller.cleanup(abnormal=True)
        self.assertEqual(self.model.config,{self.model.foreign:0xdeadbeef,
                                           "S-1-15-2-100":0x80000001})
        self.assertFalse(receipt["native_restoration_verified"])
        self.assertEqual(self.controller.data["first_error"],"foreign_delta")

    def test_target_attribute_conflict_refuses_delete(self):
        self.added(); self.model.config[self.model.boot["positive_sid"]]=8
        with self.assertRaises(admin.AdminError): self.controller.cleanup(abnormal=True)
        self.assertEqual(self.commands(),["add"])
        self.assertEqual(self.controller.data["first_error"],"owner_conflict")
        self.assertEqual(self.model.config[self.model.boot["positive_sid"]],8)

    def test_owned_intent_without_actual_add_attempt_cannot_adopt_later_target(self):
        self.model.op=manifest(self.model.boot,self.model.clock)
        self.controller.data.update(phase="add_intent",owned_intent=True)
        self.controller.data["observations"]["baseline"]=self.model.full_get(self.model.store)
        self.controller.store.flush()
        self.model.config[self.model.boot["positive_sid"]]=7
        with self.assertRaises(admin.AdminError):self.controller.cleanup(abnormal=True)
        self.assertEqual(self.commands(),[])
        self.assertEqual(self.controller.data["first_error"],"owner_conflict")
        self.assertEqual(self.model.config[self.model.boot["positive_sid"]],7)

    def test_deadline_cleanup_removes_target_without_success_credit(self):
        self.added(); self.model.clock=self.model.op.deadline_ms
        receipt=self.controller.cleanup(abnormal=True)
        self.assertNotIn(self.model.boot["positive_sid"],self.model.config)
        self.assertFalse(receipt["native_restoration_verified"])
        self.assertEqual(self.controller.data["first_error"],"deadline")

    def test_extra_job_member_causes_abnormal_stop_before_delete(self):
        self.added(); self.model.parent_pids=(1234,4321)
        with self.assertRaises(admin.AdminError): self.controller.finished()
        self.assertEqual(self.model.parent_pids,())
        events=[event[0] for event in self.model.events]
        stop=events.index("outer_empty")
        deletion=next(i for i,event in enumerate(self.model.events) if event[:2]==("command","delete"))
        self.assertLess(stop,deletion)
        self.assertEqual(self.controller.data["first_error"],"parent_failed")

    def test_cleanup_failure_retains_operation_first_error_and_ledger(self):
        self.model.results["add"]["exit_code"]=5
        with self.assertRaises(admin.AdminError): self.controller.created()
        self.model.fail_delete=True
        with self.assertRaises(admin.AdminError): self.controller.cleanup(abnormal=True)
        saved=json.loads(self.model.store.durable)
        self.assertEqual(saved["first_error"],"add_failed")
        self.assertEqual(saved["cleanup_error"],"cleanup_failed")
        self.assertTrue(saved["owned_intent"])

    def test_serve_wait_freeze_and_publish_failures_are_durable_non_success(self):
        for boundary in ("first_wait","second_wait","freeze_operation","publish_add"):
            with self.subTest(boundary=boundary):
                self.setUpModelForSubcase()
                original_publish=self.model.publish
                def wait(store,kind,timeout_ms):
                    if boundary==("first_wait" if kind=="profile_created" else "second_wait"):
                        raise RuntimeError("modeled request IO failure")
                def publish(store,kind,value):
                    if boundary=="publish_add" and kind=="add":raise RuntimeError("modeled publication failure")
                    return original_publish(store,kind,value)
                stack=[patch.object(self.model,"wait_request",wait),patch.object(self.model,"publish",publish)]
                if boundary=="freeze_operation":
                    stack.append(patch.object(self.model,"freeze_operation",side_effect=RuntimeError("modeled freeze failure")))
                for item in stack:item.start()
                try:
                    with self.assertRaises(Exception):self.controller.serve()
                finally:
                    for item in reversed(stack):item.stop()
                saved=json.loads(self.model.store.durable)
                self.assertIsNotNone(saved["first_error"],"serve boundary error must precede cleanup success")
                self.assertFalse(saved.get("exact_restoration",False))
                receipts=[event[2] for event in self.model.events if event[:2]==("receipt","cleanup")]
                self.assertTrue(all(value.get("native_restoration_verified") is not True for value in receipts))

    def test_serve_wait_body_survives_cleanup_error_without_lying_about_durable_first_error(self):
        body=RuntimeError("modeled_wait_body")
        def wait(store,kind,timeout):
            if kind=="probe_finished":raise body
        self.model.fail_delete=True
        with patch.object(self.model,"wait_request",wait):
            with self.assertRaises(RuntimeError) as caught:self.controller.serve()
        saved=json.loads(self.model.store.durable)
        self.assertEqual(saved["first_error"],"finished_request")
        self.assertEqual(saved["cleanup_error"],"cleanup_failed")
        self.assertIs(caught.exception,body)
        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_recover_actual_cleanup_body_survives_final_store_close(self):
        self.added();self.model.fail_get=True;captured=[]
        original=admin.Admin.cleanup
        def observe(controller,**options):
            try:return original(controller,**options)
            except BaseException as error:captured.append(error);raise
        def close():raise RuntimeError("modeled_recover_close")
        with patch.object(admin.Admin,"cleanup",observe),patch.object(self.model.store,"close",close):
            with self.assertRaises(Exception) as caught:admin.Admin.recover(Path("/model/admin"))
        self.assertEqual(len(captured),1);self.assertIs(caught.exception,captured[0])
        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))


if __name__=="__main__":
    unittest.main()
