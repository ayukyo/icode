import errno
import json
import os
import re
import unittest

SOURCE_NAMES=(
 "fork_exec_q","fork_exec_c","spawn_q","spawn_c","third_q","third_c",
 "refork_q","refork_c","grandchild_q","grandchild_c","pthread_q","pthread_c",
 "zombie_q","zombie_c","soft_q","soft_c","hard_q","hard_c",
 "hard_root_calibration","independent_q","independent_c","shared_counterexample",
 "migration_guard","migration_counterexample",
)
BASELINE_NAMES=("baseline_third","baseline_control")
SOURCE_CONFIGS=(
 (1,1,1,1,1,0),(1,0,1,1,1,0),(2,1,1,1,1,0),(2,0,1,1,1,0),
 (3,1,1,2,1,0),(3,0,1,2,1,0),(4,1,1,2,1,0),(4,1,0,2,1,0),
 (5,1,1,2,1,0),(5,0,1,2,1,0),(6,1,1,1,1,0),(6,0,1,1,1,0),
 (7,1,1,2,1,0),(7,0,1,2,1,0),(8,1,1,2,1,0),(8,0,1,2,1,0),
 (9,1,1,2,1,0),(9,0,1,2,1,0),(12,0,0,3,1,0),
 (10,1,1,2,2,0),(10,0,1,2,2,0),(10,1,1,2,2,1),
 (11,1,1,1,1,0),(11,1,1,1,2,1),
)
BASELINE_CONFIGS=((3,1,1,2,1,0),(3,0,1,2,1,0))
BEGIN=set("""kind version candidate_sha variant binary_sha256 profile_sha256 sandbox_exec_sha256
case_index case vector quota profile cap roots shared uid0 uid1 observer_pid observer_uid
arch os_build kernel observer_start_sec observer_start_usec deadline_ns""".split())
EVENT=set("""kind version case_index event slot other op pid ppid start_sec start_usec
uid euid gid egid saved_uid saved_gid count read group predicate current maximum rc error aux
independent_credentials live_count threads zombie_state fd3_errno fd4_errno canary_error canary_allowed""".split())
END=set("kind version case_index events roots_reaped remaining cleanup_scope retained".split())
ADMISSION=set("kind version case_index observer_uid consumed error second_forked".split())

def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key]=item
    return value

def need(condition,message):
    if not condition:
        raise ValueError(message)

def parse_vectors(raw,metadata):
    need(type(raw) is bytes and 0<len(raw)<=2*1024*1024 and raw.endswith(b"\n"),"raw bounds/LF")
    names=BASELINE_NAMES if metadata["variant"]=="baseline" else SOURCE_NAMES
    records=[]
    for line in raw.splitlines():
        need(0<len(line)<=4096,"line bound")
        row=json.loads(line,object_pairs_hook=unique)
        need(type(row) is dict,"row object")
        kind=row.get("kind")
        if kind=="begin":
            need(set(row)==BEGIN and type(row["version"]) is int and row["version"]==1,"begin schema")
            need(len(records)<len(names) and (not records or records[-1]["end"] is not None),"case nesting")
            need(type(row["case_index"]) is int and row["case_index"]==len(records)
                 and row["case"]==names[len(records)],"case order/count")
            for key in ("candidate_sha","variant","binary_sha256","arch","os_build","kernel","deadline_ns"):
                need(row[key]==metadata[key],"candidate/binary/OS mismatch")
            for key in ("binary_sha256","profile_sha256","sandbox_exec_sha256"):
                need(type(row[key]) is str and re.fullmatch("[0-9a-f]{64}",row[key]),"digest")
            need(type(row["observer_uid"]) is int and row["observer_uid"]==0
                 and type(row["observer_pid"]) is int and row["observer_pid"]>0,"observer")
            need(type(row["observer_start_sec"]) is int and row["observer_start_sec"]>0
                 and type(row["observer_start_usec"]) is int and row["observer_start_usec"]>=0
                 and type(row["deadline_ns"]) is int and 0<row["deadline_ns"]<2**64,"observer start/deadline")
            for key in ("vector","quota","profile","cap","roots","shared","uid0","uid1"):
                need(type(row[key]) is int,"begin integer")
            configs=BASELINE_CONFIGS if metadata["variant"]=="baseline" else SOURCE_CONFIGS
            need(tuple(row[k] for k in ("vector","quota","profile","cap","roots","shared"))==configs[len(records)],"fixed case configuration")
            need(row["quota"] in (0,1) and row["profile"] in (0,1) and row["shared"] in (0,1)
                 and row["roots"] in (1,2) and 1<=row["cap"]<=3,"case configuration")
            if row["vector"]!=12:
                need(60000<=row["uid0"]<61024,"UID range")
                if row["roots"]==2:
                    need(60000<=row["uid1"]<61024,"second UID")
                    need((row["uid0"]==row["uid1"])==bool(row["shared"]),"UID independence")
            records.append({"begin":row,"events":[],"admission":[],"end":None})
            continue
        need(records and records[-1]["end"] is None,"row outside case")
        record=records[-1]
        need(type(row.get("version")) is int and row["version"]==1
             and type(row.get("case_index")) is int
             and row["case_index"]==record["begin"]["case_index"],"row identity")
        if kind=="event":
            need(set(row)==EVENT,"event schema")
            need(all(type(row[k]) is int for k in EVENT-{"kind"}),"event integer")
            need(row["event"] in (1,2,3,4,5,6,7,8,100,101) and 0<=row["slot"]<8
                 and row["pid"]>0 and row["ppid"]>0 and row["start_sec"]>0
                 and row["start_usec"]>=0 and row["independent_credentials"]==1,"event identity")
            if record["begin"]["vector"]!=12:
                need(all(row[k]==row["uid"] for k in ("euid","gid","egid","saved_uid","saved_gid","group"))
                     and row["count"]==row["read"]==1 and row["predicate"]==0
                     and 60000<=row["uid"]<61024 and 1<=row["live_count"]<=8,"credential vector")
                if row["event"]!=100:
                    need(row["canary_allowed"]==1 and row["canary_error"] in ((errno.EPERM,errno.EACCES) if record["begin"]["profile"] else (0,)),"canary")
                if row["event"] not in (100,101):
                    need(row["fd3_errno"]==row["fd4_errno"]==errno.EBADF,"control FD closure")
            need(len(record["events"])<68,"event count")
            record["events"].append(row)
        elif kind=="admission":
            need(set(row)==ADMISSION and all(type(row[k]) is int for k in ADMISSION-{"kind"}),"admission schema")
            record["admission"].append(row)
        elif kind=="end":
            need(set(row)==END and all(type(row[k]) is int for k in ("version","case_index","events","roots_reaped","remaining"))
                 and type(row["events"]) is int
                 and row["events"]==len(record["events"]) and type(row["remaining"]) is int
                 and row["remaining"]==0 and row["roots_reaped"]==record["begin"]["roots"]
                 and row["cleanup_scope"]=="owned_roots_and_observed_direct_parent_reaps"
                 and row["retained"] is True,"end contract")
            record["end"]=row
        else:
            raise ValueError("unknown row")
    need(tuple(r["begin"]["case"] for r in records)==names
         and all(r["end"] is not None for r in records),"incomplete ledger")
    identities=[]
    for record in records:
        begin=record["begin"];events=record["events"]
        need(len(json.dumps(record).encode())<=65536,"case evidence bound")
        members={}
        for e in events:
            slot=e["slot"]
            if slot not in members:
                need(slot<begin["roots"] and e["event"] in (1,100),"unregistered member")
                members[slot]=(e["pid"],e["start_sec"],e["start_usec"])
            need(members[slot]==(e["pid"],e["start_sec"],e["start_usec"]),"member PID/start changed")
            if e["event"]==3:
                need(e["other"] not in members and e["rc"]>0 and e["error"]==0 and e["aux"]==1,"fork registration")
                # START supplies the already independently registered child's start tuple.
                children=[x for x in events if x["slot"]==e["other"] and x["event"]==1]
                need(len(children)==1 and children[0]["pid"]==e["rc"]
                     and children[0]["ppid"]==e["pid"],"child start/parent")
                child=children[0]
                members[e["other"]]=(child["pid"],child["start_sec"],child["start_usec"])
        starts=[e for e in events if e["event"]==1]
        need(len(starts)==len(members) and len({e["slot"] for e in starts})==len(starts),"start cardinality")
        done=[e for e in events if e["event"]==8]
        need(len({e["slot"] for e in done if e["slot"]<begin["roots"]})==begin["roots"],"roots done")
        reaped=[e["other"] for e in events if e["event"]==4]
        need(sorted(reaped)==sorted(set(members)-set(range(begin["roots"]))),"each descendant reaped once")
        if begin["vector"]!=12:
            identities.append(begin["uid0"])
            if begin["roots"]==2 and not begin["shared"]:
                identities.append(begin["uid1"])
        if begin["vector"]!=11 or begin["shared"]:
            need(not record["admission"],"unexpected admission")
        validate_creation_contract(record)
    need(len(identities)==len(set(identities)),"identity reused across cases")
    return {r["begin"]["case"]:r for r in records}

# Exact native creation contract: (parent slot, child slot, API op, succeeds).
# Per-parent order is fixed; independent root schedules may interleave.
CREATION_CONTRACT={
 "fork_exec_q":((0,2,1,False),),"fork_exec_c":((0,2,1,True),),
 "spawn_q":((0,2,2,False),),"spawn_c":((0,2,2,True),),
 "third_q":((0,2,1,True),(0,4,1,False)),
 "third_c":((0,2,1,True),(0,4,1,True)),
 "refork_q":((0,2,1,True),(0,4,1,True)),
 "refork_c":((0,2,1,True),(0,4,1,True)),
 "grandchild_q":((0,2,1,True),(2,4,1,False)),
 "grandchild_c":((0,2,1,True),(2,4,1,True)),
 "pthread_q":((0,2,1,False),),"pthread_c":((0,2,1,True),),
 "zombie_q":((0,2,1,True),(0,4,1,False),(0,6,1,True)),
 "zombie_c":((0,2,1,True),(0,4,1,True),(0,6,1,True)),
 "soft_q":((0,2,1,False),(0,4,1,True)),"soft_c":((0,2,1,True),),
 "hard_q":((0,2,1,True),),"hard_c":((0,2,1,True),),
 "hard_root_calibration":(),
 "independent_q":((0,2,1,True),(0,4,1,False),(1,3,1,True),(1,5,1,False)),
 "independent_c":((0,2,1,True),(0,4,1,True),(1,3,1,True),(1,5,1,True)),
 "shared_counterexample":((0,2,1,False),(1,3,1,False)),
 "migration_guard":(),"migration_counterexample":(),
 "baseline_third":((0,2,1,True),(0,4,1,True)),
 "baseline_control":((0,2,1,True),(0,4,1,True)),
}

def validate_creation_contract(record):
    b=record["begin"];events=record["events"];name=b["case"]
    need(name in CREATION_CONTRACT,"creation contract case")
    if name=="migration_guard":
        need(len(record["admission"])==1 and
             tuple(record["admission"][0][k] for k in ("observer_uid","consumed","error","second_forked"))
             ==(0,1,errno.EPERM,0),"creation migration admission evidence")
    attempts=CREATION_CONTRACT[name]
    expected_ops={}
    for parent,child,api,success in attempts:
        expected_ops.setdefault(parent,[]).append((3 if success else 2,child,api,success))
    if name=="soft_q":
        expected_ops[0]=[(2,0,3,None),(2,2,1,False),(2,0,4,None),(3,4,1,True)]
    elif name=="hard_q":
        expected_ops[0]=[(2,0,5,None),(3,2,1,True)]
    elif name=="hard_root_calibration":
        expected_ops[0]=[(2,0,7,None)]
    actual_ops=[e for e in events if e["event"] in (2,3)]
    need(len(actual_ops)==sum(map(len,expected_ops.values())),"creation operation cardinality")
    for parent in set(expected_ops)|{e["slot"] for e in actual_ops}:
        expected=expected_ops.get(parent,[])
        actual=[e for e in actual_ops if e["slot"]==parent]
        need(len(actual)==len(expected),"creation parent cardinality")
        for e,(kind,child,api,success) in zip(actual,expected):
            need((e["event"],e["other"],e["op"])==(kind,child,api),"creation operation sequence")
            if success is True:
                need(e["rc"]>0 and e["error"]==0 and e["aux"]==1,"creation success/first byte")
            elif success is False:
                need((e["rc"],e["error"],e["aux"])==(-1,errno.EAGAIN,0),"creation rejection")
            else:
                wanted=(-1,errno.EPERM) if api==5 else (0,0)
                need((e["rc"],e["error"],e["aux"])==(*wanted,0),"limit mutation result")
    successful={(parent,child) for parent,child,api,success in attempts if success}
    roots=set(range(b["roots"]))
    expected_members=roots|{child for parent,child in successful}
    started=[e for e in events if e["event"]==1]
    need(len(started)==len(expected_members) and {e["slot"] for e in started}==expected_members,
         "creation START set")
    positions={(kind,slot):[i for i,e in enumerate(events) if e["event"]==kind and e["slot"]==slot]
               for kind in (1,7,8,100,101) for slot in expected_members}
    for slot in expected_members:
        need(len(positions[1,slot])==1,"creation unique START")
        if slot in roots and b["vector"]!=12:
            need(len(positions[100,slot])==len(positions[101,slot])==1
                 and positions[100,slot][0]<positions[101,slot][0]<positions[1,slot][0],
                 "creation root phases")
        else:
            need(not positions[100,slot] and not positions[101,slot],"creation unexpected root phase")
    finishers=roots|({2} if b["vector"]==5 else set())
    for slot in expected_members:
        need(len(positions[7,slot])==len(positions[8,slot])==(1 if slot in finishers else 0),
             "creation FINISH/DONE set")
        if slot in finishers:
            finish,done=positions[7,slot][0],positions[8,slot][0]
            need(positions[1,slot][0]<finish<done,"creation FINISH/DONE order")
            own=[(i,e) for i,e in enumerate(events) if e["slot"]==slot and e["event"] in (2,3,5,6)]
            need(all(positions[1,slot][0]<i<finish for i,e in own),"creation operation lifetime")
            pending=sum(1 for parent,child in successful if parent==slot and
                        not any(e["event"]==4 and e["other"]==child and i<finish for i,e in enumerate(events)))
            need((events[finish]["rc"],events[finish]["error"],events[done]["rc"],events[done]["error"])
                 ==(pending,0,0,0),"creation FINISH pending count")
    reaps=[(i,e) for i,e in enumerate(events) if e["event"]==4]
    need(len(reaps)==len(successful) and {(e["slot"],e["other"]) for i,e in reaps}==successful,
         "creation reap set")
    for parent,child in successful:
        forks=[(i,e) for i,e in enumerate(events) if e["event"]==3 and e["slot"]==parent and e["other"]==child]
        waits=[(i,e) for i,e in reaps if e["slot"]==parent and e["other"]==child]
        need(len(forks)==len(waits)==1,"creation unique fork/reap")
        fi,fork=forks[0];ri,reap=waits[0];ci=positions[1,child][0]
        need(positions[1,parent][0]<fi<ci<ri<positions[8,parent][0]
             and (reap["rc"],reap["error"],reap["aux"])==(fork["rc"],0,0),
             "creation parent/child/reap causality")
        need(events[ci]["other"]==parent,"creation child parent slot")
        if child in finishers:
            need(positions[8,child][0]<ri,"creation grandchild parent DONE before reap")
    def event_index(kind,slot,other=None):
        found=[i for i,e in enumerate(events) if e["event"]==kind and e["slot"]==slot
               and (other is None or e["other"]==other)]
        need(len(found)==1,"creation causal marker cardinality")
        return found[0]
    if b["vector"]==4:
        need(event_index(4,0,2)<event_index(3,0,4),"creation refork after reap")
    if b["vector"]==7:
        need(event_index(1,2)<event_index(6,0,2)
             <event_index(2 if b["quota"] else 3,0,4)<event_index(4,0,2)
             <event_index(3,0,6),"creation zombie/reap/refork order")
    thread_events=[e for e in events if e["event"]==5]
    zombie_events=[e for e in events if e["event"]==6]
    need(len(thread_events)==(2 if b["vector"]==6 else 0),"creation thread event cardinality")
    need(len(zombie_events)==(1 if b["vector"]==7 else 0),"creation zombie event cardinality")
    if b["vector"]==6:
        need(max(i for i,e in enumerate(events) if e["event"]==5)
             <min(i for i,e in enumerate(events) if e["event"] in (2,3)),"creation joins before fork")

def operations(record,slot=None,op=None):
    return [e for e in record["events"] if e["event"] in (2,3)
            and (slot is None or e["slot"]==slot) and (op is None or e["op"]==op)]

def starts(record):
    return [e for e in record["events"] if e["event"]==1]

@unittest.skipUnless(os.environ.get("ICODE_M0A2_EVIDENCE"),"native M0a2 evidence not requested")
class TestVectorsNative(unittest.TestCase):
    rows=None
    variant=None

    def test_complete_identity_protocol(self):
        expected=BASELINE_NAMES if self.variant=="baseline" else SOURCE_NAMES
        self.assertEqual(tuple(self.rows),expected)
        for record in self.rows.values():
            b=record["begin"]
            if b["vector"]!=12:
                for root in range(b["roots"]):
                    phases=[e["event"] for e in record["events"] if e["slot"]==root and e["event"] in (100,101,1)]
                    self.assertEqual(phases,[100,101,1])
                    root_start=next(e for e in starts(record) if e["slot"]==root)
                    self.assertEqual(root_start["live_count"],b["roots"] if b["shared"] else 1)

    def test_creation_positive_controls(self):
        controls=BASELINE_NAMES[1:] if self.variant=="baseline" else (
            "fork_exec_c","spawn_c","third_c","refork_q","refork_c","grandchild_c",
            "pthread_c","zombie_c","soft_c","hard_c","independent_c")
        for name in controls:
            for e in operations(self.rows[name]):
                self.assertGreater(e["rc"],0,name)
                self.assertEqual((e["error"],e["aux"]),(0,1),name)
        if self.variant!="baseline":
            calibration=operations(self.rows["hard_root_calibration"],op=7)
            self.assertEqual(len(calibration),1)
            self.assertEqual((calibration[0]["rc"],calibration[0]["error"],
                              calibration[0]["current"],calibration[0]["maximum"]),(0,0,3,3))

    def test_cap2_quota_semantic(self):
        if self.variant=="baseline":
            third=operations(self.rows["baseline_third"])[1]
            self.assertEqual(third["rc"],-1,"M0A2_CAP2_REJECTION")
            self.assertEqual((third["error"],third["aux"]),(errno.EAGAIN,0))
            return
        expected={
            "fork_exec_q":[0],"spawn_q":[0],"third_q":[1],"grandchild_q":[1],
            "pthread_q":[0],"zombie_q":[1],"soft_q":[1],"independent_q":[1,3],
            "shared_counterexample":[0,1],
        }
        for name,indices in expected.items():
            record=self.rows[name]
            ops=operations(record)
            if name=="independent_q":
                # Cross-root scheduling is deliberately unordered.
                rejected=[e for e in ops if e["rc"]<0]
                self.assertEqual(len(rejected),2)
            elif name=="soft_q":
                rejected=[e for e in ops if e["op"]==1 and e["other"]==2]
            else:
                rejected=[ops[i] for i in indices]
            for e in rejected:
                self.assertEqual((e["rc"],e["error"],e["aux"]),(-1,errno.EAGAIN,0),name)

    def test_inheritance_and_limit_mutations(self):
        for record in self.rows.values():
            b=record["begin"]
            if b["vector"]==12:
                continue
            soft_current=b["cap"]
            initial=next(e for e in starts(record) if e["slot"]==0)
            for e in record["events"]:
                if e["op"]==3: soft_current=1
                if e["op"]==4: soft_current=2
                if self.variant=="baseline" or not b["quota"]:
                    self.assertGreaterEqual(e["current"],3 if b["vector"]==3 else 2)
                    self.assertEqual((e["current"],e["maximum"]),(initial["current"],initial["maximum"]))
                    continue
                expected=(soft_current,2) if b["vector"]==8 and e["slot"]==0 else (b["cap"],b["cap"])
                self.assertEqual((e["current"],e["maximum"]),expected,b["case"])
        if self.variant!="baseline":
            soft=operations(self.rows["soft_q"],op=3)+operations(self.rows["soft_q"],op=4)
            self.assertEqual([(e["rc"],e["error"]) for e in soft],[(0,0),(0,0)])
            hard=operations(self.rows["hard_q"],op=5)
            self.assertEqual([(e["rc"],e["error"],e["current"],e["maximum"]) for e in hard],
                             [(-1,errno.EPERM,2,2)])

    def test_threads_zombie_and_identity_boundaries(self):
        if self.variant=="baseline":
            self.assertGreater(operations(self.rows["baseline_third"])[0]["rc"],0)
            return
        for name in ("pthread_q","pthread_c"):
            waves=[e for e in self.rows[name]["events"] if e["event"]==5]
            self.assertEqual([(e["rc"],e["aux"],e["other"],e["threads"],e["live_count"]) for e in waves],
                             [(4,3,3,4,1),(2,1,4,2,1)])
        for name in ("zombie_q","zombie_c"):
            record=self.rows[name]
            z=[e for e in record["events"] if e["event"]==6]
            self.assertEqual(len(z),1)
            self.assertEqual((z[0]["rc"],z[0]["error"],z[0]["zombie_state"]),(0,0,5))
            ordered=[(e["event"],e["other"]) for e in record["events"]]
            self.assertLess(ordered.index((6,2)),next(i for i,e in enumerate(record["events"])
                if e["event"] in (2,3) and e["other"]==4))
            self.assertLess(ordered.index((4,2)),ordered.index((3,6)))
        guard=self.rows["migration_guard"]
        self.assertEqual([(r["observer_uid"],r["consumed"],r["error"],r["second_forked"])
                          for r in guard["admission"]],[(0,1,errno.EPERM,0)])
        self.assertEqual(len(starts(guard)),1)
        for name in ("migration_counterexample","shared_counterexample"):
            roots=[e for e in starts(self.rows[name]) if e["slot"]<2]
            self.assertEqual(len(roots),2)
            self.assertEqual({e["uid"] for e in roots},{self.rows[name]["begin"]["uid0"]})
            self.assertTrue(all(e["live_count"]==2 for e in roots))
        q=self.rows["independent_q"]
        self.assertNotEqual(q["begin"]["uid0"],q["begin"]["uid1"])
        self.assertEqual(len([e for e in operations(q) if e["rc"]>0]),2)
        self.assertEqual(len([e for e in operations(self.rows["independent_c"]) if e["rc"]>0]),4)

# Portable observer/collector tests; synthetic rows never grant native credit.
import copy
import hashlib
import importlib.util
from pathlib import Path
import stat
import subprocess
import time
from types import SimpleNamespace
from unittest import mock

def software_fixture(variant="source"):
    names=BASELINE_NAMES if variant=="baseline" else SOURCE_NAMES
    configs=BASELINE_CONFIGS if variant=="baseline" else SOURCE_CONFIGS
    meta={"phase":"red" if variant=="baseline" else "green","variant":variant,
          "candidate_sha":"a"*40,"binary_sha256":hashlib.sha256(b"binary").hexdigest(),
          "arch":"arm64","os_build":"26A1","kernel":"26.0.0","deadline_ns":500_000_000_000}
    rows=[]
    for index,(name,config) in enumerate(zip(names,configs)):
        vector,quota,profile,cap,roots,shared=config
        uid=0 if vector==12 else 60000+index*3
        uids=[uid,uid if shared else uid+1]
        begin={"kind":"begin","version":1,**{k:meta[k] for k in
            ("candidate_sha","variant","binary_sha256","arch","os_build","kernel")},
            "profile_sha256":"b"*64,"sandbox_exec_sha256":"c"*64,"case_index":index,"case":name,
            "vector":vector,"quota":quota,"profile":profile,"cap":cap,"roots":roots,"shared":shared,
            "uid0":uids[0],"uid1":uids[1] if roots==2 else 0,"observer_pid":400,"observer_uid":0,
            "observer_start_sec":800,"observer_start_usec":0,"deadline_ns":meta["deadline_ns"]}
        rows.append(begin);events=[];alive={s for s in range(roots)}
        pids={s:1000+index*10+s for s in alive};parents={s:400 for s in alive}
        identities={s:uids[s] for s in alive};limits={s:cap if quota and variant=="source" else 20 for s in alive}
        def emit(kind,slot,other=0,op=0,rc=0,error=0,aux=0,threads=-1,zombie=-1):
            identity=identities[slot]
            current=limits[slot]
            hard=2 if vector==8 and quota and variant=="source" else current
            row={"kind":"event","version":1,"case_index":index,"event":kind,"slot":slot,
                 "other":other,"op":op,"pid":pids[slot],"ppid":parents[slot],"start_sec":900+index,
                 "start_usec":slot,"uid":identity,"euid":identity,"gid":identity,"egid":identity,
                 "saved_uid":identity,"saved_gid":identity,"count":1,"read":1,"group":identity,
                 "predicate":0,"current":current,"maximum":hard,"rc":rc,"error":error,"aux":aux,
                 "independent_credentials":1,"live_count":sum(identities[s]==identity for s in alive),
                 "threads":threads,"zombie_state":zombie,
                 "fd3_errno":0 if kind in (100,101) else errno.EBADF,
                 "fd4_errno":0 if kind in (100,101) else errno.EBADF,
                 "canary_error":-1 if kind==100 else errno.EPERM if profile else 0,
                 "canary_allowed":0 if kind==100 else 1}
            events.append(row)
            return row
        def fork(parent,child,success=True,spawn=False):
            if not success:
                emit(2,parent,child,2 if spawn else 1,-1,errno.EAGAIN)
                return False
            pids[child]=1000+index*10+child;parents[child]=pids[parent]
            identities[child]=identities[parent];limits[child]=limits[parent];alive.add(child)
            emit(3,parent,child,2 if spawn else 1,pids[child],0,1)
            emit(1,child,parent,aux=errno.EPERM if profile else 0)
            return True
        def reap(parent,child):
            alive.remove(child)
            emit(4,parent,child,rc=pids[child])
        if vector!=12:
            for root in range(roots):
                emit(100,root);emit(101,root)
        for root in range(roots):
            emit(1,root,aux=errno.EPERM if profile else 0)
        held={root:[] for root in range(roots)}
        if vector==12:
            limits[0]=3;emit(2,0,op=7)
        elif vector==11:
            if not shared:
                rows.append({"kind":"admission","version":1,"case_index":index,"observer_uid":0,
                             "consumed":1,"error":errno.EPERM,"second_forked":0})
        elif vector==6:
            emit(5,0,3,rc=4,aux=3,threads=4)
            emit(5,0,4,rc=2,aux=1,threads=2)
            if fork(0,2,not quota or variant=="baseline"):
                held[0].append(2)
        elif vector in (1,2):
            if fork(0,2,not quota or variant=="baseline",vector==2):
                held[0].append(2)
        elif vector==4:
            fork(0,2);reap(0,2);fork(0,4);reap(0,4)
        elif vector==5:
            fork(0,2);held[0].append(2)
            if fork(2,4,not quota or variant=="baseline"):
                held[2]=[4]
            else:
                held[2]=[]
        elif vector==7:
            fork(0,2)
            emit(6,0,2,rc=0,aux=pids[2],zombie=5)
            if fork(0,4,not quota or variant=="baseline"):
                held[0].append(4)
            reap(0,2)
            fork(0,6);held[0].append(6)
        elif vector==8:
            if quota:
                limits[0]=1;emit(2,0,op=3)
                fork(0,2,False)
                limits[0]=2;emit(2,0,op=4)
                fork(0,4);held[0].append(4)
            else:
                fork(0,2);held[0].append(2)
        elif vector==9:
            if quota:
                emit(2,0,op=5,rc=-1,error=errno.EPERM)
            fork(0,2);held[0].append(2)
        else:
            for root in range(roots):
                first=2+root
                if vector==10 and shared:
                    fork(root,first,False)
                    continue
                fork(root,first);held[root].append(first)
                if fork(root,4+root,not quota or variant=="baseline"):
                    held[root].append(4+root)
        if vector==5:
            emit(7,2,rc=len(held[2]))
        for root in range(roots):
            emit(7,root,rc=len(held[root]))
        if vector==5:
            for child in held[2]:
                reap(2,child)
            emit(8,2)
        for root in range(roots):
            for child in held[root]:
                reap(root,child)
            emit(8,root)
        rows.extend(events)
        rows.append({"kind":"end","version":1,"case_index":index,"events":len(events),
            "roots_reaped":roots,"remaining":0,
            "cleanup_scope":"owned_roots_and_observed_direct_parent_reaps","retained":True})
    return meta,rows

def encoded(rows):
    return ("\n".join(json.dumps(row,separators=(",",":")) for row in rows)+"\n").encode()

def exercise_assertions(raw,meta):
    rows=parse_vectors(raw,meta)
    target=unittest.TestCase()
    target.rows=rows;target.variant=meta["variant"]
    for name in sorted(name for name in TestVectorsNative.__dict__ if name.startswith("test_")):
        getattr(TestVectorsNative,name)(target)
    return rows

class TestVectorsPortable(unittest.TestCase):
    def test_source_oracle_all_twenty_four(self):
        meta,rows=software_fixture()
        self.assertEqual(len(exercise_assertions(encoded(rows),meta)),24)

    def test_baseline_only_real_quota_assertion_would_fail(self):
        meta,rows=software_fixture("baseline")
        parsed=parse_vectors(encoded(rows),meta)
        target=unittest.TestCase();target.rows=parsed;target.variant="baseline"
        methods=[name for name in TestVectorsNative.__dict__ if name.startswith("test_")]
        failures=[]
        for name in methods:
            try:
                getattr(TestVectorsNative,name)(target)
            except AssertionError as error:
                failures.append((name,str(error)))
        self.assertEqual(len(failures),1)
        self.assertEqual(failures[0][0],"test_cap2_quota_semantic")
        self.assertIn("M0A2_CAP2_REJECTION",failures[0][1])
        # This is synthetic observer self-calibration, not a native RED claim.

    def test_schema_identity_and_completeness_negative_controls(self):
        meta,rows=software_fixture()
        mutations=[
            lambda r:r.pop(),
            lambda r:r.insert(0,copy.deepcopy(r[0])),
            lambda r:r[0].update(candidate_sha="f"*40),
            lambda r:r[0].update(binary_sha256="f"*64),
            lambda r:r[0].update(cap=2),
            lambda r:r[1].update(uid=True),
            lambda r:r[1].update(group=1),
            lambda r:r[1].update(saved_uid=0),
            lambda r:r[1].update(start_sec=0),
            lambda r:r[3].update(fd3_errno=0),
            lambda r:r[2].update(canary_allowed=0),
            lambda r:r[1].update(extra=1),
            lambda r:r[-1].update(events=0),
            lambda r:r[-1].update(roots_reaped=True),
        ]
        for change in mutations:
            with self.subTest(change=mutations.index(change)):
                bad=copy.deepcopy(rows);change(bad)
                with self.assertRaises((ValueError,AssertionError)):
                    exercise_assertions(encoded(bad),meta)
        with self.assertRaises(ValueError):
            parse_vectors(encoded(rows).replace(b'"version":1',b'"version":1,"version":1',1),meta)

    def test_semantic_mutation_negative_controls(self):
        meta,rows=software_fixture()
        predicates=[
            lambda r:r["kind"]=="event" and r["event"]==2 and r["error"]==errno.EAGAIN,
            lambda r:r["kind"]=="event" and r["event"]==5,
            lambda r:r["kind"]=="event" and r["event"]==6,
            lambda r:r["kind"]=="event" and r["op"]==5,
            lambda r:r["kind"]=="admission",
        ]
        edits=[{"error":errno.EPERM},{"threads":5},{"zombie_state":0},
               {"error":0},{"error":0}]
        for select,edit in zip(predicates,edits):
            bad=copy.deepcopy(rows)
            next(row for row in bad if select(row)).update(edit)
            with self.assertRaises((ValueError,AssertionError)):
                exercise_assertions(encoded(bad),meta)

    def test_every_case_requires_exact_creation_and_reap_evidence(self):
        checked=0
        for variant in ("source","baseline"):
            meta,rows=software_fixture(variant)
            names=SOURCE_NAMES if variant=="source" else BASELINE_NAMES
            for index,name in enumerate(names):
                attempts=CREATION_CONTRACT[name]
                successful=[child for parent,child,api,success in attempts if success]
                modes=["all_creation","one_attempt"] if attempts else ["dedicated"]
                modes += [("child_START",child) for child in successful]
                modes += [("reap",child) for child in successful]
                for mode in modes:
                    with self.subTest(variant=variant,case=name,mutation=mode):
                        bad=copy.deepcopy(rows)
                        def selected(row):
                            return row.get("case_index")==index
                        if mode=="all_creation":
                            children=set(successful)
                            bad=[r for r in bad if not (selected(r) and r["kind"]=="event" and
                                 ((r["event"] in (2,3) and r["op"] in (1,2)) or
                                  r["slot"] in children or (r["event"]==4 and r["other"] in children)))]
                            for r in bad:
                                if selected(r) and r["kind"]=="event" and r["event"]==7:
                                    r["rc"]=0
                        elif mode=="one_attempt":
                            found=next(i for i,r in enumerate(bad) if selected(r) and r["kind"]=="event"
                                       and r["event"] in (2,3) and r["op"] in (1,2))
                            del bad[found]
                        elif mode=="dedicated":
                            found=next(i for i,r in enumerate(bad) if selected(r) and
                                       ((name=="hard_root_calibration" and r["kind"]=="event" and r["op"]==7)
                                        or (name=="migration_guard" and r["kind"]=="admission")
                                        or (name=="migration_counterexample" and r["kind"]=="event"
                                            and r["event"]==1 and r["slot"]==1)))
                            del bad[found]
                        else:
                            kind,child=mode
                            found=next(i for i,r in enumerate(bad) if selected(r) and r["kind"]=="event" and
                                       ((kind=="child_START" and r["event"]==1 and r["slot"]==child)
                                        or (kind=="reap" and r["event"]==4 and r["other"]==child)))
                            del bad[found]
                        # Repair factual accounting: refusal must not rely on stale end.events.
                        for r in bad:
                            if selected(r) and r["kind"]=="end":
                                r["events"]=sum(selected(e) and e["kind"]=="event" for e in bad)
                        with self.assertRaises(ValueError):
                            exercise_assertions(encoded(bad),meta)
                        checked+=1
        self.assertEqual(checked,113)

class TestVectorsCollectorPortable(unittest.TestCase):
    def test_actual_collector_success_and_rejection_boundaries(self):
        import tempfile
        import selectors
        from scripts import run_macos_m0a2_vectors as collector
        modes=(
            "success","native_nonzero","native_timeout","native_wait_timeout","native_select_timeout",
            "native_stdout_overflow","native_stderr_overflow","native_stderr","manifest_513","manifest_empty",
            "manifest_duplicate","manifest_bool_version","manifest_version","manifest_extra","manifest_bool_cases",
            "manifest_cases","manifest_path","manifest_digest_format","manifest_digest",
            "directory_owner","directory_mode","directory_type","ledger_owner","ledger_mode","ledger_nlink",
            "ledger_zero","ledger_large","ledger_type","changed_dev","changed_ino","changed_size",
            "changed_mtime","changed_ctime","changed_owner","changed_mode","changed_nlink",
            "ledger_short","ledger_overflow","ledger_bad_json","ledger_incomplete","observer_quota",
            "binary_missing","binary_symlink","binary_zero",
        )
        self.assertEqual(len(modes),44)
        for mode in modes:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(prefix="m0a2-software-") as temporary:
                root=Path(temporary).resolve(strict=True);build=root/"build";build.mkdir();output=root/"green";output.mkdir()
                binary=build/"icode_m0a1_vectors_source";binary.write_bytes(b"binary");binary.chmod(0o700)
                meta,rows=software_fixture()
                meta["deadline_ns"]=500_000_000_000
                if mode=="observer_quota":
                    next(r for r in rows if r["kind"]=="event" and r["error"]==errno.EAGAIN)["error"]=errno.EPERM
                raw=encoded(rows)
                if mode=="ledger_bad_json":raw=b"not JSON\n"
                if mode=="ledger_incomplete":raw=encoded(rows[:-1])
                if mode=="ledger_overflow":raw=b"X"*(2*1024*1024+1)
                digest=hashlib.sha256(raw).hexdigest()
                manifest={"version":1,"root_directory":"/private/var/icode-m0a1.Model",
                          "ledger_sha256":digest,"cases":24}
                changes={
                    "manifest_bool_version":{"version":True},"manifest_version":{"version":2},
                    "manifest_extra":{"extra":1},"manifest_bool_cases":{"cases":True},
                    "manifest_cases":{"cases":23},"manifest_path":{"root_directory":"/private/var/../tmp"},
                    "manifest_digest_format":{"ledger_sha256":"z"*64},
                    "manifest_digest":{"ledger_sha256":"f"*64},
                }
                manifest.update(changes.get(mode,{}))
                stdout=json.dumps(manifest).encode()
                if mode=="manifest_513":stdout=b" "*513
                if mode=="manifest_empty":stdout=b""
                if mode=="manifest_duplicate":stdout=stdout.replace(b'"version": 1',b'"version": 1, "version": 1')
                if mode=="native_stdout_overflow":stdout=b"X"*65537
                stderr=b"X"*65537 if mode=="native_stderr_overflow" else b"diagnostic" if mode=="native_stderr" else b""
                if mode=="binary_missing":binary.unlink()
                if mode=="binary_symlink":
                    binary.unlink();binary.symlink_to("/dev/null")
                if mode=="binary_zero":binary.write_bytes(b"")
                streams={1001:bytearray(stdout),1002:bytearray(stderr),700:bytearray(raw)}
                original_lstat=Path.lstat;original_open=os.open;original_read=os.read;original_fstat=os.fstat
                directory=SimpleNamespace(st_mode=stat.S_IFDIR|0o755,st_uid=0)
                if mode=="directory_owner":directory.st_uid=1
                if mode=="directory_mode":directory.st_mode=stat.S_IFDIR|0o777
                if mode=="directory_type":directory.st_mode=stat.S_IFREG|0o755
                file_fields=dict(st_mode=stat.S_IFREG|0o444,st_uid=0,st_nlink=1,
                    st_size=len(raw),st_dev=1,st_ino=2,st_mtime_ns=3,st_ctime_ns=4)
                for key,value in {
                    "ledger_owner":("st_uid",1),"ledger_mode":("st_mode",stat.S_IFREG|0o644),
                    "ledger_nlink":("st_nlink",2),"ledger_zero":("st_size",0),
                    "ledger_large":("st_size",2*1024*1024+1),
                    "ledger_type":("st_mode",stat.S_IFDIR|0o444),
                    "ledger_short":("st_size",len(raw)+1),
                }.items():
                    if mode==key:file_fields[value[0]]=value[1]
                # Overflow is detected by actual read loop, not the initial stat guard.
                if mode=="ledger_overflow":file_fields["st_size"]=2*1024*1024
                stat_calls=[0]
                def fstat(fd):
                    if fd!=700:return original_fstat(fd)
                    stat_calls[0]+=1;fields=dict(file_fields)
                    changed={
                        "changed_dev":"st_dev","changed_ino":"st_ino","changed_size":"st_size",
                        "changed_mtime":"st_mtime_ns","changed_ctime":"st_ctime_ns","changed_owner":"st_uid",
                        "changed_mode":"st_mode","changed_nlink":"st_nlink",
                    }
                    if stat_calls[0]>1 and mode in changed:fields[changed[mode]]+=1
                    return SimpleNamespace(**fields)
                def lstat(path,*args,**kwargs):
                    if str(path)=="/private/var/icode-m0a1.Model":return directory
                    return original_lstat(path,*args,**kwargs)
                def opened(path,*args,**kwargs):
                    if str(path)=="/private/var/icode-m0a1.Model/vectors.jsonl":return 700
                    return original_open(path,*args,**kwargs)
                def read(fd,size):
                    if fd not in streams:return original_read(fd,size)
                    value=bytes(streams[fd][:size]);del streams[fd][:size];return value
                class Pipe:
                    def __init__(self,fd):self.fd=fd;self.closed=False
                    def fileno(self):return self.fd
                    def close(self):self.closed=True
                class Process:
                    pid=987
                    def __init__(self):
                        self.stdout=Pipe(1001);self.stderr=Pipe(1002);self.returncode=None
                    def poll(self):return self.returncode
                    def wait(self,timeout):
                        if mode=="native_wait_timeout":raise subprocess.TimeoutExpired("model",timeout)
                        self.returncode=9 if mode=="native_nonzero" else 0
                        return self.returncode
                process=Process()
                class Selector:
                    def __init__(self):self.mapping={}
                    def __enter__(self):return self
                    def __exit__(self,*args):return False
                    def register(self,obj,event,data):
                        self.mapping[obj.fileno()]=SimpleNamespace(fileobj=obj,data=data)
                    def unregister(self,obj):self.mapping.pop(obj.fileno())
                    def get_map(self):return self.mapping
                    def select(self,timeout):
                        if mode=="native_select_timeout":raise TimeoutError("model deadline")
                        return [(value,None) for value in list(self.mapping.values())]
                clock_calls=[0]
                def clock(which):
                    self.assertEqual(which,time.CLOCK_MONOTONIC)
                    clock_calls[0]+=1
                    return 501_000_000_000 if mode=="native_timeout" and clock_calls[0]>1 else 100_000_000_000
                original_close=os.close
                def close(fd):
                    if fd!=700:return original_close(fd)
                with mock.patch.object(collector,"process_groups_binding",return_value="d"*64), \
                     mock.patch.object(collector.subprocess,"Popen",return_value=process) as popen, \
                     mock.patch.object(collector.selectors,"DefaultSelector",Selector), \
                     mock.patch.object(collector.time,"clock_gettime_ns",side_effect=clock), \
                     mock.patch.object(collector.os,"killpg") as killed, \
                     mock.patch.object(Path,"lstat",lstat), \
                     mock.patch.object(collector.os,"open",side_effect=opened), \
                     mock.patch.object(collector.os,"read",side_effect=read), \
                     mock.patch.object(collector.os,"fstat",side_effect=fstat), \
                     mock.patch.object(collector.os,"close",side_effect=close):
                    if mode=="success":
                        result=collector.run_vectors(Path(__file__).resolve().parents[1],build,output,dict(meta))
                        self.assertEqual(result["result"],"vectors_GREEN_only")
                        self.assertEqual(result["cases"],24)
                        self.assertTrue((output/"vectors-result.json").is_file())
                        self.assertEqual(popen.call_args.args[0][-1],format(meta["deadline_ns"],"016x"))
                    else:
                        with self.assertRaises((RuntimeError,ValueError,FileNotFoundError,TimeoutError)):
                            collector.run_vectors(Path(__file__).resolve().parents[1],build,output,dict(meta))
                        self.assertFalse((output/"vectors-result.json").exists())
                        if mode in ("native_timeout","native_wait_timeout","native_select_timeout",
                                    "native_stdout_overflow","native_stderr_overflow"):
                            self.assertTrue(killed.called)

class TestVectorsDeadlinePortable(unittest.TestCase):
    def test_actual_native_deadline_functions_with_clock_boundary_stub(self):
        import shutil
        import subprocess
        import tempfile
        if os.name!="posix":
            self.skipTest("software C probe requires POSIX host; not native credit")
        compiler=shutil.which("cc")
        self.assertIsNotNone(compiler)
        repo=Path(__file__).resolve().parents[1]
        source=(repo/"native/mac/tests/icode_m0a2_vectors.c").read_text()
        common=(repo/"native/mac/tests/icode_m0a1_fixed_helpers.inc").read_text()
        fragment=source[source.index("static uint64_t experiment_deadline;"):
                        source.index("static struct definition definition_at(")]
        hex_function=common[common.index("static int hex_string("):common.index("static int numeric(")]
        probe=r"""
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <inttypes.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static jmp_buf failure;
static const char *last_stage;
static struct timespec fake_now={100,0};
static int clock_error;
static unsigned checks;
static void die(const char *stage) { last_stage=stage;longjmp(failure,1); }
static int fake_clock(clockid_t which,struct timespec *out) {
 if(which!=CLOCK_MONOTONIC) abort();
 if(clock_error) { errno=EIO;return -1; }
 *out=fake_now;return 0;
}
#define clock_gettime fake_clock
""" + hex_function + fragment + r"""
#define CHECK(statement,reject,prefix) do { \
 checks++;last_stage=NULL; \
 if(setjmp(failure)) { if(!(reject) || strncmp(last_stage,prefix,strlen(prefix))) return 3; } \
 else { statement; if(reject) return 4; } \
} while(0)
int main(void) {
 char text[17];
 snprintf(text,sizeof(text),"%016" PRIx64,(uint64_t)101000000000ULL);
 CHECK(parse_deadline(text),0,"");
 CHECK((void)remaining_seconds(),0,"");
 snprintf(text,sizeof(text),"%016" PRIx64,(uint64_t)580000000000ULL);
 CHECK(parse_deadline(text),0,"");
 snprintf(text,sizeof(text),"%016" PRIx64,(uint64_t)580000000001ULL);
 CHECK(parse_deadline(text),1,"deadline-window");
 CHECK(parse_deadline("000000174876e800"),1,"deadline-window");
 CHECK(parse_deadline("0000000000000000"),1,"deadline-window");
 CHECK(parse_deadline("ffffffffffffffff"),1,"deadline-window");
 CHECK(parse_deadline("000000000000000"),1,"deadline-hex16");
 CHECK(parse_deadline("00000000000000000"),1,"deadline-hex16");
 CHECK(parse_deadline("000000000000000G"),1,"deadline-hex16");
 CHECK(parse_deadline("+000000000000000"),1,"deadline-hex16");
 clock_error=1;CHECK(parse_deadline(text),1,"monotonic-clock");clock_error=0;
 fake_now.tv_sec=-1;CHECK(parse_deadline(text),1,"monotonic-range");fake_now.tv_sec=100;
 fake_now.tv_nsec=1000000000L;CHECK(parse_deadline(text),1,"monotonic-range");fake_now.tv_nsec=0;
 fake_now.tv_sec=(time_t)INT64_MAX;CHECK(parse_deadline(text),1,"monotonic-range");fake_now.tv_sec=100;
 experiment_deadline=101000000000ULL;fake_now.tv_nsec=1;
 CHECK((void)remaining_seconds(),1,"deadline-expired");
 fake_now.tv_sec=101;fake_now.tv_nsec=0;CHECK((void)remaining_seconds(),1,"deadline-expired");
 fake_now.tv_sec=100;experiment_deadline=115000000000ULL;
 if(remaining_seconds()!=15) return 5;
 if(checks!=17) return 6;
 puts("deadline software boundary: 17 checks");
 return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="m0a2-clock-software-") as temporary:
            executable=Path(temporary)/"probe"
            compiled=subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror","-x","c","-",
                "-o",str(executable)],input=probe,text=True,capture_output=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,"deadline software boundary: 17 checks\n")

class TestVectorsMechanicalPortable(unittest.TestCase):
    def test_exact_inverse_keeps_original_driver_and_w1(self):
        repo=Path(__file__).resolve().parents[1]
        common=(repo/"native/mac/tests/icode_m0a1_fixed_helpers.inc").read_bytes()
        split=common.index(b"static int canaries(")
        driver=(repo/"native/mac/tests/icode_m0a1_driver.c").read_bytes()
        marker=b'#include "icode_m0a1_fixed_helpers.inc"\n'
        self.assertEqual(driver.count(marker),1)
        restored=driver.replace(marker,common[:split]).replace(b"static void gate(",common[split:]+b"static void gate(")
        self.assertEqual(hashlib.sha256(restored).hexdigest(),
            "944c9268461e522a01653b46bb3c18d038504af66910c66cf861901f8f28d25e")
        identity=(repo/"native/mac/tests/icode_m0a1_unused_identity.inc").read_bytes()
        w1=(repo/"native/mac/tests/icode_m0a1_process_groups_native.c").read_bytes()
        marker=b'#include "icode_m0a1_unused_identity.inc"\n'
        self.assertEqual(w1.count(marker),1)
        self.assertEqual(hashlib.sha256(w1.replace(marker,identity)).hexdigest(),
            "eb51b489cd07399414b98dc409fe08637c56d3b1e99636def493348d0d1aa636")

@unittest.skipUnless(os.environ.get("ICODE_M0A2_LIMIT_SOFTWARE"),"explicit cap2 software gate not requested")
class TestVectorsLimitPortable(unittest.TestCase):
    def test_actual_quota_source_cap2_and_exact_readback(self):
        import shutil
        import subprocess
        import tempfile
        compiler=shutil.which("cc")
        self.assertIsNotNone(compiler)
        repo=Path(__file__).resolve().parents[1]
        source=(repo/"native/mac/icode_m0a1_limit.c").read_text()
        probe=r"""
#define _DARWIN_C_SOURCE 1
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
static unsigned sets,quota_get_calls,checks;
static int set_error,get_error,read_mode;
static struct rlimit stored;
static int fake_set(int resource,const struct rlimit *value) {
 if(resource!=RLIMIT_NPROC) abort();
 sets++;if(set_error) { errno=set_error;return -1; }
 stored=*value;return 0;
}
static int fake_get(int resource,struct rlimit *value) {
 if(resource!=RLIMIT_NPROC) abort();
 quota_get_calls++;if(get_error) { errno=get_error;return -1; }
 *value=stored;
 if(read_mode==1) value->rlim_cur--;
 if(read_mode==2) value->rlim_max++;
 return 0;
}
#define setrlimit fake_set
#define getrlimit fake_get
""" + source + r"""
#define RESET() do { sets=quota_get_calls=0;set_error=get_error=read_mode=0;stored=(struct rlimit){2,2}; } while(0)
#define EXPECT(condition) do { checks++;if(!(condition)) { printf("failed software check=%u sets=%u quota_get_calls=%u\n",checks,sets,quota_get_calls);return 42; } } while(0)
int main(void) {
 RESET();int cap2=m0_apply_limit(2,1);
 EXPECT(cap2==0 && sets==1 && quota_get_calls==1 && stored.rlim_cur==2 && stored.rlim_max==2);
 RESET();errno=EBUSY;EXPECT(m0_apply_limit(0,0)==0 && !sets && !quota_get_calls && errno==EBUSY);
 RESET();errno=EBUSY;EXPECT(m0_check_limit(2,0)==0 && !sets && !quota_get_calls && errno==EBUSY);
 RESET();EXPECT(m0_apply_limit(1,1)==0 && sets==1 && quota_get_calls==1 && stored.rlim_cur==1 && stored.rlim_max==1);
 const rlim_t invalid[]={0,3,4,8};
 for(unsigned i=0;i<4;i++) { RESET();EXPECT(m0_apply_limit(invalid[i],1)==EINVAL && !sets && !quota_get_calls); }
 RESET();set_error=EACCES;EXPECT(m0_apply_limit(2,1)==EACCES && sets==1 && !quota_get_calls);
 RESET();get_error=EIO;EXPECT(m0_apply_limit(2,1)==EIO && sets==1 && quota_get_calls==1);
 RESET();read_mode=1;EXPECT(m0_apply_limit(2,1)==ERANGE && sets==1 && quota_get_calls==1);
 RESET();read_mode=2;EXPECT(m0_apply_limit(2,1)==ERANGE && sets==1 && quota_get_calls==1);
 RESET();EXPECT(m0_check_limit(2,1)==0 && !sets && quota_get_calls==1);
 RESET();read_mode=1;EXPECT(m0_check_limit(2,1)==ERANGE && !sets && quota_get_calls==1);
 RESET();read_mode=2;EXPECT(m0_check_limit(2,1)==ERANGE && !sets && quota_get_calls==1);
 RESET();get_error=EIO;EXPECT(m0_check_limit(2,1)==EIO && !sets && quota_get_calls==1);
 EXPECT(!strcmp(m0_variant(),"source"));
 if(checks!=17) return 43;
 puts("quota software boundary: 17 checks");return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="m0a2-limit-software-") as temporary:
            executable=Path(temporary)/"probe"
            compiled=subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror","-I",str(repo/"native/mac"),
                "-x","c","-","-o",str(executable)],input=probe,text=True,capture_output=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,"M0A2_CAP2_API "+result.stdout+result.stderr)
            self.assertEqual(result.stdout,"quota software boundary: 17 checks\n")

class TestVectorsBuildPortable(unittest.TestCase):
    def test_actual_build_sequence_and_tool_failures(self):
        import tempfile
        import sys
        from scripts import run_macos_m0a2_vectors as collector
        scenarios=((False,None),(True,None),(True,0),(True,1),(True,2),(True,3))
        for with_source,failure in scenarios:
            with self.subTest(source=with_source,failure=failure),tempfile.TemporaryDirectory(prefix="m0a2-build-model-") as temporary:
                root=Path(temporary);output=root/"logs";output.mkdir();calls=[]
                def tool(argv,deadline):
                    calls.append((argv,deadline))
                    return {"native_exit":9 if failure==len(calls)-1 else 0,"reason":None,"complete":True,
                            "stdout":b"bounded tool model\n","stderr":b""}
                with mock.patch.object(collector.shutil,"which",return_value=sys.executable), \
                     mock.patch.object(collector,"bounded_native",side_effect=tool), \
                     mock.patch.object(collector.time,"clock_gettime_ns",return_value=100_000_000_000):
                    if failure is None:
                        collector.prepare_build(root,root/"build",output,with_source,500_000_000_000)
                    else:
                        with self.assertRaises(RuntimeError):
                            collector.prepare_build(root,root/"build",output,with_source,500_000_000_000)
                self.assertEqual(len(calls),(4 if with_source else 2) if failure is None else failure+1)
                self.assertTrue(all(deadline==190_000_000_000 for _,deadline in calls))
                self.assertIn("-DM0_BUILD_VECTORS_SOURCE=OFF",calls[0][0])
                if len(calls)>1:
                    self.assertEqual(calls[1][0][-4:],["--target","icode_m0a1_vectors_baseline","--parallel","1"])
                if with_source and len(calls)>2:
                    self.assertIn("-DM0_BUILD_VECTORS_SOURCE=ON",calls[2][0])
                self.assertEqual(len(tuple(output.glob("*.json"))),len(calls))
                self.assertFalse((output/"vectors-result.json").exists())
