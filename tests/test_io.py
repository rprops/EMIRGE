"""Tests functions in Emirge.io"""

import re
import os
from StringIO import StringIO
from subprocess import Popen, PIPE
from tempfile import NamedTemporaryFile
from Emirge import io
from nose.tools import assert_true, assert_false, assert_equal, assert_raises

# === FASTA test data ===

# sequence formatted at 60 cols
fasta_sample_60 = """>id123
GUGCAAAGUUGUGUAGUGCGAUCGGUGGAUGCCUUGGCACCAAGAGCCGAUGAAGGACGU
UGUGACCUGCGAUAAGCCCUGGGGAGUUGGUGAGCGAGCUGUGAUCCGGGGGUGUCCGAA
UGGGGAAACCUGGAAUGUCCGGAGUAGUGUCCGGUGGCCCUGCCCUGAAUGUAUAGGGGU
GUGGGUGGUAACGCGGGGAAGUGAAACAUCUUAGUACCCGUAGGAAGAGAAAACAAGUGU
"""

# same sequence formated at 77 cols
fasta_sample_77 = """>id123
GUGCAAAGUUGUGUAGUGCGAUCGGUGGAUGCCUUGGCACCAAGAGCCGAUGAAGGACGUUGUGACCUGCGAUAAGC
CCUGGGGAGUUGGUGAGCGAGCUGUGAUCCGGGGGUGUCCGAAUGGGGAAACCUGGAAUGUCCGGAGUAGUGUCCGG
UGGCCCUGCCCUGAAUGUAUAGGGGUGUGGGUGGUAACGCGGGGAAGUGAAACAUCUUAGUACCCGUAGGAAGAGAA
AACAAGUGU
"""

# same sequence, one line
sequence_sample = (
    "GUGCAAAGUUGUGUAGUGCGAUCGGUGGAUGCCUUGGCACCAAGAGCCGAUGAAGGACGU"
    "UGUGACCUGCGAUAAGCCCUGGGGAGUUGGUGAGCGAGCUGUGAUCCGGGGGUGUCCGAA"
    "UGGGGAAACCUGGAAUGUCCGGAGUAGUGUCCGGUGGCCCUGCCCUGAAUGUAUAGGGGU"
    "GUGGGUGGUAACGCGGGGAAGUGAAACAUCUUAGUACCCGUAGGAAGAGAAAACAAGUGU"
)

read_file_1 = "tests/test_data/ten_seq_community_000_50K_L150_I350.2.fastq"

# === helper functions ===


def assert_re_match(regex, string):
    try:
        assert re.match(regex, string) is not None
    except AssertionError as e:
        e.args += ('"{}" does not match regex "{}"'.format(string, regex),)
        raise


# === test functions ===

def test_Record_empty():
    record = io.Record()
    assert record.title == ""
    assert record.sequence == ""
    assert str(record) == ">\n\n"


def test_Record_formatting():
    record = io.Record(title="id123", sequence=sequence_sample)
    assert str(record) == fasta_sample_60


def test_FastIterator():
    n = 10
    fasta_file = StringIO(fasta_sample_77 * n)
    i = 0
    for record in io.FastIterator(fasta_file):
        assert str(record) == fasta_sample_60
        i += 1
    assert i == n


def cmp_reindexed_fq_files(orig, reindexed, nseq):
    orig.seek(0)
    lineno = 0
    for sline, dline in zip(orig, reindexed):
        if lineno % 4 == 0:
            assert_equal(dline.rstrip(), "@" + str(lineno/4))
        else:
            assert_equal(dline, sline)
        lineno += 1
    assert_equal(nseq, lineno / 4)


def test_reindex_reads():
    nlines = 4 * 1200

    # prep input files
    src = NamedTemporaryFile()
    with open(read_file_1) as f:
        for line, n in zip(f, range(0, nlines)):
            src.write(line)

    src.flush()

    dst, n_reads = io.reindex_reads(src.name)
    assert_equal(n_reads, nlines / 4)
    cmp_reindexed_fq_files(src, dst, n_reads)


def test_reindex_reads_zipped():
    nlines = 4 * 1200
    # prep input files
    src = NamedTemporaryFile(suffix=".gz")
    zipper = Popen(["gzip", "-c"], stdin=PIPE, stdout=src)

    with open(read_file_1) as f:
        for line, n in zip(f, range(0, nlines)):
            zipper.stdin.write(line)

    zipper.stdin.close()
    zipper.wait()
    src.flush()

    dst, n_reads = io.reindex_reads(src.name)

    assert_equal(n_reads, nlines / 4)
    with open(read_file_1) as f:
        cmp_reindexed_fq_files(f, dst, n_reads)


def test_NamedPipe():
    pipe = io.NamedPipe()
    pipe_file = pipe.name
    assert_true(io.ispipe(pipe_file))
    del pipe
    assert_false(io.ispipe(pipe_file))


def test_InputFileName():
    io.InputFileName(read_file_1, check=True)
    with assert_raises(Exception) as ex:
        io.InputFileName("/tmp", check=True)
    assert_re_match(".*is a dir.*", ex.exception.args[0])
    with assert_raises(Exception) as ex:
        io.InputFileName("/tmp/this_should_not_exist_d9js9d$HHx", check=True)
    assert_re_match(".*does not exist.*", ex.exception.args[0])
    tmpfile = NamedTemporaryFile()
    os.chmod(tmpfile.name, 0)
    with assert_raises(Exception) as ex:
        io.InputFileName(tmpfile.name, check=True)
    assert_re_match(".*cannot be read.*", ex.exception.args[0])


def test_OutputFileName():
    io.OutputFileName("/tmp/valid_output_file_lkjad9k", check=True)
    with assert_raises(Exception) as ex:
        io.OutputFileName("/tmp")
    assert_re_match(".*is a dir.*", ex.exception.args[0])
    with assert_raises(Exception) as ex:
        io.OutputFileName("/sbin/cannot_write_here")
    assert_re_match(".*directory is not writable.*", ex.exception.args[0])
    with assert_raises(Exception) as ex:
        io.OutputFileName("/this_path_no_exists/filename")
    assert_re_match(".*directory does not exist.*", ex.exception.args[0])
    tmpfile = NamedTemporaryFile()
    with assert_raises(Exception) as ex:
        io.OutputFileName(tmpfile.name, overwrite=False)
    assert_re_match(".*cowardly refusing to overwrite.*", ex.exception.args[0])
    os.chmod(tmpfile.name, 0)
    with assert_raises(Exception) as ex:
        io.OutputFileName(tmpfile.name, overwrite=True)
    assert_re_match(".*write protected.*", ex.exception.args[0])


def test_decompressed():
    data = ["this is a test\n", "and a second line\n"]
    methods = [("gzip", "gz"), ("lz4", "lz4"),
               ("xz", "xz"), ("bzip2", "bz2")]

    for compressor, suffix in methods:
        src = NamedTemporaryFile(suffix="."+suffix)
        zipper = io.Popen([compressor, "-c"], stdin=PIPE, stdout=src).stdin
        zipper.writelines(data)
        zipper.close()
        src.flush()

        with io.decompressed(src.name).reader() as f:
            for orig, test in zip(data, f):
                assert_equal(orig, test)


def test_EnumerateReads():
    ereads = io.EnumerateReads(io.File(read_file_1))
    i = 0
    with ereads as reads:
        for line in reads:
            i += 1
    with ereads as reads:
        for line in reads:
            i += 1
    with ereads as reads, open(read_file_1) as orig_reads:
        cmp_reindexed_fq_files(orig_reads, reads, 50000)


def test_FastqCountReads():
    n_reads = io.fastq_count_reads(read_file_1)
    assert_equal(n_reads, 50000)


def test_Pipe_chained():
    data = io.File(read_file_1)
    with io.Gunzip(io.Gzip(data)) as f, open(read_file_1) as g:
        for fline, gline in zip(f, g):
            assert_equal(fline, gline)


def test_Pipe_cmdsubst():
    cmd = ["cat", io.EnumerateReads(io.File(read_file_1)),
           io.EnumerateReads(io.File(read_file_1))]
    pipe = io.make_pipe("test", cmd)
    i = 0
    with pipe(None) as f:
        for line in f:
            i += 1

    assert_equal(i, 400000)
