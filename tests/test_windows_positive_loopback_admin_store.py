"""Real Store algorithms over byte/identity model; no native filesystem proof."""
from __future__ import annotations
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

NAME="scripts.windows_positive_loopback_admin_store"
try:
    storage=importlib.import_module(NAME)
except ModuleNotFoundError as exc:
    if exc.name!=NAME: raise
    storage=None


class Files:
    def __init__(self):
        self.nodes={}; self.handles={}; self.next=100; self.events=[]
        self.replace_during_read=False; self.fail_write=False
    def open_file(self,path,descriptor,*,create=False,write=False,**options):
        name=Path(path).name
        if create:
            if name in self.nodes: raise RuntimeError("already exists")
            self.nodes[name]=dict(identity=(7,self.next),bytes=b"",descriptor=descriptor)
        if name not in self.nodes: raise RuntimeError("absent")
        node=self.nodes[name]
        if node["descriptor"]!=descriptor: raise RuntimeError("descriptor mismatch")
        handle=self.next; self.next+=1; self.handles[handle]=node
        self.events.append(("open",name,write))
        return handle,node["identity"]
    def read(self,handle,limit):
        node=self.handles[handle]
        if self.replace_during_read: node["identity"]=(8,999)
        if len(node["bytes"])>limit: raise RuntimeError("too large")
        return node["bytes"]
    def write(self,handle,value):
        node=self.handles[handle]; node["bytes"]=value
        self.events.append(("bytes",value))
        if self.fail_write: raise RuntimeError("modeled Flush failure")
        self.events.append(("durable",value))
    def info(self,handle,**options): return self.handles[handle]["identity"]
    def close(self,handle):
        self.events.append(("close",handle)); del self.handles[handle]


class TestAdminStore(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(storage,"new Store component absent; facility RED")
        self.store=storage.Store.__new__(storage.Store)
        self.store.root=Path("/model/icode-positive-admin-"+"1"*32)
        self.store.data=dict(schema=1,account_sid="S-1-5-21-1-2-3-1001",file_identities={})
        self.store.w=Files(); self.store.handles=[]; self.store.pins=[]

    def test_canonical_wire_real_decode_duplicate_nan_utf8_limits(self):
        value={"b":2,"a":1}
        self.assertEqual(storage.wire(value),b'{"a":1,"b":2}')
        self.assertEqual(storage.decode(storage.wire(value),100),value)
        for bad in (b"",b"x"*101,b"\xff",b'{"a":1,"a":2}',b'{"a":NaN}'):
            with self.subTest(bad=bad),self.assertRaises(storage.Failure):
                storage.decode(bad,100)

    def test_roles_exact_account_binding_and_private_default(self):
        private=self.store.file_descriptor("private")
        self.assertEqual(private,storage.PRIVATE)
        public=self.store.file_descriptor("public")
        request=self.store.file_descriptor("request")
        self.assertEqual(public,private+"(A;;FR;;;S-1-5-21-1-2-3-1001)")
        self.assertEqual(request,private+"(A;;0x120003;;;S-1-5-21-1-2-3-1001)")
        with self.assertRaises(storage.Failure): self.store.file_descriptor("execute")
        self.store.data["account_sid"]="S-1-5-18"
        with self.assertRaises(storage.Failure): self.store.file_descriptor("request")

    def test_create_write_read_real_bytes_and_identity_saved(self):
        self.store.write("bootstrap.json",b"first","public",create=True)
        identity=self.store.data["file_identities"]["bootstrap.json"]
        self.assertEqual(identity,[7,100])
        self.store.write("bootstrap.json",b"second","public")
        self.assertEqual(self.store.read("bootstrap.json",self.store.file_descriptor("public"),100),b"second")
        self.assertEqual(self.store.w.handles,{})
        self.assertEqual(self.store.w.nodes["bootstrap.json"]["bytes"],b"second")

    def test_replaced_file_before_write_or_during_read_rejects_and_closes_handle(self):
        self.store.write("receipt.json",b"valid","public",create=True)
        node=self.store.w.nodes["receipt.json"]
        node["identity"]=(7,999)
        with self.assertRaises(storage.Failure): self.store.write("receipt.json",b"forged","public")
        self.assertEqual(node["bytes"],b"valid")
        node["identity"]=tuple(self.store.data["file_identities"]["receipt.json"])
        self.store.w.replace_during_read=True
        with self.assertRaises(storage.Failure):
            self.store.read("receipt.json",self.store.file_descriptor("public"),100)
        self.assertEqual(self.store.w.handles,{})

    def test_flush_serializes_actual_data_and_propagates_durable_failure(self):
        self.store.w.nodes["ledger.json"]=dict(identity=(7,200),bytes=b"old",descriptor=storage.PRIVATE)
        self.store.data["file_identities"]["ledger.json"]=[7,200]
        self.store.flush()
        saved=json.loads(self.store.w.nodes["ledger.json"]["bytes"])
        self.assertEqual(saved,self.store.data)
        self.store.data["owned_intent"]=True; self.store.w.fail_write=True
        with self.assertRaises(RuntimeError): self.store.flush()
        self.assertEqual(self.store.w.handles,{})
        self.assertNotEqual(self.store.w.events[-2][0],"durable")

    def test_leaf_names_reject_paths_and_freeform_names(self):
        for name in ("../ledger.json","a/b","a\\b",".","..","",1,"x"*101):
            with self.subTest(name=name),self.assertRaises(storage.Failure): self.store._leaf(name)
        for name in ("ledger.json","profile_created.request","probe_finished.request"):
            self.store._leaf(name)

    def directory_model(self, root):
        # Real namespace existence; only the Win32 consumer boundary is modeled.
        # No exists() patch and no exists_ok: a duplicate leaf is never created.
        model=SimpleNamespace(created=[],trusted={root},handles={},next=700)
        def create(path,descriptor):
            self.assertEqual(descriptor,storage.PRIVATE)
            path.mkdir()
            model.created.append(path); model.trusted.add(path)
        def pin(path,**options):
            if path not in model.trusted: raise storage.Failure("untrusted_directory")
            handle=model.next; model.next+=1; model.handles[handle]=path
            return handle
        model.create_directory=create; model.pin_ancestor=pin
        def opened(path,descriptor,*,directory=False,**options):
            self.assertEqual(descriptor,storage.PRIVATE);self.assertTrue(directory)
            if path not in model.trusted or path.is_symlink() or path.resolve(strict=True)!=path:
                raise storage.Failure("untrusted_directory")
            handle=pin(path)
            return handle,(7,path.stat().st_ino)
        model.open_file=opened
        model.info=lambda handle,**options:(7,model.handles[handle].stat().st_ino)
        model.close=lambda handle:model.handles.pop(handle)
        self.store.root=root; self.store.w=model
        return model

    def test_freeze_nested_trusted_directory_sequence_uses_real_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(strict=True); model=self.directory_model(root)
            # Exact Native.freeze ordering, not a replacement FakeStore method.
            sequence=("trusted","trusted/scripts","trusted/src","trusted/src/icode")
            for relative in sequence:
                try:self.store.create_directory(relative)
                except storage.Failure as exc:
                    self.fail("Native.freeze nested directory chain rejected "+relative+": "+str(exc))
            expected=[root/name for name in sequence]
            self.assertEqual(model.created,expected)
            self.assertTrue(all(path.is_dir() for path in expected))
            self.assertEqual(set(self.store.pins),set(model.handles))
            self.assertTrue(self.store.pins,"admitted directory identities remain pinned until Store.close")
            self.store.close()
            self.assertEqual(model.handles,{})

    def test_directory_creation_still_rejects_existing_leaf_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(strict=True); model=self.directory_model(root)
            self.store.create_directory("trusted")
            with self.assertRaises(storage.Failure):self.store.create_directory("trusted")
            self.assertEqual(model.created,[root/"trusted"])
            self.store.close()
            self.assertEqual(model.handles,{})

    def test_directory_creation_rejects_preexisting_untrusted_ancestor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(strict=True); model=self.directory_model(root)
            (root/"foreign").mkdir()  # Not admitted by the private-directory model.
            with self.assertRaises(storage.Failure):self.store.create_directory("foreign/child")
            self.assertFalse((root/"foreign/child").exists())
            self.assertEqual(model.created,[])
            self.assertEqual(model.handles,{})

    def test_close_attempts_all_handles_even_when_one_release_fails(self):
        attempted=[]
        def close(handle):
            attempted.append(handle)
            if handle==2: raise storage.Failure("release failed")
        self.store.w=SimpleNamespace(close=close)
        self.store.handles=[1,2]; self.store.pins=[3,4]
        with self.assertRaises(storage.Failure): self.store.close()
        self.assertEqual(attempted,[2,1,4,3])
        self.assertEqual((self.store.handles,self.store.pins),([],[]))

    def test_store_file_owners_preserve_body_with_close_failure(self):
        for owner in ("flush","read","write"):
            with self.subTest(owner=owner):
                self.setUp();body=storage.Failure("modeled_store_"+owner)
                model=self.store.w;model.nodes["ledger.json"]=dict(identity=(7,200),bytes=b"{}",descriptor=storage.PRIVATE)
                self.store.data["file_identities"]["ledger.json"]=[7,200]
                attempted=[]
                def bad_close(handle):attempted.append(handle);raise storage.Failure("modeled_store_close")
                def bad_body(*args):raise body
                model.close=bad_close
                if owner=="read":model.read=bad_body
                else:model.write=bad_body
                with self.assertRaises(storage.Failure) as caught:
                    if owner=="flush":self.store.flush()
                    elif owner=="read":self.store.read("ledger.json",storage.PRIVATE,100)
                    else:self.store.write("ledger.json",b"new")
                self.assertEqual(len(attempted),1)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(body,"__notes__",())))

    def test_store_create_owned_file_and_pin_cleanup_attempts_all_preserves_body(self):
        for failed_kind in ("ledger.json","root","route"):
            for body_failed in (False,True):
                with self.subTest(failed_kind=failed_kind,body_failed=body_failed):
                    root=Path("/model/parent/icode-positive-admin-"+"1"*32)
                    acquired={};attempted=[];counter=[100];failed=[];body=storage.Failure("modeled_create_body")
                    def allocate(kind):
                        handle=counter[0];counter[0]+=1;acquired[handle]=kind;return handle
                    def opened(path,*args,**options):
                        handle=allocate("root" if options.get("directory") else Path(path).name)
                        return handle,(7,handle)
                    def close(handle):
                        if handle not in acquired:raise AssertionError("unowned/double close")
                        attempted.append(handle)
                        if acquired[handle]==failed_kind and not failed:
                            failed.append(handle);raise storage.Failure("modeled_create_close")
                        del acquired[handle]
                    def write(handle,value):
                        if body_failed and acquired[handle]=="ledger.json":raise body
                    model=SimpleNamespace(assert_admin=lambda:None,pin_ancestor=lambda *a,**k:allocate("route"),
                        create_directory=lambda *a:None,open_file=opened,write=write,close=close)
                    with patch.object(storage,"Win32",lambda:model):
                        with self.assertRaises(storage.Failure) as caught:
                            storage.Store.create(root,dict(schema=1,file_identities={}))
                    self.assertEqual(set(acquired),set(failed),"Store.create must attempt every independently owned pin")
                    self.assertEqual(len(attempted),len(set(attempted)))
                    if body_failed:self.assertIs(caught.exception,body)
                    self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def test_store_init_directory_and_close_owners_preserve_original_failure(self):
        for owner in ("init","directory","close"):
            with self.subTest(owner=owner):
                body=storage.Failure("modeled_"+owner+"_body");attempted=[];alive={}
                def allocate(kind):
                    handle=100+len(alive);alive[handle]=kind;return handle
                def close(handle):
                    attempted.append(handle)
                    if handle not in alive:raise AssertionError("unowned/double close")
                    if not hasattr(close,"failed"):
                        close.failed=True;raise body if owner=="close" else storage.Failure("modeled_close")
                    del alive[handle]
                if owner=="close":
                    self.store.handles=[allocate("file"),allocate("file")];self.store.pins=[allocate("pin")]
                    self.store.w=SimpleNamespace(close=close)
                    with self.assertRaises(storage.Failure) as caught:self.store.close()
                elif owner=="directory":
                    with tempfile.TemporaryDirectory() as temporary:
                        root=Path(temporary).resolve(strict=True);model=self.directory_model(root);original_info=model.info
                        def info(handle,**options):raise body
                        model.info=info;original_close=model.close
                        def fail_close(handle):attempted.append(handle);raise storage.Failure("modeled_directory_close")
                        model.close=fail_close
                        with self.assertRaises(storage.Failure) as caught:self.store.create_directory("one/two")
                        self.assertEqual(len(attempted),2)
                else:
                    root=Path(tempfile.gettempdir()).resolve(strict=True)/("icode-positive-admin-"+"1"*32)
                    def info(handle,**options):
                        if alive[handle]=="root":raise body
                        return (7,handle)
                    model=SimpleNamespace(assert_admin=lambda:None,
                        pin_ancestor=lambda path,**k:allocate("root" if path==root else "route"),
                        info=info,observe_security=lambda handle:{},close=close)
                    with patch.object(storage,"Win32",lambda:model),patch.object(Path,"resolve",lambda path,**k:path):
                        with self.assertRaises(storage.Failure) as caught:storage.Store(root)
                    self.assertEqual(len(alive),1)
                self.assertIs(caught.exception,body)
                self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def tree(self,source,names,*,enumeration_error=False,drift=False,reparse=None,clock=None,faults=None):
        model=SimpleNamespace(opened=0,written=0,closed=[],creates=[])
        def create_file(path,*args): model.opened+=1; return 501
        model.k=SimpleNamespace(CreateFileW=create_file)
        model.create_directory=lambda path,descriptor:model.creates.append(path)
        model.verify_ancestor=lambda handle:None
        calls={}
        def info(handle):
            calls[handle]=calls.get(handle,0)+1
            return (7,999 if drift and handle==501 and calls[handle]>1 else handle)
        model.info=info
        model.read=lambda handle,size:b""
        model.open_file=lambda *args,**options:(502,(7,502))
        def write(handle,value): model.written+=1
        model.write=write; model.close=lambda handle:model.closed.append(handle)
        if faults is not None:
            faults["model"]=model
            def release(handle):
                model.closed.append(handle)
                if handle==faults["failed"]:raise storage.Failure("modeled_copy_close")
            model.close=release
            if faults.get("body") is not None:
                def failed_write(*args):raise faults["body"]
                model.write=failed_write
        store=SimpleNamespace(root=self.store.root,w=model)
        def walk(root,topdown=True,followlinks=False,onerror=None):
            yield str(source),[],names
            if enumeration_error:
                if onerror is not None: onerror(OSError("modeled child scandir denied"))
                return
        def symlink(path):
            return path==reparse if reparse is not None else False
        def lstat(path,*args,**kwargs):
            return SimpleNamespace(st_size=0,st_file_attributes=0x400 if path==reparse else 0)
        stack=[patch.object(storage.os,"walk",walk),patch.object(Path,"is_symlink",symlink),
               patch.object(Path,"lstat",lstat)]
        if clock is not None:stack.append(patch.object(storage.time,"monotonic",side_effect=clock))
        for item in stack:item.start()
        try:
            result=storage.copy_private_tree(store,source,"runtime",deadline=1 if clock else 10**20)
            return result,model
        finally:
            for item in reversed(stack):item.stop()

    def test_copytree_child_enumeration_failure_rejects_partial_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary).resolve(strict=True)
            with self.assertRaises((OSError,storage.Failure)):
                self.tree(source,["normal.bin"],enumeration_error=True)

    def test_copytree_output_source_release_attempts_all_and_preserves_body(self):
        for failed in (502,501):
            for body_failed in (False,True):
                with self.subTest(failed=failed,body_failed=body_failed),tempfile.TemporaryDirectory() as temporary:
                    body=storage.Failure("modeled_copy_body") if body_failed else None
                    faults=dict(failed=failed,body=body)
                    with self.assertRaises(storage.Failure) as caught:self.tree(Path(temporary).resolve(strict=True),["normal.bin"],faults=faults)
                    self.assertEqual(faults["model"].closed,[502,501])
                    if body_failed:self.assertIs(caught.exception,body)
                    self.assertTrue(any(n.startswith("cleanup_unknown:") for n in getattr(caught.exception,"__notes__",())))

    def test_copytree_root_or_child_reparse_identity_drift_and_deadline_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary).resolve(strict=True)
            for reparse in (source,source/"child.bin"):
                with self.subTest(reparse=reparse),self.assertRaises(storage.Failure):
                    self.tree(source,["child.bin"],reparse=reparse)
            with self.assertRaises(storage.Failure):self.tree(source,["normal.bin"],drift=True)
            with self.assertRaises(storage.Failure):self.tree(source,["normal.bin"],clock=[0,2,2,2])

    def test_copytree_actual_count_ceiling_is_not_truncated_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary).resolve(strict=True)
            with self.assertRaises(storage.Failure):
                self.tree(source,[f"file-{index}.bin" for index in range(100001)])


if __name__=="__main__":
    unittest.main()
