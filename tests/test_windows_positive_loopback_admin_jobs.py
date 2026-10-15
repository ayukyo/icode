"""Fixed Job algorithm on real ctypes buffers and synthetic process handles."""
from __future__ import annotations
import copy
import ctypes as c
from ctypes import wintypes as t
import importlib
import json
from pathlib import Path, PureWindowsPath
import struct
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

NAME="scripts.windows_positive_loopback_admin_jobs"
try:
    jobs=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name!=NAME: raise
    jobs=None


def put(pointer,kind,value): c.cast(pointer,c.POINTER(kind))[0]=value


class Kernel:
    def __init__(self,store,win32):
        self.store,self.win32=store,win32
        self.mode="ok"; self.events=[]; self.members=(); self.exited=False
        self.resumed=False; self.alive=set(); self.attributes={}
        self.closed=[]; self.null_created=False
    def LocalFree(self,pointer): return 0
    def CreateJobObjectW(self,security,name):
        self.events.append("job"); self.alive.add(10); return 10
    def SetInformationJobObject(self,job,kind,pointer,size):
        limits=c.cast(pointer,c.POINTER(self.win32.EXTENDED_LIMITS)).contents
        if (job,kind,limits.basic.flags)!=(10,9,0x2000): raise AssertionError("limits")
        return 1
    def CreateFileW(self,path,access,sharing,security,creation,flags,template):
        if path!=r"\\.\NUL": raise AssertionError("nonfixed null path")
        self.null_created=True; self.alive.add(21); return 21
    def InitializeProcThreadAttributeList(self,pointer,count,flags,size):
        if count!=2 or flags!=0: raise AssertionError("attribute count")
        put(size,c.c_size_t,128); return pointer is not None
    def UpdateProcThreadAttribute(self,attribute_list,flags,kind,pointer,size,previous,returned):
        self.attributes[kind]=(pointer.value,size)
        return 1
    def DeleteProcThreadAttributeList(self,pointer): self.events.append("delete_attributes")
    def CreateProcessW(self,application,command,process_security,thread_security,inherit,flags,
                       environment,cwd,startup,output):
        self.events.append("create_suspended")
        if flags!=(4|0x400|0x80000|0x08000000) or inherit is not True:
            raise AssertionError("flags")
        if application!=self.store.data["system_tool"]["path"]: raise AssertionError("tool")
        if set(self.attributes)!={0x2000D,0x20002}: raise AssertionError("attributes")
        ptr,size=self.attributes[0x2000D]
        if size!=c.sizeof(t.HANDLE) or c.cast(ptr,c.POINTER(t.HANDLE))[0]!=10:
            raise AssertionError("job-list lifetime")
        ptr,size=self.attributes[0x20002]
        if tuple(c.cast(ptr,c.POINTER(t.HANDLE))[i] for i in range(2))!=(20,21):
            raise AssertionError("handle-list lifetime")
        start=c.cast(startup,c.POINTER(self.win32.STARTUP_EX)).contents
        if (start.startup.stdin,start.startup.stdout,start.startup.stderr)!=(21,20,20):
            raise AssertionError("stdio")
        process=c.cast(output,c.POINTER(self.win32.PROCESS)).contents
        process.process=30; process.thread=31
        self.alive.update((30,31))
        process.pid=0 if self.mode=="zero_pid" else 1234; process.tid=1235
        self.members=(9999,) if self.mode=="admission" else (1234,)
        return 1
    def GetProcessTimes(self,handle,created,exited,kernel,user):
        value=c.cast(created,c.POINTER(t.FILETIME)).contents
        value.dwLowDateTime=5678; value.dwHighDateTime=0; return 1
    def QueryInformationJobObject(self,job,kind,output,capacity,returned):
        if self.resumed and self.mode=="query_failure_after_resume": return 0
        c.memmove(output,struct.pack("<II",len(self.members),len(self.members)),8)
        if self.resumed and self.mode=="query_incomplete_after_resume":
            c.memmove(output,struct.pack("<II",len(self.members)+1,len(self.members)),8)
        values=c.cast(c.byref(output,8),c.POINTER(c.c_size_t))
        for index,pid in enumerate(self.members): values[index]=pid
        put(returned,t.DWORD,8+len(self.members)*c.sizeof(c.c_size_t)); return 1
    def ResumeThread(self,thread):
        self.events.append("resume")
        saved=json.loads(self.store.durable)
        record=saved["commands"][-1]
        if record["state"]!="ready" or record["resume_attempted"] is not None:
            raise AssertionError("resume without flushed ready identity")
        self.resumed=True
        if self.mode=="resume_exception": raise RuntimeError("ambiguous Resume")
        return 0 if self.mode=="resume_bad" else 1
    def WaitForSingleObject(self,handle,milliseconds):
        self.events.append(("wait",milliseconds))
        if milliseconds==5000:
            if self.mode=="reap_timeout": return 258
            self.exited=True
            self.members=(4321,) if self.mode in ("descendant","persistent_descendant","terminate_failure") else ()
            return 0
        if self.mode=="reap_timeout": return 258
        return 0 if self.exited else 258
    def TerminateJobObject(self,job,code):
        self.events.append("terminate")
        if self.mode=="terminate_failure": return 0
        self.exited=True
        if self.mode!="persistent_descendant": self.members=()
        return 1
    def GetExitCodeProcess(self,handle,output):
        self.events.append("exit_code")
        if self.mode=="exit_failure": return 0
        put(output,t.DWORD,0); return 1
    def CloseHandle(self,handle):
        if handle not in self.alive: raise AssertionError("double or unowned close")
        self.closed.append(handle)
        if self.mode=="close_failure" and handle==31: return 0
        self.alive.discard(handle); return 1


class ModelStore:
    def __init__(self,win32):
        self.root=Path("/model/admin")
        self.data=dict(session="4"*32,commands=[],owned_intent=True,phase="add_intent",
            operation_manifest=dict(started_ms=1000,deadline_ms=61000),
            bootstrap=dict(positive_sid="S-1-15-2-1",reviewer_sid="S-1-15-2-2"),
            system_tool=dict(path=r"C:\Windows\System32\CheckNetIsolation.exe"))
        self.w=win32.Win32.__new__(win32.Win32)
        self.kernel=Kernel(self,win32); self.w.k=self.kernel
        self.w.system_directory=PureWindowsPath(r"C:\Windows\System32")
        self.w.descriptor=lambda sddl:c.c_void_p(700)
        self.w.verify_security=lambda *args,**kwargs:None
        def open_output(*args,**kwargs):
            self.kernel.alive.add(20); return 20,(7,20)
        self.w.open_file=open_output
        self.files={}; self.durable=b""; self.fail_flush_state=None
        self.failed_once=False; self.flushes=[]
        self.flush()
    def write(self,name,value,*,create=False):
        if create and name in self.files: raise AssertionError("duplicate output")
        self.files[name]=value
    def flush(self):
        current=self.data["commands"][-1] if self.data["commands"] else {}
        if self.fail_flush_state is not None and current.get("state")==self.fail_flush_state and not self.failed_once:
            self.failed_once=True; raise RuntimeError("modeled FlushFileBuffers failed")
        self.durable=json.dumps(self.data,sort_keys=True,separators=(",",":"))
        self.flushes.append(copy.deepcopy(self.data))


class TestAdminJobs(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(jobs,"new fixed Job adapter absent; facility RED")
        self.win32=importlib.import_module("scripts.windows_positive_loopback_admin_win32")
        self.store=ModelStore(self.win32)
        self.patches=[patch.object(jobs.c,"set_last_error",lambda value:None,create=True),
                      patch.object(jobs.c,"get_last_error",lambda:0,create=True),
                      patch.object(jobs.time,"monotonic",lambda:1.0),
                      patch.object(jobs.time,"sleep",lambda seconds:None)]
        for item in self.patches: item.start(); self.addCleanup(item.stop)

    def test_normal_real_run_fixed_flushes_ready_before_resume_and_reaps_all(self):
        result=jobs.run_fixed(self.store,"add")
        self.assertTrue(result["reaped"])
        self.assertEqual((result["pid"],result["process_created"],result["resume_returned"]),(1234,5678,1))
        self.assertEqual(self.store.kernel.members,())
        self.assertTrue(self.store.kernel.exited)
        self.assertEqual(set(self.store.kernel.closed),{10,20,21,30,31})
        self.assertEqual(self.store.kernel.alive,set())
        self.assertEqual(json.loads(self.store.durable)["commands"][-1]["state"],"reaped")

    def test_create_job_final_descriptor_free_failure_closes_unreturned_job(self):
        self.store.kernel.LocalFree=lambda pointer:700
        with self.assertRaises(self.win32.Failure):
            jobs.create_job(self.store,"Local\\ICODE.Positive.test")
        self.assertEqual(self.store.kernel.alive,set(),"failed return must not strand acquired Job")
        self.assertEqual(self.store.kernel.closed,[10])

    def test_create_job_body_is_not_replaced_by_descriptor_or_job_cleanup(self):
        for failed in ("descriptor","job"):
            with self.subTest(failed=failed):
                self.store=ModelStore(self.win32);k=self.store.kernel
                body=self.win32.Failure("modeled_job_body")
                def limits(*args):raise body
                k.SetInformationJobObject=limits
                original_close=k.CloseHandle
                if failed=="descriptor":k.LocalFree=lambda pointer:700
                else:
                    def close(handle):original_close(handle);raise self.win32.Failure("modeled_job_close")
                    k.CloseHandle=close
                with self.assertRaises(self.win32.Failure) as caught:jobs.create_job(self.store,"Local\\owned")
                self.assertEqual(k.closed,[10])
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_run_fixed_body_survives_all_cleanup_boundaries_and_all_handles_attempted(self):
        for failed in ("thread","attributes","terminate","flush"):
            with self.subTest(failed=failed):
                self.store=ModelStore(self.win32);k=self.store.kernel
                body=self.win32.Failure("modeled_command_body")
                def resume(thread):raise body
                k.ResumeThread=resume
                if failed=="thread":k.mode="close_failure"
                elif failed=="attributes":
                    def attributes(pointer):raise self.win32.Failure("modeled_attributes_cleanup")
                    k.DeleteProcThreadAttributeList=attributes
                elif failed=="terminate":k.mode="terminate_failure"
                else:self.store.fail_flush_state="reaped_after_failure"
                clock=[1.0]
                def now():clock[0]+=0.01;return clock[0]
                with patch.object(jobs.time,"monotonic",now),self.assertRaises(self.win32.Failure) as caught:
                    jobs.run_fixed(self.store,"add")
                self.assertEqual(set(k.closed),{10,20,21,30,31},"cleanup failure must not stop independent CloseHandle attempts")
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_successful_create_bad_pid_or_job_admission_never_resumes_and_reaps(self):
        for mode in ("zero_pid","admission"):
            self.store=ModelStore(self.win32); self.store.kernel.mode=mode
            with self.subTest(mode=mode),self.assertRaises(self.win32.Failure):
                jobs.run_fixed(self.store,"add")
            self.assertFalse(self.store.kernel.resumed)
            self.assertTrue(self.store.kernel.exited); self.assertEqual(self.store.kernel.members,())
            self.assertIn("terminate",self.store.kernel.events)

    def test_ready_flush_failure_never_resumes_and_actually_reaps_suspended_process(self):
        self.store.fail_flush_state="ready"
        with self.assertRaises(RuntimeError): jobs.run_fixed(self.store,"add")
        self.assertFalse(self.store.kernel.resumed)
        self.assertTrue(self.store.kernel.exited); self.assertEqual(self.store.kernel.members,())
        saved=json.loads(self.store.durable)["commands"][-1]
        self.assertFalse(saved["resume_attempted"])
        self.assertTrue(saved["reaped"])

    def test_ready_flush_crossing_core_deadline_never_resumes(self):
        clock={"now":1.0};original=self.store.flush
        self.store.data["operation_manifest"]["deadline_ms"]=1500
        def flush():
            original()
            if self.store.data["commands"] and self.store.data["commands"][-1]["state"]=="ready":clock["now"]=1.6
        self.store.flush=flush
        with patch.object(jobs.time,"monotonic",lambda:clock["now"]):
            with self.assertRaises(self.win32.Failure):jobs.run_fixed(self.store,"add")
        self.assertFalse(self.store.kernel.resumed)
        self.assertTrue(self.store.kernel.exited)
        self.assertEqual(self.store.kernel.members,())
        self.assertFalse(json.loads(self.store.durable)["commands"][-1]["resume_attempted"])

    def test_resume_nonone_and_ambiguous_exception_do_not_return_success(self):
        for mode in ("resume_bad","resume_exception"):
            self.store=ModelStore(self.win32); self.store.kernel.mode=mode
            with self.subTest(mode=mode),self.assertRaises((self.win32.Failure,RuntimeError)):
                jobs.run_fixed(self.store,"add")
            self.assertTrue(self.store.kernel.resumed)
            self.assertTrue(self.store.kernel.exited); self.assertEqual(self.store.kernel.members,())

    def test_root_exit_is_insufficient_while_descendant_pid_remains(self):
        self.store.kernel.mode="descendant"
        result=jobs.run_fixed(self.store,"add")
        self.assertTrue(result["reaped"])
        self.assertIn("terminate",self.store.kernel.events)
        self.assertEqual(self.store.kernel.members,())
        events=self.store.kernel.events
        self.assertLess(events.index("terminate"),events.index("exit_code"))

    def test_exitcode_and_final_flush_failure_raise_despite_process_exit(self):
        for mode in ("exit_failure","final_flush"):
            self.store=ModelStore(self.win32)
            if mode=="final_flush":self.store.fail_flush_state="reaped"
            else:self.store.kernel.mode=mode
            with self.subTest(mode=mode),self.assertRaises((self.win32.Failure,RuntimeError)):
                jobs.run_fixed(self.store,"add")
            self.assertTrue(self.store.kernel.exited); self.assertEqual(self.store.kernel.members,())

    def test_final_close_failure_cannot_return_success(self):
        self.store.kernel.mode="close_failure"
        with self.assertRaises(self.win32.Failure): jobs.run_fixed(self.store,"add")
        self.assertEqual(set(self.store.kernel.closed),{10,20,21,30,31})
        self.assertEqual(self.store.kernel.alive,{31})

    def test_argv_fixed_positive_sid_and_replay_refusal(self):
        expected=[r"C:\Windows\System32\CheckNetIsolation.exe","LoopbackExempt","-a","-p=S-1-15-2-1"]
        self.assertEqual(jobs._argv(self.store,"add"),expected)
        self.store.data["phase"]="cleanup_intent"
        self.assertEqual(jobs._argv(self.store,"delete"),expected[:2]+["-d",expected[-1]])
        for kind in ("clear","-c","-is","shell",None):
            with self.subTest(kind=kind),self.assertRaises(self.win32.Failure):jobs._argv(self.store,kind)
        self.store.data["phase"]="add_intent"
        self.store.data["commands"].append(dict(kind="add"))
        with self.assertRaises(self.win32.Failure):jobs._argv(self.store,"add")

    def advancing_clock(self):
        state={"calls":0,"now":0.0}
        def now():
            state["calls"]+=1
            if state["calls"]>40: raise AssertionError("test clock finite-step guard")
            state["now"]+=0.75
            return state["now"]
        return state,now

    def test_wait_empty_continuing_descendants_has_finite_deadline_and_refuses(self):
        self.store.kernel.members=(4321,)
        state,now=self.advancing_clock()
        with patch.object(jobs.time,"monotonic",now):
            with self.assertRaises(self.win32.Failure):jobs.wait_empty(self.store,10,2000)
        self.assertGreater(state["calls"],1); self.assertLess(state["calls"],10)
        self.assertEqual(self.store.kernel.members,(4321,))

    def test_wait_empty_actual_query_failure_or_incomplete_never_means_empty(self):
        for mode in ("query_failure_after_resume","query_incomplete_after_resume"):
            self.store=ModelStore(self.win32);self.store.kernel.mode=mode
            self.store.kernel.resumed=True;self.store.kernel.members=(4321,)
            state,now=self.advancing_clock()
            with patch.object(jobs.time,"monotonic",now):
                with self.subTest(mode=mode),self.assertRaises(self.win32.Failure):
                    jobs.wait_empty(self.store,10,2000)
            self.assertEqual(self.store.kernel.members,(4321,))
            self.assertLess(state["calls"],10)

    def test_run_fixed_persistent_descendant_query_unknown_never_reports_reaped(self):
        for mode in ("persistent_descendant","query_failure_after_resume","query_incomplete_after_resume"):
            self.store=ModelStore(self.win32);self.store.kernel.mode=mode
            state,now=self.advancing_clock()
            with patch.object(jobs.time,"monotonic",now):
                with self.subTest(mode=mode),self.assertRaises(self.win32.Failure):
                    jobs.run_fixed(self.store,"add")
            record=self.store.data["commands"][-1]
            self.assertFalse(record["reaped"])
            self.assertNotEqual(record["state"],"reaped")
            self.assertFalse(json.loads(self.store.durable)["commands"][-1]["reaped"])
            self.assertLess(state["calls"],40)
            self.assertEqual(set(self.store.kernel.closed),{10,20,21,30,31})

    def test_run_fixed_terminate_failure_or_reap_wait_timeout_never_succeeds(self):
        for mode in ("terminate_failure","reap_timeout"):
            self.store=ModelStore(self.win32);self.store.kernel.mode=mode
            state,now=self.advancing_clock()
            with patch.object(jobs.time,"monotonic",now):
                with self.subTest(mode=mode),self.assertRaises(self.win32.Failure):
                    jobs.run_fixed(self.store,"add")
            self.assertFalse(self.store.data["commands"][-1]["reaped"])
            self.assertFalse(json.loads(self.store.durable)["commands"][-1]["reaped"])
            self.assertIn("terminate",self.store.kernel.events)
            self.assertLess(state["calls"],40)


if __name__=="__main__":
    unittest.main()
