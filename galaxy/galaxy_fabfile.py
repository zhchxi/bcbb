"""Fabric deployment file to set up Galaxy plus associated data files.

Fabric (http://docs.fabfile.org) is used to manage the automation of
a remote server.

Usage:
    fab -f galaxy_fabfile.py servername deploy_galaxy
"""
import os
from contextlib import contextmanager

from fabric.api import *
from fabric.contrib.files import *

# -- Host specific setup for various groups of servers.

env.include_arachne = True

def mothra():
    """Setup environment for mothra.
    """
    env.user = 'chapman'
    env.hosts = ['mothra']
    env.path = '/home/chapman/install/web/galaxy-central'
    env.galaxy_files = '/store3/galaxy_files'
    env.install_dir = '/source'
    env.shell = "/bin/zsh -l -i -c"

def galaga():
    """Setup environment for galaga.
    """
    env.user = 'chapman'
    env.hosts = ['galaga']
    env.path = '/source/galaxy/web'
    env.galaxy_files = '/source/galaxy'
    env.install_dir = '/source'
    env.shell = "/bin/zsh -l -i -c"
    env.include_arachne = False

def localhost():
    """Setup environment for local authentication.
    """
    env.user = 'chapmanb'
    env.hosts = ['localhost']
    env.shell = '/usr/local/bin/bash -l -c'
    env.path = '/home/chapmanb/tmp/galaxy-central'

# -- Configuration for genomes to download and prepare

class _DownloadHelper:
    def _exists(self, fname, seq_dir):
        """Check if a file exists in either download or final destination.
        """
        return exists(fname) or exists(os.path.join(seq_dir, fname))

class UCSCGenome(_DownloadHelper):
    def __init__(self, genome_name):
        self._name = genome_name
        self._url = "ftp://hgdownload.cse.ucsc.edu/goldenPath/%s/bigZips" % \
                genome_name

    def download(self, seq_dir):
        for zipped_file in ["chromFa.tar.gz", "%s.fa.gz" % self._name,
                            "chromFa.zip"]:
            if not self._exists(zipped_file, seq_dir):
                with settings(warn_only=True):
                    result = run("wget %s/%s" % (self._url, zipped_file))
                if not result.failed:
                    break
            else:
                break
        genome_file = "%s.fa" % self._name
        if not self._exists(genome_file, seq_dir):
            if zipped_file.endswith(".tar.gz"):
                run("tar -xzpf %s" % zipped_file)
            elif zipped_file.endswith(".zip"):
                run("unzip %s" % zipped_file)
            elif zipped_file.endswith(".gz"):
                run("gunzip -c %s > out.fa" % zipped_file)
            else:
                raise ValueError("Do not know how to handle: %s" % zipped_file)
            tmp_file = genome_file.replace(".fa", ".txt")
            with settings(warn_only=True):
                result = run("ls *.fa")
            # some UCSC downloads have the files in multiple directories
            # mv them to the parent directory and delete the child directories
            if result.failed:
                run("find . -name '*.fa' -a \! -name '*_random.fa' -a \! -name 'chrUn*' -exec mv {} . \;")
                run("find . -type d -a \! -name '\.' | xargs rm -rf")
            result = run("find . -name '*.fa' -a \! -name '*random.fa' -a \! " \
                         "-name '*hap*.fa' | xargs cat > %s" % tmp_file)
            run("rm -f *.fa")
            run("mv %s %s" % (tmp_file, genome_file))
        return genome_file, [zipped_file]

class NCBIRest(_DownloadHelper):
    """Retrieve files using the TogoWS REST server pointed at NCBI.
    """
    def __init__(self, name, refs):
        self._name = name
        self._refs = refs
        self._base_url = "http://togows.dbcls.jp/entry/genbank/%s.fasta"

    def download(self, seq_dir):
        genome_file = "%s.fa" % self._name
        if not self._exists(genome_file, seq_dir):
            for ref in self._refs:
                run("wget %s" % (self._base_url % ref))
                run("ls -l")
                run("sed -i.bak -r -e '/1/ s/^>.*$/>%s/g' %s.fasta" % (ref,
                    ref))
                # sed in Fabric does not cd properly?
                #sed('%s.fasta' % ref, '^>.*$', '>%s' % ref, '1')
            tmp_file = genome_file.replace(".fa", ".txt")
            run("cat *.fasta > %s" % tmp_file)
            run("rm -f *.fasta")
            run("rm -f *.bak")
            run("mv %s %s" % (tmp_file, genome_file))
        return genome_file, []

class EnsemblGenome(_DownloadHelper):
    """Retrieve genome FASTA files from Ensembl.

    ftp://ftp.ensemblgenomes.org/pub/plants/release-3/fasta/arabidopsis_thaliana/dna/Arabidopsis_thaliana.TAIR9.55.dna.toplevel.fa.gz
    ftp://ftp.ensembl.org/pub/release-56/fasta/caenorhabditis_elegans/dna/Caenorhabditis_elegans.WS200.56.dna.toplevel.fa.gz
    """
    def __init__(self, ensembl_section, release_number, release2, organism,
            name):
        if ensembl_section == "standard":
            url = "ftp://ftp.ensembl.org/pub/"
        else:
            url = "ftp://ftp.ensemblgenomes.org/pub/%s/" % ensembl_section
        url += "release-%s/fasta/%s/dna/" % (release_number, organism.lower())
        self._url = url
        self._get_file = "%s.%s.%s.dna.toplevel.fa.gz" % (organism, name,
                release2)
        self._name = name

    def download(self, seq_dir):
        genome_file = "%s.fa" % self._name
        if not self._exists(self._get_file, seq_dir):
            run("wget %s%s" % (self._url, self._get_file))
        if not self._exists(genome_file, seq_dir):
            run("gunzip -c %s > %s" % (self._get_file, genome_file))
        return genome_file, [self._get_file]

genomes = [
           ("phiX174", "phix", NCBIRest("phix", ["NC_001422.1"])),
           ("Scerevisiae", "sacCer2", UCSCGenome("sacCer2")),
           ("Mmusculus", "mm9", UCSCGenome("mm9")),
           ("Hsapiens", "hg18", UCSCGenome("hg18")),
           ("Rnorvegicus", "rn4", UCSCGenome("rn4")),
           ("Xtropicalis", "xenTro2", UCSCGenome("xenTro2")),
           ("Athaliana", "araTha_tair9", EnsemblGenome("plants", "3", "55",
               "Arabidopsis_thaliana", "TAIR9")),
           ("Celegans", "WS200", EnsemblGenome("standard", "56", "56",
               "Caenorhabditis_elegans", "WS200")),
           ("Dmelanogaster", "BDGP5.13", EnsemblGenome("metazoa", "4", "55",
               "Drosophila_melanogaster", "BDGP5.13")),
           ("Mtuberculosis_H37Rv", "mycoTube_H37RV", NCBIRest("mycoTube_H37RV",
               ["NC_000962"])),
           ("Msmegmatis", "92", NCBIRest("92", ["NC_008596.1"])),
           ("Paeruginosa_UCBPP-PA14", "386", NCBIRest("386", ["CP000438.1"])),
          ]

lift_over_genomes = ['hg18', 'hg19', 'mm9', 'xenTro2', 'rn4']

# -- Fabric instructions

def deploy_galaxy():
    """Deploy a Galaxy server along with associated data files.
    """
    _required_libraries()
    _support_programs()
    #latest_code()
    _setup_ngs_tools()
    _setup_liftover()

# == Decorators and context managers

def _if_not_installed(pname):
    def argcatcher(func):
        def decorator(*args, **kwargs):
            with settings(
                    hide('warnings', 'running', 'stdout', 'stderr'),
                    warn_only=True):
                result = run(pname)
            if result.return_code == 127:
                return func(*args, **kwargs)
        return decorator
    return argcatcher

@contextmanager
def _make_tmp_dir():
    work_dir = os.path.join(env.galaxy_files, "tmp")
    if not exists(work_dir):
        run("mkdir %s" % work_dir)
    yield work_dir
    if exists(work_dir):
        run("rm -rf %s" % work_dir)

# == NGS

def _setup_ngs_tools():
    """Install next generation tools. Follows Galaxy docs at:

    http://bitbucket.org/galaxy/galaxy-central/wiki/NGSLocalSetup
    """
    _install_ngs_tools()
    _setup_ngs_genomes()

def _install_ngs_tools():
    """Install external next generation sequencing tools.
    """
    _install_bowtie()
    _install_bwa()
    _install_samtools()
    _install_fastx_toolkit()
    _install_maq()

@_if_not_installed("bowtie")
def _install_bowtie():
    """Install the bowtie short read aligner.
    """
    version = "0.12.3"
    url = "http://downloads.sourceforge.net/project/bowtie-bio/bowtie/%s/" \
          "bowtie-%s-linux-x86_64.zip" % (version, version)
    install_dir = os.path.join(env.install_dir, "bin")
    with _make_tmp_dir() as work_dir:
        with cd(work_dir):
            run("wget %s" % url)
            run("unzip %s" % os.path.split(url)[-1])
            with cd("bowtie-%s" % version):
                for fname in run("ls bowtie*").split("\n"):
                    run("mv -f %s %s" % (fname, install_dir))

@_if_not_installed("bwa")
def _install_bwa():
    version = "0.5.7"
    url = "http://downloads.sourceforge.net/project/bio-bwa/bwa-%s.tar.bz2" % (
            version)
    install_dir = os.path.join(env.install_dir, "bin")
    with _make_tmp_dir() as work_dir:
        with cd(work_dir):
            run("wget %s" % url)
            run("tar -xjvpf %s" % (os.path.split(url)[-1]))
            with cd("bwa-%s" % version):
                run("make")
                run("mv bwa %s" % install_dir)
                run("mv solid2fastq.pl %s" % install_dir)
                run("mv qualfa2fq.pl %s" % install_dir)

@_if_not_installed("samtools")
def _install_samtools():
    version = "0.1.7"
    vext = "a"
    url = "http://downloads.sourceforge.net/project/samtools/samtools/%s/" \
            "samtools-%s%s.tar.bz2" % (version, version, vext)
    install_dir = os.path.join(env.install_dir, "bin")
    with _make_tmp_dir() as work_dir:
        with cd(work_dir):
            run("wget %s" % url)
            run("tar -xjvpf %s" % (os.path.split(url)[-1]))
            with cd("samtools-%s%s" % (version, vext)):
                run("sed -i.bak -r -e 's/-lcurses/-lncurses/g' Makefile")
                #sed("Makefile", "-lcurses", "-lncurses")
                run("make")
                for install in ["samtools", "misc/maq2sam-long"]:
                    run("mv -f %s %s" % (install, install_dir))

@_if_not_installed("fastq_quality_boxplot_graph.sh")
def _install_fastx_toolkit():
    version = "0.0.13"
    gtext_version = "0.6"
    url_base = "http://hannonlab.cshl.edu/fastx_toolkit/"
    fastx_url = "%sfastx_toolkit-%s.tar.bz2" % (url_base, version)
    gtext_url = "%slibgtextutils-%s.tar.bz2" % (url_base, gtext_version)
    with _make_tmp_dir() as work_dir:
        with cd(work_dir):
            run("wget %s" % gtext_url)
            run("tar -xjvpf %s" % (os.path.split(gtext_url)[-1]))
            with cd("libgtextutils-%s" % gtext_version):
                run("./configure --prefix=%s" % (env.install_dir))
                run("make")
                run("make install")
            run("wget %s" % fastx_url)
            run("tar -xjvpf %s" % os.path.split(fastx_url)[-1])
            with cd("fastx_toolkit-%s" % version):
                run("./configure --prefix=%s" % (env.install_dir))
                run("make")
                run("make install")

@_if_not_installed("maq")
def _install_maq():
    version = "0.7.1"
    url = "http://downloads.sourceforge.net/project/maq/maq/%s/maq-%s.tar.bz2" \
            % (version, version)
    with _make_tmp_dir() as work_dir:
        with cd(work_dir):
            run("wget %s" % url)
            run("tar -xjvpf %s" % (os.path.split(url)[-1]))
            with cd("maq-%s" % version):
                run("./configure --prefix=%s" % (env.install_dir))
                run("make")
                run("make install")

def _setup_ngs_genomes():
    """Download and create index files for next generation genomes.
    """
    genome_dir = os.path.join(env.galaxy_files, "genomes")
    if not exists(genome_dir):
        run('mkdir %s' % genome_dir)
    for organism, genome, manager in genomes:
        cur_dir = os.path.join(genome_dir, organism, genome)
        if not exists(cur_dir):
            run('mkdir %s' % cur_dir)
        with cd(cur_dir):
            seq_dir = 'seq'
            ref_file, base_zips = manager.download(seq_dir)
            ref_file = _move_seq_files(ref_file, base_zips, seq_dir)
            bwa_index = _index_bwa(ref_file)
            bowtie_index = _index_bowtie(ref_file)
            maq_index = _index_maq(ref_file)
            if env.include_arachne:
                arachne_index = _index_arachne(ref_file)
            with cd(seq_dir):
                sam_index = _index_sam(ref_file)
        for ref_index_file, cur_index, prefix in [
                ("sam_fa_indices.loc", sam_index, "index"),
                ("bowtie_indices.loc", bowtie_index, ""),
                ("bwa_index.loc", bwa_index, "")]:
            str_parts = [genome, os.path.join(cur_dir, cur_index)]
            if prefix:
                str_parts.insert(0, prefix)
            _update_loc_file(ref_index_file, str_parts)

def _move_seq_files(ref_file, base_zips, seq_dir):
    if not exists(seq_dir):
        run('mkdir %s' % seq_dir)
    for move_file in [ref_file] + base_zips:
        if exists(move_file):
            run("mv %s %s" % (move_file, seq_dir))
    path, fname = os.path.split(ref_file)
    moved_ref = os.path.join(path, seq_dir, fname)
    assert exists(moved_ref), moved_ref
    return moved_ref

def _update_loc_file(ref_file, line_parts):
    """Add a reference to the given genome to the base index file.
    """
    tools_dir = os.path.join(env.path, "tool-data")
    add_str = "\t".join(line_parts)
    with cd(tools_dir):
        if not exists(ref_file):
            run("cp %s.sample %s" % (ref_file, ref_file))
        if not contains(add_str, ref_file):
            append(add_str, ref_file)

def _index_bowtie(ref_file):
    dir_name = "bowtie"
    ref_base = os.path.splitext(os.path.split(ref_file)[-1])[0]
    if not exists(dir_name):
        run("mkdir %s" % dir_name)
        with cd(dir_name):
            run("bowtie-build -f %s %s" % (
                os.path.join(os.pardir, ref_file),
                ref_base))
    return os.path.join(dir_name, ref_base)

def _index_bwa(ref_file):
    dir_name = "bwa"
    local_ref = os.path.split(ref_file)[-1]
    if not exists(dir_name):
        run("mkdir %s" % dir_name)
        with cd(dir_name):
            run("ln -s %s" % os.path.join(os.pardir, ref_file))
            with settings(warn_only=True):
                result = run("bwa index -a bwtsw %s" % local_ref)
            # work around a bug in bwa indexing for small files
            if result.failed:
                run("bwa index %s" % local_ref)
            run("rm -f %s" % local_ref)
    return os.path.join(dir_name, local_ref)

def _index_maq(ref_file):
    dir_name = "maq"
    local_ref = os.path.split(ref_file)[-1]
    binary_out = "%s.bfa" % os.path.splitext(local_ref)[0]
    if not exists(dir_name):
        run("mkdir %s" % dir_name)
        with cd(dir_name):
            run("ln -s %s" % os.path.join(os.pardir, ref_file))
            run("maq fasta2bfa %s %s" % (local_ref,
                binary_out))
    return os.path.join(dir_name, binary_out)

def _index_sam(ref_file):
    (_, local_file) = os.path.split(ref_file)
    if not exists("%s.fai" % local_file):
        run("samtools faidx %s" % local_file)
    return ref_file

def _index_arachne(ref_file):
    """Index for Broad's Arachne aligner.
    """
    dir_name = "arachne"
    ref_base = os.path.splitext(os.path.split(ref_file)[-1])[0]
    if not exists(dir_name):
        run("mkdir %s" % dir_name)
        with cd(dir_name):
            run("ln -s %s" % os.path.join(os.pardir, ref_file))
            ref_file = os.path.split(ref_file)[-1]
            run("MakeLookupTable SOURCE=%s OUT_HEAD=%s" % (ref_file,
                ref_base))
            run("rm -f %s" % ref_file)
    return os.path.join(dir_name, ref_base)

# == Liftover files

def _setup_liftover():
    """Download chain files for running liftOver.

    Does not install liftOver binaries automatically.
    """
    lo_dir = os.path.join(env.galaxy_files, "liftOver")
    if not exists(lo_dir):
        run("mkdir %s" % lo_dir)
    lo_base_url = "ftp://hgdownload.cse.ucsc.edu/goldenPath/%s/liftOver/%s"
    lo_base_file = "%sTo%s.over.chain.gz"
    for g1 in lift_over_genomes:
        for g2 in [g for g in lift_over_genomes if g != g1]:
            g2u = g2[0].upper() + g2[1:]
            cur_file = lo_base_file % (g1, g2u)
            non_zip = os.path.splitext(cur_file)[0]
            worked = False
            with cd(lo_dir):
                if not exists(non_zip):
                    with settings(warn_only=True):
                        result = run("wget %s" % (lo_base_url % (g1, cur_file)))
                    # Lift over back and forths don't always exist
                    # Only move forward if we found the file
                    if not result.failed:
                        worked = True
                        run("gunzip %s" % cur_file)
            if worked:
                ref_parts = [g1, g2, os.path.join(lo_dir, non_zip)]
                _update_loc_file("liftOver.loc", ref_parts)

def _required_libraries():
    """Install galaxy libraries not included in the eggs.
    """
    # -- HDF5
    # wget 'http://www.hdfgroup.org/ftp/HDF5/current/src/hdf5-1.8.4-patch1.tar.bz2'
    # tar -xjvpf hdf5-1.8.4-patch1.tar.bz2
    # ./configure --prefix=/source
    # make && make install
    #
    # -- PyTables http://www.pytables.org/moin
    # wget 'http://www.pytables.org/download/preliminary/pytables-2.2b3/tables-2.2b3.tar.gz'
    # tar -xzvpf tables-2.2b3.tar.gz
    # cd tables-2.2b3
    # python2.6 setup.py build --hdf5=/source
    # python2.6 setup.py install --hdf5=/source
    pass

def _support_programs():
    """Install programs used by galaxy.
    """
    pass
    # gnuplot
    # gcc44-fortran
    # R
    # rpy
    # easy_install gnuplot-py

def latest_code():
    """Pull the latest Galaxy code from bitbucket and update.
    """
    is_new = False
    if not exists(env.path):
        is_new = True
        with cd(os.path.split(env.path)[0]):
            run('hg clone https://chapmanb@bitbucket.org/chapmanb/galaxy-central/')
    with cd(env.path):
        run('hg pull')
        run('hg update')
        if is_new:
            run('sh setup.sh')
        else:
            run('sh manage_db.sh upgrade')
