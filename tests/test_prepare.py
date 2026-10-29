"""Integrity and preservation boundaries for dependency preparation."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

spec=importlib.util.spec_from_file_location('prepare',Path(__file__).resolve().parents[1]/'scripts/prepare.py')
prepare=importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):
        super().__init__(data); self.status=status; self.headers=headers or {}


class InputIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.file=self.root/'input.bin'
        self.data=b'pinned upstream input'
        self.sha=hashlib.sha256(self.data).hexdigest()

    def tearDown(self): self.tmp.cleanup()

    def test_verified_cache_needs_no_network(self):
        self.file.write_bytes(self.data)
        with patch.object(prepare.urllib.request,'urlopen',side_effect=AssertionError('network')):
            prepare.download('https://example.invalid/input',self.file,self.sha,len(self.data))

    def test_resume_requires_correct_range_and_reconstructs_exact_input(self):
        partial=self.file.with_name(self.file.name+'.part')
        partial.write_bytes(self.data[:5])
        def serve(request,timeout):
            self.assertEqual(request.headers['Range'],'bytes=5-')
            return Response(self.data[5:],206,{'Content-Range':f'bytes 5-{len(self.data)-1}/{len(self.data)}'})
        with patch.object(prepare.urllib.request,'urlopen',side_effect=serve):
            prepare.download('https://example.invalid/input',self.file,self.sha,len(self.data))
        self.assertEqual(self.file.read_bytes(),self.data)
        self.assertFalse(partial.exists())

    def test_server_ignoring_range_restarts_instead_of_appending(self):
        self.file.with_name(self.file.name+'.part').write_bytes(b'incomplete')
        with patch.object(prepare.urllib.request,'urlopen',return_value=Response(self.data)):
            prepare.download('https://example.invalid/input',self.file,self.sha,len(self.data))
        self.assertEqual(self.file.read_bytes(),self.data)

    def test_corrupt_response_never_replaces_existing_input(self):
        self.file.write_bytes(b'preserve existing cache')
        with patch.object(prepare.urllib.request,'urlopen',side_effect=lambda *a,**k:Response(b'x'*len(self.data))), \
             patch.object(prepare.time,'sleep'):
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                prepare.download('https://example.invalid/input',self.file,self.sha,len(self.data))
        self.assertEqual(self.file.read_bytes(),b'preserve existing cache')

    def test_network_failure_retains_partial_download(self):
        partial=self.file.with_name(self.file.name+'.part')
        partial.write_bytes(b'partial')
        with patch.object(prepare.urllib.request,'urlopen',side_effect=URLError('offline')), \
             patch.object(prepare.time,'sleep'):
            with self.assertRaises(URLError):
                prepare.download('https://example.invalid/input',self.file,self.sha,len(self.data))
        self.assertEqual(partial.read_bytes(),b'partial')

    def test_driver_changes_and_extra_files_are_rejected(self):
        source=self.root/'source';source.mkdir()
        p=source/'driver.cpp';p.write_bytes(self.data)
        manifest={'files':[{'path':'driver.cpp','sha256':self.sha}]}
        prepare.verify_source(source,manifest)
        p.write_text('local changes')
        with self.assertRaisesRegex(ValueError,'modified'):
            prepare.verify_source(source,manifest)
        self.assertEqual(p.read_text(),'local changes')
        p.write_bytes(self.data);(source/'extra.cpp').write_text('extra')
        with self.assertRaisesRegex(ValueError,'file set'):
            prepare.verify_source(source,manifest)

    def test_dependency_paths_cannot_escape_root(self):
        for value in ('../outside','/absolute','a/../../outside','a\\outside',''):
            with self.subTest(value=value),self.assertRaises(ValueError):
                prepare.safe_relative(value)

    def test_dataset_tar_traversal_is_rejected(self):
        archive=self.root/'bad.tar'
        with tarfile.open(archive,'w') as stream:
            info=tarfile.TarInfo('../outside');info.size=4
            stream.addfile(info,io.BytesIO(b'data'))
        output=self.root/'assets';output.mkdir()
        with self.assertRaises(tarfile.FilterError):
            prepare.extract_dataset(archive,output)
        self.assertFalse((self.root/'outside').exists())


if __name__=='__main__':unittest.main()
