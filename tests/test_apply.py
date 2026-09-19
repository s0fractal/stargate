import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from stargate import apply as a, certificate as c
from stargate.canonical import canon, decode, InvalidRecord


def model(next='x', invariant='true', goals=None):
    rule=lambda expr: 'fact x: bool\ncheck '+expr
    return dict(language='boolean-machine-1', state=['x'], events=[], initial=[{'x':False}],
                next={'x':rule(next)}, invariant=rule(invariant), goals=goals or [])


def cert(m):
    return c.create(m,[{'x':False},{'x':True}],[])


class Apply(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.repo=self.root/'models.git'
        subprocess.run(['git','init','--bare',str(self.repo)],check=True,capture_output=True)
        self.parent=model();self.child=model('!x')
        self.packet=c.pack_change(cert(self.parent),cert(self.child))
        self.base=self.seed(canon(self.parent))

    def git(self,*args,data=None):
        return subprocess.check_output(['git','--git-dir='+str(self.repo),*args],input=data).strip()

    def seed(self,raw,mode='100644'):
        blob=self.git('hash-object','-w','--stdin',data=raw)
        extra=self.git('hash-object','-w','--stdin',data=b'unchanged\n')
        tree=self.git('mktree',data=mode.encode()+b' blob '+blob+b'\tmodel.json\n100644 blob '+extra+b'\tkeep.txt\n')
        commit=self.git('hash-object','-t','commit','-w','--stdin',data=b'tree '+tree+b'\nauthor Test <test@localhost> 1 +0000\ncommitter Test <test@localhost> 1 +0000\n\nroot\n')
        self.git('update-ref','refs/heads/main',commit.decode())
        return commit.decode()

    def run_apply(self,raw=None,**kw):
        args=dict(repository=self.repo,ref='refs/heads/main',model_path='model.json',
                  expected_commit=self.base,expected_checker=c.checker_id())
        args.update(kw)
        return a.apply(self.packet if raw is None else raw,**args)

    def tip(self):return self.git('rev-parse','refs/heads/main').decode()

    def test_real_commit_contains_only_verified_model_and_exact_parent(self):
        report=self.run_apply()
        self.assertEqual((report['status'],report['applied'],a.exit_code(report)),('applied',True,0))
        self.assertEqual(self.tip(),report['commit'])
        self.assertEqual(self.git('rev-parse',report['commit']+'^').decode(),self.base)
        self.assertEqual(self.git('show',report['commit']+':model.json'),canon(self.child))
        self.assertEqual(self.git('diff-tree','--no-commit-id','--name-only','-r',self.base,report['commit']),b'model.json')
        self.assertEqual(self.git('rev-parse',self.base+':keep.txt'),self.git('rev-parse',report['commit']+':keep.txt'))
        msg=self.git('cat-file','commit',report['commit'])
        self.assertIn(c.identity(decode(self.packet)).encode(),msg)
        self.assertIn(c.checker_id().encode(),msg)

    def test_repair_of_genuinely_unsafe_parent(self):
        broken=model('!x','!x');fixed=model('x','!x')
        ref=c.create_refutation(broken,dict(kind='unsafe',trace=dict(initial={'x':False},steps=[dict(event={},state={'x':True})])))
        child=c.create(fixed,[{'x':False}],[])
        self.base=self.seed(canon(broken))
        result=self.run_apply(c.pack_repair(ref,child))
        self.assertEqual(result['status'],'applied')
        self.assertEqual(result['check']['status'],'verified_repair')
        self.assertEqual(self.git('show','refs/heads/main:model.json'),canon(fixed))

    def test_invalid_proofs_contract_changes_and_other_base_never_publish(self):
        variants=[]
        bad=decode(self.packet);bad['candidate']['states']=[];variants.append(canon(bad))
        bad=decode(self.packet);bad['candidate']['model']['goals']=[{'x':True}];variants.append(canon(bad))
        bad=decode(self.packet);bad['extra']='surprise';variants.append(canon(bad))
        variants.append(c.pack_change(cert(model('true')),cert(self.child)))
        for raw in variants:
            with self.subTest(raw=raw),self.assertRaises(InvalidRecord):self.run_apply(raw)
            self.assertEqual(self.tip(),self.base)

    def test_refusal_never_even_writes_git_objects(self):
        original=a._Git.run
        writes=[]
        def counted(obj,*args,**kw):
            if args[0] in ('hash-object','mktree','update-ref'):writes.append(args)
            return original(obj,*args,**kw)
        with patch.object(a._Git,'run',counted):
            incomplete=self.run_apply(max_steps=0)
            unavailable=self.run_apply(expected_checker='0'*64)
            unchanged=self.run_apply(c.pack_change(cert(self.parent),cert(self.parent)))
        self.assertEqual([incomplete['status'],unavailable['status'],unchanged['status']],
                         ['incomplete','checker_unavailable','unchanged'])
        self.assertEqual([a.exit_code(x) for x in (incomplete,unavailable,unchanged)],[3,3,4])
        self.assertEqual(writes,[]);self.assertEqual(self.tip(),self.base)

    def test_cas_preserves_concurrent_commit_even_with_same_model(self):
        other=self.git('hash-object','-t','commit','-w','--stdin',data=b'tree '+self.git('rev-parse',self.base+'^{tree}')+b'\nparent '+self.base.encode()+b'\nauthor Test <test@localhost> 2 +0000\ncommitter Test <test@localhost> 2 +0000\n\nconcurrent\n').decode()
        verify=c.verify_change
        def racing(*args,**kw):
            answer=verify(*args,**kw)
            self.git('update-ref','refs/heads/main',other,self.base)
            return answer
        with patch.object(c,'verify_change',racing):result=self.run_apply()
        self.assertEqual((result['status'],result['applied'],a.exit_code(result)),('base_changed',False,4))
        self.assertEqual(self.tip(),other)
        self.assertEqual(self.run_apply()['status'],'base_changed')

    def test_stale_base_is_refused_before_proof_work(self):
        other=self.seed(canon(model('true')))
        self.assertNotEqual(other,self.base)
        with patch.object(c,'verify_change',wraps=c.verify_change) as verify:
            result=self.run_apply()
        self.assertEqual(result['status'],'base_changed')
        self.assertEqual(verify.call_count,0)
        self.assertEqual(self.tip(),other)

    def test_foreign_environment_hooks_and_replace_objects_do_not_choose_bytes(self):
        marker=self.root/'ran'
        hook=self.repo/'hooks'/'reference-transaction'
        hook.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\nexit 0\n');hook.chmod(0o755)
        # A replacement blob must not alter what we read from the committed tree.
        oid=self.git('rev-parse',self.base+':model.json').decode()
        replacement=self.git('hash-object','-w','--stdin',data=canon(model('false'))).decode()
        self.git('-c','core.hooksPath='+os.devnull,'replace',oid,replacement)
        with patch.dict(os.environ,{'GIT_DIR':'/does/not/exist','GIT_CONFIG_COUNT':'1',
                                    'GIT_CONFIG_KEY_0':'core.hooksPath','GIT_CONFIG_VALUE_0':str(hook.parent)}):
            result=self.run_apply()
        self.assertEqual(result['status'],'applied');self.assertFalse(marker.exists())

    def test_operator_scope_and_blob_modes(self):
        for kw in (dict(ref='HEAD'),dict(ref='refs/tags/x'),dict(model_path='../model.json'),
                   dict(model_path='dir/model.json'),dict(expected_commit='main')):
            with self.subTest(kw=kw),self.assertRaises(InvalidRecord):self.run_apply(**kw)
        for mode in ('100755','120000'):
            self.base=self.seed(canon(self.parent),mode)
            with self.assertRaisesRegex(InvalidRecord,'regular'):self.run_apply()
        self.git('symbolic-ref','refs/heads/alias','refs/heads/main')
        with self.assertRaisesRegex(InvalidRecord,'symbolic'):self.run_apply(ref='refs/heads/alias')
        checkout=self.root/'checkout';subprocess.run(['git','init',str(checkout)],check=True,capture_output=True)
        with self.assertRaisesRegex(InvalidRecord,'bare'):self.run_apply(repository=checkout/'.git')

    def test_cli_applies_and_stale_retry_is_not_success(self):
        packet=self.root/'change.json';packet.write_bytes(self.packet)
        cmd=[sys.executable,'-I','-m','stargate','model-apply',str(packet),'--repository',str(self.repo),
             '--ref','refs/heads/main','--model-path','model.json','--expect-commit',self.base,
             '--expect-checker',c.checker_id()]
        first=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(json.loads(first.stdout)['status'],'applied')
        second=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(second.returncode,4,second.stderr)
        self.assertEqual(json.loads(second.stdout)['status'],'base_changed')

    def test_git_failure_is_not_a_success_or_a_base_conflict(self):
        original=a._Git.run
        def fail(obj,*args,**kw):
            if args[0]=='update-ref':return subprocess.CompletedProcess(args,1,b'',b'permission denied')
            return original(obj,*args,**kw)
        with patch.object(a._Git,'run',fail),self.assertRaisesRegex(a.GitError,'permission denied'):
            self.run_apply()
        self.assertEqual(self.tip(),self.base)
