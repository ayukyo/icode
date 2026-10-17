"""Real Native algorithms; every OS object here is an explicit software model."""
from __future__ import annotations
import copy
import ctypes as c
from ctypes import wintypes as t
from dataclasses import asdict
import importlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch
from tests.test_windows_positive_loopback_admin_binding import identity,manifest
from icode import windows_positive_loopback_policy as policy

NAME="scripts.windows_positive_loopback_admin_native"
MODEL=Path(tempfile.gettempdir()).resolve(strict=True)/"icode-admin-model"
SYSTEM=MODEL/"windows/System32"
try:
    native=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name!=NAME:raise
    native=None


def put(pointer,kind,value):c.cast(pointer,c.POINTER(kind))[0]=value
def serialized(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")
def snapshot(entries):
    return dict(schema=1,entries=entries,api_code=0,complete=True,sid_attempted=len(entries),
        sid_freed=len(entries),array_freed=True,library_freed=True,process_reaped=True)


def image_bytes(matrix="x64",*,dll=False):
    raw=bytearray(256);raw[:2]=b"MZ";raw[60:64]=(64).to_bytes(4,"little")
    raw[64:68]=b"PE\0\0";raw[68:70]={"x64":0x8664,"ARM64":0xAA64}[matrix].to_bytes(2,"little")
    raw[86:88]=(0x2000 if dll else 0).to_bytes(2,"little")
    return bytes(raw)


class Boundary:
    def __init__(self,store):
        self.store=store;self.error=0;self.next=100;self.handles={};self.closed=[]
        self.processes={1234:dict(created=5678,alive=True,user=store.boot["account_sid"]),
                        2234:dict(created=6789,alive=True,user=store.boot["account_sid"])}
        self.jobs={store.data["outer_job"]:[1234]};self.k=self;self.a=self;self.u=self
        self.system_directory=SYSTEM
        self.security_changed=False
        self.mode="ok";self.impersonated=False;self.impersonation_events=[]
        self.buffers={};self.sid_buffers={};self.descriptor_frees=0;self.sid_frees=0
        self.version_changes={}
    def assert_admin(self):pass
    def info(self,handle,*,directory=False):return (7,1)
    def verify_security(self,handle,sddl,**options):
        if self.security_changed:raise native.Failure("modeled_security_changed")
    def set_kernel_dacl(self,handle,sddl):pass
    def _handle(self,kind,value):
        self.next+=1;self.handles[self.next]=(kind,value);return self.next
    def close(self,handle):
        handle=handle.value if hasattr(handle,"value") else handle
        if handle not in self.handles:raise AssertionError("unowned/double close")
        self.closed.append(self.handles.pop(handle))
    def LookupAccountNameW(self,system,name,sid,size,domain,domain_size,use):
        raw=policy.sid_bytes(self.store.boot["account_sid"])
        put(size,t.DWORD,len(raw));put(domain_size,t.DWORD,2);put(use,t.DWORD,1)
        if sid is None:self.error=122;return 0
        c.memmove(sid,raw,len(raw));domain.value="M";return 1
    def IsValidSid(self,sid):return 1
    def GetLengthSid(self,sid):
        address=sid.value if isinstance(sid,c.c_void_p) else c.cast(sid,c.c_void_p).value
        return self.sid_buffers[address][1] if address in self.sid_buffers else len(policy.sid_bytes(self.store.boot["account_sid"]))
    def OpenProcess(self,access,inherit,pid):
        if pid not in self.processes:self.error=87;return 0
        return self._handle("process",pid)
    def process_created(self,handle):return 5678 if handle==1 else self.processes[self.handles[handle][1]]["created"]
    def process_user(self,handle):return self.processes[self.handles[handle][1]]["user"]
    def WaitForSingleObject(self,handle,milliseconds):
        if handle==1:return 258
        return 258 if self.processes[self.handles[handle][1]]["alive"] else 0
    def OpenJobObjectW(self,access,inherit,name):
        if name not in self.jobs:self.error=2;return 0
        return self._handle("job",name)
    def job_pids(self,handle):return tuple(self.jobs[self.handles[handle][1]])
    def IsProcessInJob(self,process,job,inside):
        pid=self.handles[process][1];members=self.jobs[self.handles[job][1]]
        put(inside,t.BOOL,pid in members);return 1
    def TerminateJobObject(self,job,code):
        members=self.jobs[self.handles[job][1]]
        for pid in members:
            if pid in self.processes:self.processes[pid]["alive"]=False
        members.clear();return 1
    def pin_ancestor(self,path,*,observe_only=False):return self._handle("route",str(path))
    def observe_security(self,handle):
        return dict(owner_binary=policy.sid_bytes("S-1-5-18").hex(),dacl_binary="0200080000000000",protected=True)
    def effective_access(self,handle,parent):
        return dict(api_completed=True,access_status=True,granted=0,privilege_bytes=0)
    def CreateFileW(self,path,*args):
        mask=args[0]
        if self.impersonated:
            leaf=Path(path).name
            permitted=(leaf=="readonly-request.canary" and mask==2 and self.mode!="deny_request") or (
                leaf=="readonly-public.canary" and mask==0x80000000)
            if self.mode=="allow_private" and leaf=="readonly-private.canary" and mask==2:permitted=True
            if not permitted:self.error=32 if self.mode=="wrong_denial" else 5;return c.c_void_p(-1).value
        return self._handle("file",path)
    def read(self,handle,limit):
        path=self.handles[handle][1];value=self.store.files[Path(path).name]
        if len(value)>limit:raise native.Failure("modeled_read_limit")
        return value
    def open_file(self,path,descriptor,**options):
        handle=self._handle("file",str(path));return handle,self.info(handle)
    def write(self,handle,value):self.store.files[Path(self.handles[handle][1]).name]=value
    def create_directory(self,path,descriptor):pass
    def verify_ancestor(self,handle):pass
    def WriteFile(self,handle,data,size,count,overlap):
        path=self.handles[handle][1]
        value=data[:size] if type(data) is bytes else c.string_at(data,size)
        self.store.files[Path(path).name]=value;put(count,t.DWORD,len(value));return 1
    def OpenProcessToken(self,parent,access,output):put(output,t.HANDLE,self._handle("token",parent));return 1
    def DuplicateToken(self,token,level,output):put(output,t.HANDLE,self._handle("token",token.value));return 1
    def ImpersonateLoggedOnUser(self,token):self.impersonated=True;self.impersonation_events.append("enter");return 1
    def RevertToSelf(self):self.impersonated=False;self.impersonation_events.append("leave");return 1
    def SetFileAttributesW(self,path,value):
        if self.mode=="allow_attributes":return 1
        self.error=5;return 0
    def MoveFileExW(self,source,destination,flags):
        if self.mode=="allow_rename":
            self.store.files[Path(destination).name]=self.store.files.pop(Path(source).name);return 1
        self.error=5;return 0
    def GetCurrentProcess(self):return 1
    def descriptor(self,sddl):
        buffer=c.create_string_buffer(b"synthetic-descriptor");address=c.addressof(buffer)
        self.buffers[address]=buffer;return c.c_void_p(address)
    def LocalFree(self,pointer):
        address=pointer.value if hasattr(pointer,"value") else pointer
        if address not in self.buffers:raise AssertionError("wrong descriptor allocator or double free")
        del self.buffers[address];self.descriptor_frees+=1;return None
    def DeriveAppContainerSidFromAppContainerName(self,name,output):
        raw=policy.sid_bytes(self.store.boot["positive_sid"])
        buffer=c.create_string_buffer(raw);address=c.addressof(buffer)
        self.sid_buffers[address]=(buffer,len(raw));put(output,c.c_void_p,address);return 0
    def FreeSid(self,pointer):
        if pointer.value not in self.sid_buffers:raise AssertionError("wrong SID allocator or double free")
        del self.sid_buffers[pointer.value];self.sid_frees+=1;return None
    def GetFileInformationByHandle(self,handle,output):
        value=c.cast(output,c.POINTER(native.abi.FILE_INFO)).contents
        value.attributes=0;value.links=2;value.volume=7;value.index_high=0;value.index_low=1
        value.size_high=0;value.size_low=256;return 1
    def GetFinalPathNameByHandleW(self,handle,buffer,capacity,flags):
        buffer.value=self.handles[handle][1];return len(buffer.value)

    def library(self,path,**options):
        if Path(path).name!="version.dll":return N()
        if Path(path)!=self.system_directory/"version.dll" or options.get("winmode")!=0x800:
            raise AssertionError("nonfixed version library")
        class Function:
            def __init__(self,body):self.body=body
            def __call__(self,*args):return self.body(*args)
        def read_version(path,handle,size,buffer):
            words=[0xFEEF04BD,0x10000,10<<16,1<<16,10<<16,1<<16,0,0,0,
                   2 if Path(path).suffix.lower()==".dll" else 1,0,0,0]
            for index,value in self.version_changes.get(Path(path).name,{}).items():words[index]=value
            raw=b"".join(value.to_bytes(4,"little") for value in words)
            c.memmove(buffer,raw,len(raw));return 1
        def query(buffer,subkey,pointer,count):
            put(pointer,c.c_void_p,c.addressof(buffer));put(count,t.UINT,52);return 1
        return N(GetFileVersionInfoSizeW=Function(lambda *args:52),
                 GetFileVersionInfoW=Function(read_version),VerQueryValueW=Function(query))


class NativeStore:
    def __init__(self):
        self.boot=identity();b=self.boot
        ctx={key:b[key] for key in ("repository","source_sha","run_id","run_attempt","job","matrix")}
        import hashlib
        self.root=MODEL/("icode-positive-admin-"+hashlib.sha256(serialized(ctx)).hexdigest()[:32]);self.root_handle=1
        self.handles=[];self.pins=[];self.route_records=[];self.files={};self.fail_flush=False
        self.extra_files=[];self.extra_directories=[];self.existing_slots=set()
        self.closed=False
        reader=b"fixed-reader"
        frozen_reader=dict(path="trusted/scripts/windows_positive_loopback_full_get.py",identity=[7,1],
                           size=len(reader),sha256=hashlib.sha256(reader).hexdigest())
        self.files["windows_positive_loopback_full_get.py"]=reader
        self.tree_files=[frozen_reader["path"]];self.tree_directories=[".","runtime","trusted","trusted/scripts"]
        security=dict(owner_binary=policy.sid_bytes("S-1-5-18").hex(),dacl_binary="0200080000000000",protected=True)
        access=dict(api_completed=True,access_status=True,granted=0,privilege_bytes=0)
        route=dict(path=str(MODEL.anchor),identity=[7,1],security=copy.deepcopy(security),effective=copy.deepcopy(access))
        image=dict(path=str(SYSTEM/"CheckNetIsolation.exe"),identity=[7,1],
            security=copy.deepcopy(security),effective=copy.deepcopy(access),
            file_info=dict(identity=[7,1],links=2,attributes=0,size=256),
            file_version=[10,0,1,0],product_version=[10,0,1,0])
        raw=image_bytes(ctx["matrix"])
        self.files["CheckNetIsolation.exe"]=raw
        image["provenance"]=dict(file_info=copy.deepcopy(image["file_info"]),
            sha256=hashlib.sha256(raw).hexdigest(),machine={"x64":0x8664,"ARM64":0xAA64}[ctx["matrix"]],
            file_version=list(image["file_version"]),product_version=list(image["product_version"]))
        self.data=dict(schema=1,context=ctx,account_name="icodeprobe_a",account_sid=b["account_sid"],
            session=b["session"],root_identity=[7,1],phase="bound",bootstrap=copy.deepcopy(b),
            operation_manifest=None,owned_intent=False,intent_ms=None,target_attributes=None,
            commands=[],observations={},reads=[],file_identities={},frozen_files=[frozen_reader],
            frozen_directories=[dict(path=name,identity=[7,1]) for name in self.tree_directories],
            system_tool=None,consumed={"profile_created":False,"probe_finished":False},
            parent=dict(pid=b["pid"],process_created=b["process_created"]),
            outer_job="Local\\ICODE.Positive."+b["session"]+".parent",first_error=None,
            cleanup_error=None,add_verified=False,delete_verified=False,others_preserved=False,
            exact_restoration=False,readonly_prepare=dict(schema=1,routes=[route],root_security=security,
                root_effective=access,sdk_layout_verified=True,python_binding_verified=True,
                loader_verified=True,canaries_verified=True,loader_images=[copy.deepcopy(image),
                    dict(path=str(self.root/frozen_reader["path"]),identity=list(frozen_reader["identity"]),
                         security=copy.deepcopy(security),effective=copy.deepcopy(access),file_info=None,provenance=None)],
                tool=[copy.deepcopy(image)],runner_arch_raw="X64"),operation_completed_ms=None,
            prepared_ms=b["prepared_ms"],profile_names=[b["positive_profile"],b["reviewer_profile"]],
            nonce=b["nonce"],ports=[b["ipv4_port"],b["ipv6_port"]])
        self.w=Boundary(self);self.flush()
    def flush(self):
        if self.fail_flush:raise native.Failure("modeled_flush")
        self.durable=serialized(self.data)
    def read(self,name,descriptor,limit):
        value=self.durable if name=="ledger.json" else self.files[name]
        if len(value)>limit:raise native.Failure("file_limit")
        return value
    def write(self,name,value,role="private",*,create=False):self.files[name]=value
    def file_descriptor(self,role):return native.Store.file_descriptor(self,role)
    def close(self):
        for collection in (self.handles,self.pins):
            while collection:self.w.close(collection.pop())
        self.closed=True


class TestAdminNative(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(native,"new Native component absent; expected facility RED")
        self.store=NativeStore();self.n=native.Native()
        b=self.store.boot
        self.env=dict(GITHUB_ACTIONS="true",RUNNER_ENVIRONMENT="github-hosted",RUNNER_OS="Windows",
            GITHUB_REPOSITORY=b["repository"],GITHUB_SHA=b["source_sha"],GITHUB_RUN_ID=b["run_id"],
            GITHUB_RUN_ATTEMPT=str(b["run_attempt"]),GITHUB_JOB=b["job"],RUNNER_ARCH="X64" if b["matrix"]=="x64" else "ARM64",
            GITHUB_REF="refs/heads/main",GITHUB_WORKFLOW_REF="ayukyo/icode/.github/workflows/ci.yml@refs/heads/main",
            GITHUB_WORKFLOW_SHA=b["source_sha"],ICODE_CI_POSITIVE_LOOPBACK_ADMIN="1",
            ICODE_CI_POSITIVE_LOOPBACK_DEDICATED_WRITER="1")
        self.patches=[patch.dict(native.os.environ,self.env,clear=True),
            patch.object(native.c,"WinDLL",lambda path,**options:self.store.w.library(path,**options),create=True),
            patch.object(native.c,"set_last_error",lambda value:setattr(self.store.w,"error",value),create=True),
            patch.object(native.c,"get_last_error",lambda:self.store.w.error,create=True),
            patch.object(native.time,"monotonic",lambda:180.999)]
        original_lstat,original_exists,original_glob,original_resolve=Path.lstat,Path.exists,Path.glob,Path.resolve
        root_prefix=str(self.store.root)
        def lstat(path,*args,**options):
            return N(st_file_attributes=0,st_size=0,st_mode=0) if str(path).startswith(root_prefix) else original_lstat(path,*args,**options)
        def exists(path):return str(path) in self.store.existing_slots if str(path).startswith(root_prefix) else original_exists(path)
        def glob(path,pattern):
            if str(path).startswith(root_prefix):return iter(Path(value) for value in self.store.existing_slots if Path(value).parent==path and value.endswith("._pth"))
            return original_glob(path,pattern)
        def resolve(path,*args,**options):
            # Synthetic roles stay lexical; unrelated real namespaces still resolve.
            modeled=any(path==root or root in path.parents for root in (self.store.root,self.store.w.system_directory))
            return path if modeled else original_resolve(path,*args,**options)
        def walk(path,*args,**options):
            base=Path(path).relative_to(self.store.root).as_posix()
            directories=self.store.tree_directories+self.store.extra_directories
            for value in directories:
                if value!=base and not value.startswith(base+"/"):continue
                current=self.store.root/value
                files=[Path(item).name for item in self.store.tree_files+self.store.extra_files if (self.store.root/item).parent==current]
                children=[Path(item).name for item in directories if (self.store.root/item).parent==current]
                yield str(current),children,files
        self.patches += [patch.object(Path,"lstat",lstat),patch.object(Path,"exists",exists),
                         patch.object(Path,"glob",glob),patch.object(Path,"resolve",resolve),patch.object(native.os,"walk",walk)]
        for item in self.patches:item.start();self.addCleanup(item.stop)

    def operation(self):
        self.store.data["consumed"]["profile_created"]=True
        base=snapshot([["S-1-15-2-99",0x80000004]])
        self.store.data["observations"]={"baseline_first":copy.deepcopy(base),"baseline":base}
        self.store.flush()
        return self.n.freeze_operation(self.store)

    def ledger(self,value):
        # Same explicit role context as each real Native entry point, not a
        # replacement parser or a permissive callback into production code.
        return native.ledger(value,private_root=self.store.root,system_directory=self.store.w.system_directory)

    def command_record(self,*,state="ready",pid=2234,attempted=None):
        return dict(kind="add",job="Local\\ICODE.Positive."+self.store.data["session"]+".command.0",
            output="command-0.out",state=state,pid=pid,process_created=6789 if pid else None,
            resume_permitted=pid is not None,resume_attempted=attempted,resume_returned=None,
            exit_code=None,timed_out=False,reaped=False)

    def ready(self,record=None):
        operation=self.operation()
        self.store.data.update(phase="add_intent",owned_intent=True,intent_ms=operation.started_ms)
        record=self.command_record() if record is None else record
        self.store.data["commands"]=[record];self.store.flush()
        self.store.w.jobs[record["job"]]=[2234]
        return record

    def test_context_exact_environment_and_schema_rejects_spoofed_inputs(self):
        self.assertEqual(native.context(self.store.data["context"]),self.store.data["context"])
        for key in self.env:
            with self.subTest(key=key),patch.dict(native.os.environ,{key:"wrong"}):
                with self.assertRaises(native.Failure):native.context(self.store.data["context"])
        for changed in (dict(self.store.data["context"],extra=1),
                        dict(self.store.data["context"],run_attempt=True)):
            with self.assertRaises(native.Failure):native.context(changed)

    def test_context_official_arch_mapping_and_cross_or_nonofficial_values_reject(self):
        for matrix,architecture in (("x64","X64"),("ARM64","ARM64")):
            value=dict(self.store.data["context"],matrix=matrix)
            with patch.dict(native.os.environ,{"RUNNER_ARCH":architecture}):
                self.assertEqual(native.context(value),value)
            for wrong in ({"X64","ARM64","x64","arm64","X86","ARM","unknown"}-{architecture}):
                with self.subTest(matrix=matrix,wrong=wrong),patch.dict(native.os.environ,{"RUNNER_ARCH":wrong}):
                    with self.assertRaises(native.Failure):native.context(value)

    def test_ledger_exact_top_level_and_critical_types(self):
        self.n.verify_store(self.store)
        for key in self.store.data:
            value=copy.deepcopy(self.store.data);del value[key]
            with self.subTest(key=key),self.assertRaises(native.Failure):self.ledger(value)
        for key,value in (("schema",True),("consumed",{"profile_created":1,"probe_finished":False}),
                          ("ports",[True,2]),("target_attributes",True),("owned_intent",1)):
            changed=copy.deepcopy(self.store.data);changed[key]=value
            with self.subTest(key=key),self.assertRaises(native.Failure):self.ledger(changed)

    def test_ledger_bootstrap_identity_cannot_disagree_with_owned_context(self):
        self.ledger(self.store.data)
        for key,value in (("source_sha","b"*40),("pid",4321),("nonce","8"*32),
                          ("ipv4_port",12346),("positive_profile","icode-"+"9"*32)):
            changed=copy.deepcopy(self.store.data);changed["bootstrap"][key]=value
            with self.subTest(key=key),self.assertRaises(native.Failure):self.ledger(changed)

    def test_verify_store_extra_files_directories_and_startup_slots_reject(self):
        self.n.verify_store(self.store)
        for relative in ("runtime/unlisted.pyd","trusted/unlisted.py"):
            self.store.extra_files=[relative]
            with self.subTest(relative=relative),self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.extra_files=[];self.store.extra_directories=["runtime/injected"]
        with self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.extra_directories=[]
        for relative in ("pyvenv.cfg","runtime/pyvenv.cfg","runtime/python312._pth","runtime/python3._pth","runtime/python312.zip"):
            self.store.existing_slots={str(self.store.root/relative)}
            with self.subTest(relative=relative),self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.existing_slots=set()

    def test_operation_uses_fresh_clock_and_can_only_freeze_once(self):
        result=self.operation()
        self.assertEqual((result.started_ms,result.deadline_ms),(180999,240999))
        self.assertEqual(self.store.data["operation_manifest"],asdict(result))
        with self.assertRaises(native.Failure):self.n.freeze_operation(self.store)

    def test_request_real_slot_bytes_are_consumed_durably_once(self):
        self.store.files[native.SLOTS["profile_created"]]=b"fixed request bytes"
        result=self.n.consume_request(self.store,"profile_created")
        self.assertEqual(result,b"fixed request bytes")
        self.assertTrue(json.loads(self.store.durable)["consumed"]["profile_created"])
        with self.assertRaises(native.Failure):self.n.consume_request(self.store,"profile_created")
        self.assertEqual(self.store.data["commands"],[])

    def test_consumption_failed_flush_does_not_return_request_or_start_command(self):
        self.store.files[native.SLOTS["profile_created"]]=b"fixed request bytes"
        self.store.fail_flush=True
        with self.assertRaises(native.Failure):self.n.consume_request(self.store,"profile_created")
        self.assertFalse(json.loads(self.store.durable)["consumed"]["profile_created"])
        self.assertEqual(self.store.data["commands"],[])

    def test_parent_only_checks_real_identity_membership_and_complete_pid_set(self):
        self.assertTrue(self.n.parent_only(self.store))
        name=self.store.data["outer_job"]
        self.store.w.jobs[name]=[1234,4321]
        self.assertFalse(self.n.parent_only(self.store))
        self.store.w.processes[1234]["created"]=9999
        with self.assertRaises(native.Failure):self.n.parent_only(self.store)
        self.assertEqual(self.store.w.handles,{})

    def test_every_job_verification_uses_the_job_masked_kernel_descriptor(self):
        seen=[]
        original=self.store.w.verify_security
        def verify(handle,sddl,**options):seen.append((sddl,options))
        self.store.w.verify_security=verify
        try:
            self.n._outer(self.store)
            record=self.ready();self.n.reap_commands(self.store)
            self.n.stop_parent_job(self.store)
        finally:
            self.store.w.verify_security=original
        jobs_only=[item for item in seen if item[1].get("object_type")==6]
        self.assertEqual({options.get("category") for sddl,options in jobs_only},
            {"outer_job_security_changed","stop_job_security_changed","reap_job_security_changed"})
        for sddl,options in jobs_only:
            self.assertEqual(sddl,native.KERNEL_PRIVATE)
        for sddl,options in seen:
            if options.get("object_type")!=6:
                self.assertNotEqual(sddl,native.KERNEL_PRIVATE)

    def test_durable_ready_unknown_resume_requires_actual_job_termination_and_exit(self):
        record=self.ready()
        self.assertIsNone(json.loads(self.store.durable)["commands"][0]["resume_attempted"])
        self.n.reap_commands(self.store)
        self.assertFalse(self.store.w.processes[2234]["alive"])
        self.assertEqual(self.store.w.jobs[record["job"]],[])
        self.assertTrue(self.n.has_add_attempt(self.store))
        self.assertEqual(self.store.w.handles,{})

    def test_missing_job_with_live_recorded_process_refuses_no_late_add_claim(self):
        record=self.ready();del self.store.w.jobs[record["job"]]
        with self.assertRaises(native.Failure):self.n.reap_commands(self.store)
        self.assertTrue(self.store.w.processes[2234]["alive"])
        self.assertEqual(self.store.w.handles,{})

    def test_missing_outer_job_rejection_releases_parent_handle(self):
        del self.store.w.jobs[self.store.data["outer_job"]]
        with self.assertRaises(native.Failure):self.n.verify_parent(self.store)
        self.assertEqual(self.store.w.handles,{})

    def test_stop_parent_missing_job_but_live_parent_refuses_and_closes_handle(self):
        del self.store.w.jobs[self.store.data["outer_job"]]
        with self.assertRaises(native.Failure):self.n.stop_parent_job(self.store)
        self.assertTrue(self.store.w.processes[1234]["alive"])
        self.assertEqual(self.store.w.handles,{})

    def test_allocated_without_identity_cannot_adopt_unknown_add_attempt(self):
        record=self.ready(self.command_record(state="allocated",pid=None,attempted=False))
        with self.assertRaises(native.Failure):self.n.reap_commands(self.store)
        self.assertEqual(self.store.w.jobs[record["job"]],[])
        self.assertFalse(self.n.has_add_attempt(self.store))

    def test_has_add_attempt_true_none_false_permitted_and_identity_are_distinct(self):
        for attempted,expected in ((True,True),(None,True),(False,False)):
            self.store=NativeStore();self.ready(self.command_record(attempted=attempted))
            self.assertEqual(self.n.has_add_attempt(self.store),expected)
        self.store=NativeStore();record=self.command_record();del record["resume_permitted"]
        self.ready(record)
        with self.assertRaises(native.Failure):self.n.has_add_attempt(self.store)
        for missing in ("pid","process_created"):
            self.store=NativeStore();record=self.command_record();record[missing]=None
            self.ready(record)
            with self.subTest(missing=missing),self.assertRaises(native.Failure):self.n.has_add_attempt(self.store)

    def test_real_admin_cleanup_with_known_no_resume_refuses_unexpected_target(self):
        record=self.command_record(state="reaped_after_failure",attempted=False);record["reaped"]=True
        self.ready(record)
        self.store.w.processes[2234]["alive"]=False;self.store.w.jobs[record["job"]]=[]
        calls=[]
        raw=snapshot([["S-1-15-2-99",0x80000004],[self.store.boot["positive_sid"],7]])
        raw["process_reaped"]=None
        def worker(store,kind):
            calls.append(kind)
            if kind!="get":raise AssertionError("known-not-resumed add never grants delete")
            number=len(store.data["commands"])
            result=self.command_record(state="reaped",attempted=True)
            result.update(kind="get",job="Local\\ICODE.Positive."+store.data["session"]+".command."+str(number),
                output="command-"+str(number)+".out",resume_returned=1,exit_code=0,reaped=True)
            store.files[result["output"]]=serialized(raw);store.data["commands"].append(result);store.flush()
            return copy.deepcopy(result)
        admin_module=importlib.import_module("scripts.windows_positive_loopback_admin")
        controller=admin_module.Admin.__new__(admin_module.Admin)
        controller.native=self.n;controller.store=self.store;controller.data=self.store.data
        with patch.object(native,"run_fixed",worker):
            with self.assertRaises(admin_module.AdminError):controller.cleanup(abnormal=False)
        self.assertEqual(calls,["get"])
        self.assertEqual(controller.data["first_error"],"owner_conflict")
        self.assertEqual(controller.data["observations"]["pre_delete"]["entries"][-1],
                         [self.store.boot["positive_sid"],7])

    def repeat_completed_cleanup(self, foreign_changed=False):
        operation=self.operation(); completed=operation.started_ms+1
        record=self.command_record(state="reaped",attempted=True)
        record.update(reaped=True,resume_returned=1,exit_code=0)
        self.store.data.update(phase="cleaned",owned_intent=True,intent_ms=operation.started_ms,
            add_verified=True,delete_verified=True,others_preserved=True,exact_restoration=True,
            operation_completed_ms=completed,target_attributes=7,commands=[record])
        base=copy.deepcopy(self.store.data["observations"]["baseline"])
        self.store.data["observations"].update(
            after_add=snapshot(base["entries"]+[[self.store.boot["positive_sid"],7]]),
            pre_delete=copy.deepcopy(base),post_delete=copy.deepcopy(base))
        self.store.w.processes[2234]["alive"]=False
        self.store.flush()
        # Validate a real producer-shaped success ledger before entering cleanup.
        self.n.verify_store(self.store)
        raw=snapshot([["S-1-15-2-99",0x80000005 if foreign_changed else 0x80000004]])
        raw["process_reaped"]=None; calls=[]
        def worker(store,kind):
            calls.append(kind)
            if kind!="get":raise AssertionError("completed cleanup must not issue another mutation")
            number=len(store.data["commands"])
            result=self.command_record(state="reaped",attempted=True)
            result.update(kind="get",job="Local\\ICODE.Positive."+store.data["session"]+".command."+str(number),
                output="command-"+str(number)+".out",resume_returned=1,exit_code=0,reaped=True)
            store.files[result["output"]]=serialized(raw);store.data["commands"].append(result);store.flush()
            return copy.deepcopy(result)
        module=importlib.import_module("scripts.windows_positive_loopback_admin")
        controller=module.Admin.__new__(module.Admin)
        controller.native=self.n;controller.store=self.store;controller.data=self.store.data
        with patch.object(native,"run_fixed",worker),patch.object(native.time,"monotonic",
                lambda:(operation.deadline_ms+1000)/1000):
            try:receipt=controller.cleanup(abnormal=True)
            except module.AdminError as exc:
                self.fail("independent always cleanup rejected valid completed ledger: "+str(exc))
        self.assertEqual(self.store.data["operation_completed_ms"],completed)
        self.assertEqual(self.store.data["operation_manifest"]["deadline_ms"],operation.deadline_ms)
        self.assertEqual(self.store.data["operation_manifest"]["started_ms"],operation.started_ms)
        self.assertTrue(calls);self.assertTrue(all(kind=="get" for kind in calls))
        self.n.verify_store(self.store)
        return receipt

    def test_real_completed_cleanup_independent_always_is_idempotent_after_deadline(self):
        receipt=self.repeat_completed_cleanup()
        self.assertTrue(receipt["native_restoration_verified"])
        self.assertEqual(self.store.data["phase"],"cleaned")
        self.assertIsNone(self.store.data["first_error"])
        self.assertIsNone(self.store.data["cleanup_error"])

    def test_real_completed_cleanup_foreign_change_never_reuses_exact_success(self):
        receipt=self.repeat_completed_cleanup(foreign_changed=True)
        self.assertFalse(receipt["native_restoration_verified"])
        self.assertFalse(self.store.data["exact_restoration"])
        self.assertEqual(self.store.data["first_error"],"foreign_delta")

    def test_real_first_cleanup_producer_then_independent_reopen_cleanup(self):
        operation=self.operation()
        record=self.command_record(state="reaped",attempted=True)
        record.update(reaped=True,resume_returned=1,exit_code=0)
        base=copy.deepcopy(self.store.data["observations"]["baseline"])
        self.store.data.update(phase="added",owned_intent=True,intent_ms=operation.started_ms,
            target_attributes=7,add_verified=True,commands=[record])
        self.store.data["observations"]["after_add"]=snapshot(base["entries"]+[[self.store.boot["positive_sid"],7]])
        self.store.w.processes[2234]["alive"]=False
        self.store.flush();self.n.verify_store(self.store)
        flush_records=[]
        def checked_flush():
            # Every production intermediate Flush must itself remain replayable.
            self.ledger(self.store.data)
            NativeStore.flush(self.store)
            self.ledger(native.decode(self.store.durable,8388608))
            flush_records.append(copy.deepcopy(self.store.data))
        self.store.flush=checked_flush
        calls=[]
        def worker(store,kind):
            calls.append(kind)
            if kind!="get":raise AssertionError("target already absent: no further mutation")
            index=len(store.data["commands"])
            result=self.command_record(state="reaped",attempted=True)
            result.update(kind="get",job="Local\\ICODE.Positive."+store.data["session"]+".command."+str(index),
                output="command-"+str(index)+".out",resume_returned=1,exit_code=0,reaped=True)
            raw=copy.deepcopy(base);raw["process_reaped"]=None
            store.files[result["output"]]=serialized(raw);store.data["commands"].append(result);store.flush()
            return copy.deepcopy(result)
        module=importlib.import_module("scripts.windows_positive_loopback_admin")
        def controller():
            result=module.Admin.__new__(module.Admin)
            result.native=self.n;result.store=self.store;result.data=self.store.data
            return result
        with patch.object(native,"run_fixed",worker):
            first=controller().cleanup(abnormal=False)
            self.assertTrue(first["native_restoration_verified"])
            completed=self.store.data["operation_completed_ms"]
            durable=self.store.durable;files=copy.deepcopy(self.store.files)
            processes=copy.deepcopy(self.store.w.processes);job_members=copy.deepcopy(self.store.w.jobs)
            # Independent object reopens persisted bytes, not the first controller state.
            reopened=NativeStore();reopened.data=native.decode(durable,8388608)
            reopened.durable=durable;reopened.files=files
            reopened.w.processes=processes;reopened.w.jobs=job_members
            self.store=reopened;self.n=native.Native();self.n.verify_store(self.store)
            self.store.flush=checked_flush
            with patch.object(native.time,"monotonic",lambda:(operation.deadline_ms+1000)/1000):
                try:second=controller().cleanup(abnormal=True)
                except module.AdminError as exc:self.fail("real first-cleanup ledger failed independent always: "+str(exc))
            self.assertTrue(second["native_restoration_verified"])
            self.assertEqual(self.store.data["operation_completed_ms"],completed)
            self.assertEqual(self.store.data["operation_manifest"]["deadline_ms"],operation.deadline_ms)
            self.n.verify_store(self.store)
            self.assertTrue(any(row["phase"]=="cleanup_intent" and not row["exact_restoration"]
                                and not row["delete_verified"] for row in flush_records))

    def test_ledger_intermediate_cleanup_flush_cannot_retain_completed_success_flags(self):
        self.repeat_completed_cleanup()
        valid=copy.deepcopy(self.store.data)
        changed=copy.deepcopy(valid);changed["phase"]="cleanup_intent"
        with self.assertRaises(native.Failure):self.ledger(changed)
        changed.update(exact_restoration=False,delete_verified=False,others_preserved=False)
        self.ledger(changed)
        for missing in ("readonly_prepare","parent","outer_job"):
            changed=copy.deepcopy(valid);changed[missing]=None
            with self.subTest(missing=missing),self.assertRaises(native.Failure):self.ledger(changed)

    def test_ledger_owned_baselines_cannot_precontain_positive_or_reviewer(self):
        self.ready();valid=copy.deepcopy(self.store.data)
        for key in ("positive_sid","reviewer_sid"):
            changed=copy.deepcopy(valid)
            for name in ("baseline_first","baseline"):
                changed["observations"][name]=snapshot([[self.store.boot[key],7]])
            with self.subTest(key=key),self.assertRaises(native.Failure):self.ledger(changed)

    def test_ledger_owned_baselines_must_agree_and_observations_bind_target_attributes(self):
        self.ready();valid=copy.deepcopy(self.store.data)
        changed=copy.deepcopy(valid)
        changed["observations"]["baseline_first"]=snapshot([["S-1-15-2-99",9]])
        with self.subTest(kind="baseline_delta"),self.assertRaises(native.Failure):self.ledger(changed)
        changed=copy.deepcopy(valid);changed.update(phase="added",add_verified=True,target_attributes=7)
        changed["observations"]["after_add"]=copy.deepcopy(changed["observations"]["baseline"])
        with self.subTest(kind="after_add_missing_target"),self.assertRaises(native.Failure):self.ledger(changed)

    def test_reused_pid_is_not_killed_but_owned_job_descendant_is_stopped(self):
        record=self.ready()
        self.store.w.processes[2234]["created"]=9999
        self.store.w.processes[4321]=dict(created=1111,alive=True,user=self.store.boot["account_sid"])
        self.store.w.jobs[record["job"]]=[4321]
        self.n.reap_commands(self.store)
        self.assertTrue(self.store.w.processes[2234]["alive"])
        self.assertFalse(self.store.w.processes[4321]["alive"])
        self.assertEqual(self.store.w.handles,{})

    def test_stale_memory_reaped_flag_never_overrides_persisted_ready_record(self):
        self.ready();self.store.data["commands"][0]["reaped"]=True
        with self.assertRaises(native.Failure):self.n.reap_commands(self.store)
        self.assertTrue(self.store.w.processes[2234]["alive"])

    def test_complete_get_worker_may_not_supply_its_own_reaped_credit(self):
        raw=snapshot([["S-1-15-2-99",7]]);raw["process_reaped"]=None
        def worker(store,kind):
            number=len(store.data["commands"])
            record=self.command_record(state="reaped",attempted=True)
            record.update(kind="get",job="Local\\ICODE.Positive."+store.data["session"]+".command."+str(number),
                output="command-"+str(number)+".out",resume_returned=1,exit_code=0,reaped=True)
            store.files[record["output"]]=serialized(raw)
            store.data["commands"].append(record);store.flush()
            return copy.deepcopy(record)
        with patch.object(native,"run_fixed",worker):
            observed=self.n.full_get(self.store)
        self.assertTrue(observed["process_reaped"])
        import hashlib
        read=self.store.data["reads"][0]
        self.assertEqual(set(read),{"started_ms","finished_ms","command_index","raw_sha256","reader_sha256"})
        self.assertEqual((read["started_ms"],read["finished_ms"],read["command_index"]),(180999,180999,0))
        self.assertEqual(read["raw_sha256"],hashlib.sha256(serialized(observed)).hexdigest())
        self.assertEqual(read["reader_sha256"],self.store.data["frozen_files"][0]["sha256"])
        raw["process_reaped"]=True
        with patch.object(native,"run_fixed",worker):
            with self.assertRaises(native.Failure):self.n.full_get(self.store)

    def test_get_unreaped_timed_out_or_nonzero_never_returns_complete_mapping(self):
        for changed in (dict(reaped=False,timed_out=False,exit_code=0),
                        dict(reaped=True,timed_out=True,exit_code=0),
                        dict(reaped=True,timed_out=False,exit_code=5)):
            with patch.object(native,"run_fixed",lambda store,kind:dict(changed,output="worker.out")):
                with self.subTest(changed=changed),self.assertRaises(native.Failure):self.n.full_get(self.store)

    def test_bootstrap_publication_uses_nested_identity_and_independent_digest(self):
        import hashlib
        self.n.publish_manifest(self.store)
        published=json.loads(self.store.files["bootstrap.json"])
        self.assertEqual(set(published),{"identity","binding"})
        self.assertEqual(published["identity"],self.store.boot)
        self.assertEqual(published["binding"],hashlib.sha256(serialized(self.store.boot)).hexdigest())

    def test_loader_real_algorithm_rejects_module_extension_and_dll_external_origins(self):
        extensions=("_ctypes","_socket","select","_hashlib","_ssl","unicodedata")
        modules={name:N(__file__=str(self.store.root/"runtime/DLLs"/(name+".pyd"))) for name in extensions}
        self.store.data["frozen_files"]=[dict(path="runtime/DLLs/"+name+".pyd") for name in extensions]
        self.store.data["frozen_files"] += [dict(path="runtime/"+name) for name in ("python312.dll","python3.dll")]
        dlls={name:str(self.store.root/"runtime"/name) if name.startswith("python") else
              str(self.store.w.system_directory/name) for name in
              ("python312.dll","python3.dll","advapi32.dll","userenv.dll","kernel32.dll","FirewallAPI.dll")}
        for name in dlls:
            if not name.startswith("python"):self.store.files[name]=image_bytes(dll=True)
        names=list(dlls)
        self.store.w.GetModuleHandleW=lambda name:names.index(name)+1
        def filename(handle,buffer,capacity):
            buffer.value=dlls[names[handle-1]];return len(buffer.value)
        self.store.w.GetModuleFileNameW=filename
        def enumerate_modules(current,output,capacity,returned):
            for index,name in enumerate(names):output[index]=index+1
            put(returned,t.DWORD,len(names)*c.sizeof(t.HANDLE));return 1
        self.store.w.K32EnumProcessModules=enumerate_modules
        with patch.object(native.sys,"executable",str(self.store.root/"runtime/python.exe")),patch.object(
            native.sys,"flags",N(isolated=1,no_site=1,dont_write_bytecode=1)),patch.object(
            native.sys,"modules",modules),patch.object(native.importlib,"import_module",lambda name:modules[name]),patch.object(
            Path,"resolve",lambda path,*args,**kwargs:path),patch.object(native.c,"WinDLL",self.store.w.library,create=True),patch.object(
            native.sys,"path",[str(self.store.root/name) for name in ("runtime/python312.zip","runtime/DLLs","runtime/Lib","runtime","trusted","trusted/src")]):
            self.n._loader(self.store,123)
            self.store.close();self.assertEqual(self.store.w.handles,{})
            for paths in (native.sys.path+["/external"],native.sys.path+native.sys.path[:1],
                          native.sys.path+[native.sys.path[0].upper()],native.sys.path[:-1]):
                with patch.object(native.sys,"path",paths):
                    with self.assertRaises(native.Failure):self.n._loader(self.store,123)
            modules["_ssl"].__file__="/external/ssl.pyd"
            with self.assertRaises(native.Failure):self.n._loader(self.store,123)
            modules["_ssl"].__file__=str(self.store.root/"runtime/DLLs/_ssl.pyd")
            dlls["python312.dll"]="/external/python312.dll"
            with self.assertRaises(native.Failure):self.n._loader(self.store,123)

    def test_loader_route_or_leaf_access_failure_closes_every_allocated_handle(self):
        extensions=("_ctypes","_socket","select","_hashlib","_ssl","unicodedata")
        for stage in ("route_api","route_rights","leaf_api","leaf_rights"):
            self.store=NativeStore()
            modules={name:N(__file__=str(self.store.root/"runtime/DLLs"/(name+".pyd"))) for name in extensions}
            self.store.data["frozen_files"]=[dict(path="runtime/DLLs/"+name+".pyd") for name in extensions]
            self.store.data["frozen_files"] += [dict(path="runtime/"+name) for name in ("python312.dll","python3.dll")]
            names=["python312.dll","python3.dll","advapi32.dll","userenv.dll","kernel32.dll","FirewallAPI.dll"]
            paths=[str(self.store.root/"runtime"/name) if name.startswith("python") else
                   str(self.store.w.system_directory/name) for name in names]
            self.store.w.GetModuleHandleW=lambda name:names.index(name)+1
            def filename(handle,buffer,capacity):buffer.value=paths[handle-1];return len(buffer.value)
            self.store.w.GetModuleFileNameW=filename
            def enum(current,output,capacity,returned):output[0]=1;put(returned,t.DWORD,c.sizeof(t.HANDLE));return 1
            self.store.w.K32EnumProcessModules=enum
            # The production low-level role is 'file'; map it to the requested
            # leaf fault without changing the actual allocation/close table.
            def effective(handle,parent):
                kind=self.store.w.handles[handle][0]
                match=(kind=="route" and stage.startswith("route")) or (kind=="file" and stage.startswith("leaf"))
                if match and stage.endswith("api"):raise native.Failure("modeled_access_api")
                return dict(api_completed=True,access_status=True,granted=0x100 if match else 0,privilege_bytes=0)
            self.store.w.effective_access=effective
            with patch.object(native.sys,"executable",str(self.store.root/"runtime/python.exe")),patch.object(
                native.sys,"flags",N(isolated=1,no_site=1,dont_write_bytecode=1)),patch.object(native.sys,"modules",modules),patch.object(
                native.importlib,"import_module",lambda name:modules[name]),patch.object(Path,"resolve",lambda path,*args,**kwargs:path),patch.object(
                native.c,"WinDLL",lambda *args,**options:N(),create=True),patch.object(native.sys,"path",[str(self.store.root/name) for name in (
                "runtime/python312.zip","runtime/DLLs","runtime/Lib","runtime","trusted","trusted/src")]):
                with self.subTest(stage=stage),self.assertRaises(native.Failure):self.n._loader(self.store,123)
            self.store.close()
            with self.subTest(stage=stage):self.assertEqual(self.store.w.handles,{})

    def test_real_canaries_standard_token_writes_only_request_and_reads_public(self):
        self.store.files.update({"readonly-request.canary":b"","readonly-public.canary":b"public",
                                 "readonly-private.canary":b"private"})
        self.n._canaries(self.store,123)
        self.assertEqual(self.store.files["readonly-request.canary"],b"ok")
        self.assertEqual(self.store.files["readonly-public.canary"],b"public")
        self.assertEqual(self.store.files["readonly-private.canary"],b"private")
        self.assertFalse(self.store.w.impersonated)
        self.assertEqual(self.store.w.impersonation_events,["enter","leave"])
        self.assertEqual(self.store.w.handles,{})

    def test_real_canary_negative_rights_wrong_error_and_rename_fail_closed(self):
        for mode in ("deny_request","allow_private","wrong_denial","allow_attributes","allow_rename"):
            self.store=NativeStore();self.store.w.mode=mode
            self.store.files.update({"readonly-request.canary":b"","readonly-public.canary":b"public",
                                     "readonly-private.canary":b"private"})
            with self.subTest(mode=mode),self.assertRaises(native.Failure):self.n._canaries(self.store,123)
            self.assertFalse(self.store.w.impersonated)
            self.assertEqual(self.store.w.impersonation_events,["enter","leave"])
            self.assertEqual(self.store.w.handles,{})

    def test_real_canary_token_cleanup_attempts_both_and_preserves_body_or_revert_error(self):
        for failed_token in (1,2):
            for body_mode in ("ok","write_error","revert_error","write_and_revert_error"):
                with self.subTest(failed_token=failed_token,body_mode=body_mode):
                    self.store=NativeStore();w=self.store.w;attempted=[];token_attempts=[]
                    body=native.Failure("modeled_canary_body")
                    self.store.files.update({"readonly-request.canary":b"","readonly-public.canary":b"public",
                                             "readonly-private.canary":b"private"})
                    def close_handle(resource):
                        handle=resource.value if hasattr(resource,"value") else resource
                        if handle not in w.handles:raise AssertionError("unowned/double close")
                        kind=w.handles[handle][0];attempted.append(handle)
                        if kind=="token":
                            token_attempts.append(handle)
                            if len(token_attempts)==failed_token:return 0
                        w.closed.append(w.handles.pop(handle));return 1
                    w.CloseHandle=close_handle
                    # Execute actual Win32.close too; inject failure only at CloseHandle.
                    w.close=native.abi.Win32.close.__get__(w,type(w))
                    if body_mode in ("write_error","write_and_revert_error"):
                        def write_error(*args):raise body
                        w.WriteFile=write_error
                    if body_mode in ("revert_error","write_and_revert_error"):
                        def revert_error():
                            w.impersonated=False;w.impersonation_events.append("leave")
                            raise body if body_mode=="revert_error" else native.Failure("modeled_revert_cleanup")
                        w.RevertToSelf=revert_error
                    with self.assertRaises(native.Failure) as caught:self.n._canaries(self.store,123)
                    self.assertEqual(len(token_attempts),2,"duplicate close failure must not skip original token")
                    self.assertEqual(len(w.handles),1)
                    self.assertEqual(next(iter(w.handles.values()))[0],"token")
                    self.assertFalse(w.impersonated)
                    if body_mode!="ok":self.assertIs(caught.exception,body)
                    self.assertTrue(any(note.startswith("cleanup_unknown:")
                                        for note in getattr(caught.exception,"__notes__",())))

    def test_recovery_work_budget_is_one_deadline_not_reset_per_command(self):
        clock={"now":180.999};budgets=[]
        self.n.recovery_deadline=185999
        def worker(store,kind,*,budget_ms):
            budgets.append(budget_ms);clock["now"]+=3;return {"modeled":True}
        with patch.object(native.time,"monotonic",lambda:clock["now"]),patch.object(native,"run_fixed",worker):
            self.n._run(self.store,"get")
            with self.assertRaises(native.Failure):self.n._run(self.store,"get")
            with self.assertRaises(native.Failure):self.n._run(self.store,"delete")
        self.assertEqual(budgets,[5000,2000])
        self.assertEqual(self.n.recovery_deadline,185999)

    def test_real_admin_recovery_deadline_starts_before_reopen_validation(self):
        clock={"now":180.999}
        admin_module=importlib.import_module("scripts.windows_positive_loopback_admin")
        def reopen_storage(root):
            self.assertEqual(root,self.store.root);clock["now"]+=31;return self.store
        with patch.object(native.time,"monotonic",lambda:clock["now"]),patch.object(native,"Store",reopen_storage):
            with self.assertRaises(native.Failure) as caught:admin_module.Admin.recover(self.store.root)
        self.assertEqual(caught.exception.args,("recovery_deadline",))
        self.assertTrue(self.store.closed)

    def source_tree(self,mode):
        source=MODEL/"source/Lib";self.store.files["sample.py"]=b"abc"
        state={"walks":0};original_read=self.store.w.read
        def walk(root,*args,**options):
            state["walks"]+=1
            if mode=="count":
                for index in range(10001):yield str(source/("directory-"+str(index))),[],[]
                return
            names=["sample.py"]
            if mode=="directory_drift" and state["walks"]>=3:names.append("added.py")
            yield str(source),[],names
            if mode=="enumeration_error":options["onerror"](OSError("modeled denied child"))
        def lstat(path,*args,**options):
            return N(st_size=3 if path.name=="sample.py" else 0,st_mode=0,
                     st_file_attributes=0x400 if mode=="reparse" and path==source else 0)
        def read(handle,limit):
            if mode=="file_drift" and state["walks"]>=3:return b"xyz"
            return original_read(handle,limit)
        with patch.object(native.os,"walk",walk),patch.object(Path,"lstat",lstat),patch.object(
            Path,"resolve",lambda path,*args,**options:path),patch.object(self.store.w,"read",read):
            return self.n._source_tree(self.store,source,"runtime/Lib",1000)

    def test_source_tree_double_enumeration_and_file_reread_preserve_full_copy(self):
        import hashlib
        records=self.source_tree("ok")
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]["path"],"runtime/Lib/sample.py")
        self.assertEqual(records[0]["sha256"],hashlib.sha256(b"abc").hexdigest())
        self.assertEqual(self.store.w.handles,{})

    def test_native_copy_and_source_tree_owners_attempt_all_preserve_body(self):
        for owner in ("copy_file","source_tree"):
            for failed_index in ((0,1) if owner=="copy_file" else (0,1,3)):
                for body_failed in (False,True):
                    with self.subTest(owner=owner,failed_index=failed_index,body_failed=body_failed):
                        self.store=NativeStore();w=self.store.w;allocated=[];attempted=[];failed=[]
                        body=native.Failure("modeled_"+owner+"_body")
                        original_allocate=w._handle;original_close=w.close
                        def allocate(kind,value):
                            handle=original_allocate(kind,value)
                            if (owner=="copy_file" and kind=="file") or (owner=="source_tree" and kind=="route"):
                                allocated.append(handle)
                            return handle
                        def close(handle):
                            if handle in allocated:
                                attempted.append(handle)
                                if allocated.index(handle)==failed_index and not failed:
                                    failed.append(handle);raise native.Failure("modeled_owner_close")
                            return original_close(handle)
                        w._handle=allocate;w.close=close
                        if body_failed:
                            def write(*args):raise body
                            w.write=write
                        with self.assertRaises(native.Failure) as caught:
                            if owner=="source_tree":self.source_tree("ok")
                            else:
                                self.store.files["sample.py"]=b"abc"
                                with patch.object(Path,"lstat",lambda *a,**k:N(st_size=3,st_file_attributes=0,st_mode=0)),patch.object(
                                    Path,"stat",lambda *a,**k:N(st_size=3)),patch.object(Path,"resolve",lambda path,*a,**k:path):
                                    self.n._copy_file(self.store,Path("/source/sample.py"),"trusted/sample.py")
                        self.assertEqual(set(w.handles),set(failed),"each owned source/output/pin must be independently attempted")
                        self.assertEqual(len(attempted),len(set(attempted)))
                        if body_failed:self.assertIs(caught.exception,body)
                        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def test_native_process_job_owners_release_both_and_preserve_body(self):
        for owner in ("verify_parent","stop_parent_job","reap_commands"):
            for failed_kind in ("job","process"):
                for body_failed in (False,True):
                    with self.subTest(owner=owner,failed_kind=failed_kind,body_failed=body_failed):
                        self.store=NativeStore();w=self.store.w
                        if owner=="reap_commands":self.ready()
                        acquired=[];attempted=[];failed=[];body=native.Failure("modeled_"+owner+"_body")
                        original_allocate=w._handle;original_close=w.close
                        def allocate(kind,value):
                            handle=original_allocate(kind,value)
                            if kind in ("job","process"):acquired.append(handle)
                            return handle
                        def close(handle):
                            if handle in acquired:
                                attempted.append(handle)
                                if w.handles[handle][0]==failed_kind and not failed:
                                    failed.append(handle);raise native.Failure("modeled_pair_close")
                            return original_close(handle)
                        w._handle=allocate;w.close=close
                        if body_failed:
                            def fault(*args):raise body
                            if owner=="verify_parent":w.IsProcessInJob=fault
                            else:w.TerminateJobObject=fault
                        clock=[180.999]
                        def now():clock[0]+=0.01;return clock[0]
                        with patch.object(native.time,"monotonic",now),self.assertRaises(native.Failure) as caught:
                            getattr(self.n,owner)(self.store)
                        self.assertTrue(acquired)
                        self.assertEqual(set(attempted),set(acquired),"job close failure must not skip held parent/process")
                        self.assertEqual(set(w.handles),set(failed))
                        if body_failed:self.assertIs(caught.exception,body)
                        self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def test_attach_parent_failure_still_reaps_and_closes_each_acquired_resource(self):
        for cleanup in ("process_close","job_close","terminate","wait"):
            with self.subTest(cleanup=cleanup):
                self.store=NativeStore();w=self.store.w
                self.store.data.update(phase="prepared",bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
                self.store.flush();body=native.Failure("modeled_attach_body")
                acquired=[];attempted=[];cleanup_events=[];original_allocate=w._handle;original_close=w.close
                def allocate(kind,value):
                    handle=original_allocate(kind,value)
                    if kind in ("job","process"):acquired.append(handle)
                    return handle
                def job(security,name):w.jobs[name]=[];return w._handle("job",name)
                def assign(*args):raise body
                original_terminate=w.TerminateJobObject
                def terminate(job,code):
                    cleanup_events.append("terminate")
                    if cleanup=="terminate":raise native.Failure("modeled_terminate_cleanup")
                    return original_terminate(job,code)
                def terminate_process(handle,code):
                    cleanup_events.append("terminate")
                    if cleanup=="terminate":raise native.Failure("modeled_terminate_cleanup")
                    w.processes[w.handles[handle][1]]["alive"]=False;return 1
                original_wait=w.WaitForSingleObject
                def wait(handle,milliseconds):
                    if milliseconds==2000:
                        cleanup_events.append("wait")
                        if cleanup=="wait":raise native.Failure("modeled_wait_cleanup")
                    return original_wait(handle,milliseconds)
                def close(handle):
                    if handle in acquired:
                        attempted.append(handle)
                        kind=w.handles[handle][0]
                        if cleanup==kind+"_close":raise native.Failure("modeled_attach_close")
                    return original_close(handle)
                w._handle=allocate;w.close=close;w.CreateJobObjectW=job
                w.SetInformationJobObject=lambda *args:1;w.AssignProcessToJobObject=assign
                w.TerminateJobObject=terminate;w.TerminateProcess=terminate_process;w.WaitForSingleObject=wait
                with self.assertRaises(native.Failure) as caught:self.n.attach_parent(self.store,1234)
                self.assertEqual(set(attempted),set(acquired),"failed termination/wait/first close cannot strand other owned handles")
                self.assertIn("terminate",cleanup_events)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def attach_case(self,stage,*,failures=()):
        self.store=NativeStore();w=self.store.w
        self.store.data.update(phase="prepared",bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
        self.store.flush();w.jobs={}
        w.processes[4321]=dict(created=9876,alive=True,user=self.store.boot["account_sid"])
        w.processes[9999]=dict(created=1111,alive=True,user="S-1-5-21-1-2-3-9999")
        state=dict(events=[],acquired=[],body=native.Failure("modeled_attach_"+stage))
        original_allocate=w._handle;original_close=w.close;original_wait=w.WaitForSingleObject
        original_terminate=w.TerminateJobObject;original_user=w.process_user;original_created=w.process_created
        original_inside=w.IsProcessInJob;inside_calls=[0]
        def allocate(kind,value):
            handle=original_allocate(kind,value)
            if kind in ("process","job"):state["acquired"].append(handle)
            return handle
        def job(security,name):w.jobs[name]=[];return w._handle("job",name)
        def assign(job,process):
            state["events"].append("assign")
            if stage in ("unassigned","assign_exited"):
                if stage=="assign_exited":w.processes[w.handles[process][1]]["alive"]=False
                raise state["body"]
            members=(w.handles[process][1],) if stage=="transferred" else (w.handles[process][1],4321)
            w.jobs[w.handles[job][1]].extend(members);return 1
        def inside(*args):
            inside_calls[0]+=1
            if stage=="assigned" and inside_calls[0]==1:raise state["body"]
            return original_inside(*args)
        def terminate_job(job,code):
            state["events"].append("terminate_job")
            if "terminate_job" in failures:raise native.Failure("modeled_job_terminate_cleanup")
            return original_terminate(job,code)
        def terminate_process(process,code):
            state["events"].append("terminate_process")
            if "terminate_process" in failures:raise native.Failure("modeled_process_terminate_cleanup")
            w.processes[w.handles[process][1]]["alive"]=False;return 1
        def wait(handle,milliseconds):
            if milliseconds==0 and stage=="wait":return 0xffffffff
            if milliseconds==2000:
                state["events"].append("wait")
                if "wait" in failures:raise native.Failure("modeled_attach_wait_cleanup")
            return original_wait(handle,milliseconds)
        def user(handle):
            if stage=="token":raise state["body"]
            return original_user(handle)
        def created(handle):
            if stage=="creation":raise state["body"]
            if stage=="creation_zero":return 0
            if stage=="creation_bool":return True
            if stage=="creation_overflow":return 1<<64
            return original_created(handle)
        def close(handle):
            handle=handle.value if hasattr(handle,"value") else handle
            if handle in state["acquired"]:
                kind=w.handles[handle][0];state["events"].append("close_"+kind)
                if "close_"+kind in failures:raise native.Failure("modeled_attach_"+kind+"_close")
            return original_close(handle)
        if stage=="sid":w.processes[1234]["user"]="S-1-5-21-1-2-3-9999"
        if stage=="exited":w.processes[1234]["alive"]=False
        w._handle=allocate;w.close=close;w.CreateJobObjectW=job
        w.SetInformationJobObject=lambda *args:1;w.AssignProcessToJobObject=assign
        w.IsProcessInJob=inside;w.TerminateJobObject=terminate_job;w.TerminateProcess=terminate_process
        w.WaitForSingleObject=wait;w.process_user=user;w.process_created=created
        if stage=="transferred":
            def readonly_failure(*args):raise state["body"]
            self.n.readonly_prepare=readonly_failure
        with self.assertRaises(native.Failure) as caught:self.n.attach_parent(self.store,1234)
        state["error"]=caught.exception
        return state

    def test_attach_unverified_identity_is_closed_but_never_terminated(self):
        for stage in ("sid","token","wait","exited","creation",
                      "creation_zero","creation_bool","creation_overflow"):
            with self.subTest(stage=stage):
                state=self.attach_case(stage)
                self.assertEqual(self.store.w.handles,{})
                self.assertFalse(any(event.startswith("terminate_") for event in state["events"]),
                                 "held handle does not authorize killing an unverified PID")
                self.assertEqual(self.store.w.processes[1234]["alive"],stage!="exited")
                self.assertTrue(self.store.w.processes[9999]["alive"])
                if stage in ("token","creation"):self.assertIs(state["error"],state["body"])
                elif not stage.startswith("creation_"):self.assertEqual(state["error"].args,("parent_identity",))

    def test_attach_authenticated_but_unassigned_parent_is_directly_reaped(self):
        state=self.attach_case("unassigned")
        self.assertEqual(self.store.w.handles,{})
        self.assertIs(state["error"],state["body"])
        self.assertFalse(self.store.w.processes[1234]["alive"],"empty Job termination cannot reap an unassigned parent")
        self.assertIn("terminate_process",state["events"])
        self.assertIn("wait",state["events"])
        self.assertTrue(self.store.w.processes[4321]["alive"])
        self.assertTrue(self.store.w.processes[9999]["alive"])

    def test_attach_assigned_parent_is_reaped_through_actual_job_members_only(self):
        state=self.attach_case("assigned")
        self.assertIs(state["error"],state["body"])
        self.assertFalse(self.store.w.processes[1234]["alive"])
        self.assertFalse(self.store.w.processes[4321]["alive"])
        self.assertTrue(self.store.w.processes[9999]["alive"])
        self.assertTrue(all(not members for members in self.store.w.jobs.values()))
        self.assertIn("terminate_job",state["events"])
        self.assertNotIn("terminate_process",state["events"])
        self.assertEqual(self.store.w.handles,{})

    def test_attach_assign_failure_already_exited_needs_no_blind_termination(self):
        state=self.attach_case("assign_exited")
        self.assertIs(state["error"],state["body"])
        self.assertFalse(self.store.w.processes[1234]["alive"])
        self.assertFalse(any(event.startswith("terminate_") for event in state["events"]),
                         "held-handle signaled exit needs no speculative termination")
        self.assertTrue(self.store.w.processes[4321]["alive"])
        self.assertTrue(self.store.w.processes[9999]["alive"])
        self.assertEqual(self.store.w.handles,{})

    def test_attach_unassigned_multiple_cleanup_failures_attempt_all_keep_body(self):
        state=self.attach_case("unassigned",failures=("terminate_process","wait","close_process","close_job"))
        self.assertIs(state["error"],state["body"])
        self.assertTrue(self.store.w.processes[1234]["alive"],"failed termination must remain unknown, not reaped")
        for event in ("terminate_process","wait","close_process","close_job"):
            self.assertIn(event,state["events"],"one cleanup failure must not skip an independent attempt")
        self.assertEqual(len(self.store.w.handles),2)
        self.assertTrue(any(note.startswith("cleanup_unknown:") for note in getattr(state["error"],"__notes__",())))

    def test_attach_post_transfer_failure_leaves_reclamation_to_store_owner(self):
        state=self.attach_case("transferred")
        self.assertIs(state["error"],state["body"])
        self.assertTrue(self.store.w.processes[1234]["alive"])
        self.assertFalse(any(event.startswith("terminate_") for event in state["events"]))
        self.assertEqual(set(self.store.w.handles),set(state["acquired"]))
        self.assertEqual(set(self.store.handles),set(state["acquired"]))
        self.store.close()
        self.assertEqual(self.store.w.handles,{})

    def test_native_single_handle_owners_preserve_body_on_release_failure(self):
        for owner in ("_process","_outer","parent_only","readonly_prepare","_tool",
                      "verify_store_directory","verify_store_file","verify_store_image","_derived"):
            with self.subTest(owner=owner):
                self.store=NativeStore();w=self.store.w;body=native.Failure("modeled_"+owner+"_body")
                active=[False];attempted=[];original_close=w.close
                def fault(*args,**options):active[0]=True;raise body
                def close(handle):
                    if active[0]:attempted.append(handle);raise native.Failure("modeled_single_close")
                    return original_close(handle)
                w.close=close
                if owner=="_process":w.process_created=fault
                elif owner=="_outer":w.verify_security=fault
                elif owner=="parent_only":
                    original_query=w.job_pids;queries=[0]
                    def query(handle):
                        queries[0]+=1
                        if queries[0]==2:return fault()
                        return original_query(handle)
                    w.job_pids=query
                elif owner=="readonly_prepare":
                    self.store.data["readonly_prepare"]=None;w.observe_security=fault
                elif owner=="_tool":w.read=fault
                elif owner=="_derived":
                    w.IsValidSid=fault
                    def free(pointer):attempted.append(pointer.value);raise native.Failure("modeled_sid_free")
                    w.FreeSid=free
                else:
                    original_info=w.info;original_read=w.read
                    def info(handle,**options):
                        if owner=="verify_store_directory" and handle in w.handles and w.handles[handle][0]=="route":return fault()
                        return original_info(handle,**options)
                    def read(handle,size):
                        if handle in w.handles:
                            path=Path(w.handles[handle][1])
                            if ((owner=="verify_store_file" and path.name=="windows_positive_loopback_full_get.py") or
                                (owner=="verify_store_image" and path.name=="CheckNetIsolation.exe")):return fault()
                        return original_read(handle,size)
                    w.info=info;w.read=read
                with self.assertRaises(native.Failure) as caught:
                    if owner=="_process":self.n._process(self.store,self.store.data["parent"])
                    elif owner=="_outer":self.n._outer(self.store)
                    elif owner=="_derived":self.n._derived(w,self.store.data["profile_names"][0])
                    elif owner.startswith("verify_store"):self.n.verify_store(self.store)
                    else:getattr(self.n,owner)(self.store)
                self.assertTrue(active[0],"case must enter intended owner's actual body")
                self.assertTrue(attempted)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_source_tree_pin_is_owned_before_identity_query_can_fail(self):
        w=self.store.w;body=native.Failure("modeled_pin_info_body");attempted=[]
        original_info=w.info;original_close=w.close
        def info(handle,**options):
            if handle in w.handles and w.handles[handle][0]=="route":raise body
            return original_info(handle,**options)
        def close(handle):attempted.append(handle);return original_close(handle)
        with patch.object(w,"info",info),patch.object(w,"close",close):
            with self.assertRaises(native.Failure) as caught:self.source_tree("ok")
        self.assertTrue(attempted,"pin acquired before info must be registered for cleanup")
        self.assertEqual(w.handles,{})
        self.assertIs(caught.exception,body)

    def test_canary_request_and_public_file_close_failures_preserve_original_body(self):
        for stage in ("request","public"):
            with self.subTest(stage=stage):
                self.store=NativeStore();w=self.store.w;body=native.Failure("modeled_canary_file_body")
                self.store.files.update({"readonly-request.canary":b"","readonly-public.canary":b"public",
                                         "readonly-private.canary":b"private"})
                original_close=w.close;attempted=[]
                def close(handle):
                    handle=handle.value if hasattr(handle,"value") else handle
                    attempted.append(w.handles[handle][0])
                    kind,value=w.handles[handle]
                    if kind=="file" and Path(value).name=="readonly-"+stage+".canary":
                        raise native.Failure("modeled_canary_file_close")
                    return original_close(handle)
                w.close=close
                if stage=="request":
                    def write(*args):raise body
                    w.WriteFile=write
                else:
                    def read(*args):raise body
                    w.read=read
                with self.assertRaises(native.Failure) as caught:self.n._canaries(self.store,123)
                self.assertEqual(attempted.count("token"),2)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_native_lifecycle_store_close_does_not_replace_freeze_reopen_prepare_body(self):
        for owner in ("freeze","reopen","prepare"):
            with self.subTest(owner=owner):
                self.store=NativeStore();w=self.store.w;body=native.Failure("modeled_"+owner+"_body")
                closed=[];body_entered=[]
                def close():closed.append(True);raise native.Failure("modeled_lifecycle_close")
                self.store.close=close
                def fault(*args,**options):body_entered.append(True);raise body
                patches=[patch.object(native,"Store",lambda root:self.store)]
                if owner=="reopen":w.assert_admin=fault
                elif owner=="prepare":
                    self.store.data.update(phase="frozen",account_sid=None,bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
                    self.store.flush();w.LookupAccountNameW=fault
                else:
                    # Only OS/storage/runtime boundaries are modeled; Native.freeze
                    # and its actual trusted-context/account/path gates still run.
                    checkout=Path(policy.__file__).resolve(strict=True).parents[2]
                    patches=[patch.object(native,"Win32",lambda:w),
                        patch.object(native,"__file__",str(checkout/"scripts/preflight.py")),
                        patch.dict(native.os.environ,{"GITHUB_WORKSPACE":str(checkout)}),
                        patch.object(native.sys,"base_prefix",str(MODEL/"runtime")),
                        patch.object(native.sys,"executable",str(MODEL/"runtime/python.exe"))]
                    def lookup(system,name,sid,size,domain,domain_size,use):w.error=1332;return 0
                    w.LookupAccountNameW=lookup
                    def temporary(capacity,buffer):buffer.value=str(Path(tempfile.gettempdir()).resolve(strict=True));return len(buffer.value)
                    w.GetTempPathW=temporary
                    self.store.create_directory=fault
                    factory=N(create=lambda root,data:self.store)
                    patches.append(patch.object(native,"Store",factory))
                for item in patches:item.start()
                try:
                    with self.assertRaises(native.Failure) as caught:
                        if owner=="freeze":self.n.freeze(self.store.data["context"],self.store.data["account_name"])
                        elif owner=="prepare":self.n.prepare(self.store.root,self.store.boot["account_sid"])
                        else:self.n.reopen(self.store.root)
                finally:
                    for item in reversed(patches):item.stop()
                self.assertTrue(closed)
                self.assertTrue(body_entered,"case must actually raise intended lifecycle body before cleanup")
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_prepare_root_and_socket_cleanup_keep_original_body_and_close_store(self):
        for stage in ("root_dacl","socket_bind"):
            with self.subTest(stage=stage):
                self.store=NativeStore();w=self.store.w;body=native.Failure("modeled_prepare_"+stage)
                self.store.data.update(phase="frozen",account_sid=None,bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
                self.store.flush();attempted=[];original_close=w.close;active=[False]
                def store_close():attempted.append("store");raise native.Failure("modeled_prepare_store_close")
                self.store.close=store_close
                def dacl(*args):
                    if stage=="root_dacl":active[0]=True;raise body
                w.set_root_dacl=dacl
                def close(handle):
                    attempted.append("root")
                    if stage=="root_dacl" and active[0]:raise native.Failure("modeled_root_close")
                    return original_close(handle)
                w.close=close
                class Socket:
                    def __enter__(self):return self
                    def __exit__(self,*args):self.close()
                    def setsockopt(self,*args):pass
                    def bind(self,*args):raise body
                    def close(self):attempted.append("socket");raise native.Failure("modeled_socket_close")
                with patch.object(native,"Store",lambda root:self.store),patch.object(native.socket,"socket",lambda *a:Socket()),patch.object(
                    native.socket,"SO_EXCLUSIVEADDRUSE",-5,create=True):
                    with self.assertRaises(native.Failure) as caught:self.n.prepare(self.store.root,self.store.boot["account_sid"])
                self.assertIn("store",attempted)
                self.assertIn("root" if stage=="root_dacl" else "socket",attempted)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_prepare_socket_creation_oserror_becomes_bounded_loopback_failure(self):
        for family,category in (("AF_INET","loopback_socket4"),("AF_INET6","loopback_socket6")):
            with self.subTest(family=family):
                self.store=NativeStore()
                self.store.data.update(phase="frozen",account_sid=None,bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
                self.store.flush()
                self.store.w.set_root_dacl=lambda *args:None
                boom=OSError(10106,"modeled provider init")
                calls=[]
                def broken(f,*a,**k):
                    calls.append(f)
                    if f==getattr(native.socket,family):raise boom
                    class Good:
                        def setsockopt(self,*args):pass
                        def bind(self,*args):pass
                        def getsockname(self):return ("127.0.0.1" if f==native.socket.AF_INET else "::1",5000)
                        def close(self):pass
                    return Good()
                with patch.object(native,"Store",lambda root:self.store),patch.object(
                    native.socket,"socket",broken),patch.object(native.time,"sleep",lambda seconds:None):
                    with self.assertRaises(native.Failure) as caught:self.n.prepare(self.store.root,self.store.boot["account_sid"])
                self.assertEqual(str(caught.exception),category)
                self.assertIs(caught.exception.__cause__,boom)
                self.assertEqual(len(calls),3 if family=="AF_INET" else 4)

    def test_prepare_socket_creation_transient_failure_is_retried(self):
        self.store=NativeStore()
        self.store.data.update(phase="frozen",account_sid=None,bootstrap=None,parent=None,outer_job=None,readonly_prepare=None)
        self.store.flush()
        self.store.w.set_root_dacl=lambda *args:None
        boom=OSError(10106,"modeled provider init")
        calls=[]
        def flaky(f,*a,**k):
            calls.append(f)
            if len(calls)==1:raise boom
            class Good:
                def setsockopt(self,*args):pass
                def bind(self,*args):pass
                def getsockname(self):return ("127.0.0.1",5000)
                def close(self):pass
            return Good()
        sleeps=[]
        with patch.object(native,"Store",lambda root:self.store),patch.object(
            native.socket,"socket",flaky),patch.object(native.time,"sleep",lambda seconds:sleeps.append(seconds)):
            self.n.prepare(self.store.root,self.store.boot["account_sid"])
        self.assertEqual(len(calls),3)
        self.assertEqual(sleeps,[0.2])

    def test_source_tree_enumeration_reparse_membership_file_drift_count_reject_and_close(self):
        for mode in ("enumeration_error","reparse","directory_drift","file_drift","count"):
            self.store=NativeStore()
            with self.subTest(mode=mode),self.assertRaises(native.Failure):self.source_tree(mode)
            with self.subTest(mode=mode):self.assertEqual(self.store.w.handles,{})

    def test_system_image_hardlinks_are_role_scoped_and_bad_shape_rejected(self):
        path=self.store.w.system_directory/"CheckNetIsolation.exe"
        info=self.n._image_info(self.store,99,path)
        self.assertEqual(info,dict(identity=[7,1],links=2,attributes=0,size=256))
        with self.assertRaises(native.Failure):self.n._image_info(self.store,99,self.store.root/"private.exe")
        for attributes,links,index in ((0x400,2,1),(0x10,2,1),(0,0,1),(0,2,0)):
            def query(handle,output):
                value=c.cast(output,c.POINTER(native.abi.FILE_INFO)).contents
                value.attributes=attributes;value.links=links;value.volume=7;value.index_low=index;return 1
            with patch.object(self.store.w,"GetFileInformationByHandle",query):
                with self.subTest(attributes=attributes,links=links,index=index),self.assertRaises(native.Failure):
                    self.n._image_info(self.store,99,path)

    def tool(self,mode):
        import struct
        raw=bytearray(256);raw[:2]=b"MZ";raw[60:64]=(64).to_bytes(4,"little")
        raw[64:68]=b"PE\0\0";raw[68:70]=(0xAA64 if mode=="wrong_arch" else 0x8664).to_bytes(2,"little")
        self.store.files["CheckNetIsolation.exe"]=bytes(raw)
        words=[0xFEEF04BD,0x10000,10<<16,(1<<16)|2,10<<16,(1<<16)|3,0,0,0,1,0,0,0]
        if mode=="bad_magic":words[0]=0
        if mode=="bad_type":words[9]=0
        class Function:
            def __init__(self,body):self.body=body
            def __call__(self,*args):return self.body(*args)
        def read_version(path,handle,size,buffer):c.memmove(buffer,struct.pack("<13I",*words),52);return 1
        def query(buffer,subkey,pointer,count):
            put(pointer,c.c_void_p,c.addressof(buffer)+(52 if mode=="version_pointer" else 0))
            put(count,t.UINT,52);return 1
        version=N(GetFileVersionInfoSizeW=Function(lambda *args:51 if mode=="version_size" else 52),
                  GetFileVersionInfoW=Function(read_version),VerQueryValueW=Function(query))
        def dll(path,**options):
            self.assertEqual((path,options.get("winmode")),(str(self.store.w.system_directory/"version.dll"),0x800))
            return version
        with patch.object(native.c,"WinDLL",dll,create=True):return self.n._tool(self.store)

    def test_image_provenance_accepts_system_executable_that_self_reports_vft_dll(self):
        path=self.store.w.system_directory/"CheckNetIsolation.exe"
        handle=self.store.w.CreateFileW(str(path),0x80020080)
        try:
            self.store.w.version_changes[path.name]={9:2}
            proof=self.n._image_provenance(self.store,handle,path,dll=False)
            self.assertEqual(proof["file_version"],[10,0,1,0])
            self.store.w.version_changes={}
            self.assertEqual(self.n._image_provenance(self.store,handle,path,dll=False)["file_version"],[10,0,1,0])
            for value in (0,3,4):
                self.store.w.version_changes[path.name]={9:value}
                with self.subTest(filetype=value),self.assertRaises(native.Failure) as caught:
                    self.n._image_provenance(self.store,handle,path,dll=False)
                self.assertEqual(str(caught.exception),"image_version_resource")
        finally:
            self.store.w.close(handle);self.store.w.version_changes={}

    def test_tool_reads_actual_pe_version_buffer_and_pins_exact_system_image(self):
        record=self.tool("ok")
        self.assertEqual(record["file_version"],[10,0,1,2])
        self.assertEqual(record["product_version"],[10,0,1,3])
        self.assertEqual(record["file_info"]["links"],2)
        self.assertEqual(record["machine"],0x8664)
        self.assertEqual(record["path"],str(self.store.w.system_directory/"CheckNetIsolation.exe"))
        self.assertEqual(len(self.store.handles),1)
        self.store.close();self.assertEqual(self.store.w.handles,{})

    def test_shared_dll_real_proof_and_durable_image_hash_version_drift_reject(self):
        path=self.store.w.system_directory/"kernel32.dll"
        self.store.files[path.name]=image_bytes(dll=True)
        handle=self.store.w.CreateFileW(str(path),0x80020080)
        try:
            proof=self.n._image_provenance(self.store,handle,path,dll=True)
            self.assertEqual(proof["file_info"]["size"],len(self.store.files[path.name]))
            self.assertEqual(proof["machine"],0x8664)
            for mode in ("not_dll","unknown_machine","wrong_version_type","bad_magic"):
                self.store.files[path.name]=image_bytes(dll=mode!="not_dll")
                self.store.w.version_changes={}
                if mode=="unknown_machine":
                    raw=bytearray(self.store.files[path.name]);raw[68:70]=(0xffff).to_bytes(2,"little")
                    self.store.files[path.name]=bytes(raw)
                elif mode=="wrong_version_type":self.store.w.version_changes[path.name]={9:0}
                elif mode=="bad_magic":self.store.files[path.name]=b"NO"+self.store.files[path.name][2:]
                with self.subTest(mode=mode),self.assertRaises(native.Failure):
                    self.n._image_provenance(self.store,handle,path,dll=True)
        finally:self.store.w.close(handle)
        self.store.w.version_changes={}
        self.n.verify_store(self.store)
        original=self.store.files["CheckNetIsolation.exe"]
        self.store.files["CheckNetIsolation.exe"]=original[:-1]+b"x"
        with self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.files["CheckNetIsolation.exe"]=original
        self.store.w.version_changes["CheckNetIsolation.exe"]={3:2<<16}
        with self.assertRaises(native.Failure):self.n.verify_store(self.store)
        self.store.w.version_changes={}
        self.n.verify_store(self.store)
        self.assertEqual(self.store.w.handles,{})

    def test_system32_singlelink_image_cannot_downgrade_to_private_nullable_proof(self):
        path=self.store.w.system_directory/"kernel32.dll"
        self.store.files[path.name]=image_bytes(dll=True)
        original_query=self.store.w.GetFileInformationByHandle
        def singlelink(handle,output):
            result=original_query(handle,output)
            if self.store.w.handles.get(handle)==("file",str(path)):
                c.cast(output,c.POINTER(native.abi.FILE_INFO)).contents.links=1
            return result
        with patch.object(self.store.w,"GetFileInformationByHandle",singlelink):
            handle=self.store.w.CreateFileW(str(path),0x80020080)
            try:proof=self.n._image_provenance(self.store,handle,path,dll=True)
            finally:self.store.w.close(handle)
            row=dict(path=str(path),identity=proof["file_info"]["identity"],
                security=self.store.w.observe_security(1),effective=self.store.w.effective_access(1,123),
                file_info=proof["file_info"],provenance=proof)
            self.store.data["readonly_prepare"]["loader_images"]=[row]
            self.store.flush();self.n.verify_store(self.store)
            row["file_info"]=None;row["provenance"]=None
            self.store.flush()
            # Same admitted System32 pathname and single-link OS identity;
            # nullable record fields cannot choose the private-frozen role.
            with self.subTest(boundary="admission"),self.assertRaises(native.Failure):
                native.admission(self.store.data["readonly_prepare"],self.store.data["context"]["matrix"],
                    private_images=[self.store.root/item["path"] for item in self.store.data["frozen_files"]],
                    system_directory=self.store.w.system_directory)
            self.store.files[path.name]=b"NO"+self.store.files[path.name][2:]
            with self.subTest(boundary="verify_store"),self.assertRaises(native.Failure):
                self.n.verify_store(self.store)
        self.assertEqual(self.store.w.handles,{})

    def test_tool_architecture_version_size_pointer_signature_and_type_reject_without_leak(self):
        for mode in ("wrong_arch","version_size","version_pointer","bad_magic","bad_type"):
            self.store=NativeStore()
            with self.subTest(mode=mode),self.assertRaises(native.Failure):self.tool(mode)
            self.store.close()
            with self.subTest(mode=mode):self.assertEqual(self.store.w.handles,{})

    def abi_observation(self):
        # Synthetic host-layout observation for parser tests only. The actual
        # Windows SDK executable remains a separate x64/ARM64 native gate.
        a=native.abi
        names={"SA":a.SA,"FILE_INFO":a.FILE_INFO,"STARTUP":a.STARTUP,"STARTUP_EX":a.STARTUP_EX,
            "PROCESS":a.PROCESS,"TOKEN_USER":a.TOKEN_USER,"GENERIC_MAPPING":a.GENERIC_MAPPING,
            "EXTENDED_LIMITS":a.EXTENDED_LIMITS}
        value=dict(schema=1,machine="x64",DWORD=c.sizeof(t.DWORD),BOOL=c.sizeof(t.BOOL),
            FILETIME=c.sizeof(t.FILETIME),HANDLE=c.sizeof(t.HANDLE),
            sa_descriptor=a.SA.descriptor.offset,file_volume=a.FILE_INFO.volume.offset,
            file_links=a.FILE_INFO.links.offset,startup_stdin=a.STARTUP.stdin.offset,
            startup_attributes=a.STARTUP_EX.attributes.offset,process_pid=a.PROCESS.pid.offset,
            token_sid=a.TOKEN_USER.sid.offset,job_pid_list=8,job_list_attribute=0x2000D,
            calling_convention_verified=True,owned_buffer_freed=True)
        value.update({name:c.sizeof(kind) for name,kind in names.items()})
        extra={"IO":a.IO,"LIMITS":a.LIMITS,"FILETIME":t.FILETIME,"SID_AND_ATTRIBUTES":native.SID_AND_ATTRIBUTES}
        layout=dict(WORD=c.sizeof(t.WORD),LONG=c.sizeof(t.LONG),ULONG_PTR=c.sizeof(c.c_size_t),
                    IO=c.sizeof(a.IO),LIMITS=c.sizeof(a.LIMITS),SID_AND_ATTRIBUTES=c.sizeof(native.SID_AND_ATTRIBUTES))
        for name,kind in {**names,**extra}.items():
            layout.update({name+"."+field:getattr(kind,field).offset for field,_kind in kind._fields_})
        layout.update({"JOB_PID.assigned":0,"JOB_PID.count":4,"JOB_PID.pids":8});value["layout"]=layout
        return value

    def consume_abi(self,value):
        self.store.files["command-0.out"]=serialized(value)
        result=dict(output="command-0.out",reaped=True,timed_out=False,exit_code=0)
        with patch.object(native,"run_fixed",lambda store,kind:dict(result)):self.n._abi(self.store)

    def test_abi_real_python_consumer_checks_schema_and_pairs_descriptor_and_derived_sid_frees(self):
        self.consume_abi(self.abi_observation())
        self.assertEqual((self.store.w.descriptor_frees,self.store.w.sid_frees),(1,1))
        self.assertEqual((self.store.w.buffers,self.store.w.sid_buffers),({},{}))

    def test_abi_schema_flag_machine_width_and_offset_mutations_reject(self):
        original=self.abi_observation()
        cases=[]
        for key,value in (("schema",True),("machine","ARM64"),("calling_convention_verified",False),
                          ("owned_buffer_freed",False),("DWORD",4 if original["DWORD"]!=4 else 8)):
            changed=copy.deepcopy(original);changed[key]=value;cases.append(changed)
        for key in original["layout"]:
            changed=copy.deepcopy(original);changed["layout"][key]+=1;cases.append(changed)
        missing=copy.deepcopy(original);del missing["HANDLE"];cases.append(missing)
        for changed in cases:
            with self.subTest(changed=changed),self.assertRaises(native.Failure):self.consume_abi(changed)
        self.assertEqual((self.store.w.descriptor_frees,self.store.w.sid_frees),(0,0))

    def test_abi_python_get_process_times_failure_cannot_borrow_c_flag(self):
        with patch.object(self.store.w,"process_created",lambda handle:0):
            with self.assertRaises(native.Failure):self.consume_abi(self.abi_observation())
        self.assertEqual((self.store.w.descriptor_frees,self.store.w.sid_frees),(0,0))


if __name__=="__main__":unittest.main()
