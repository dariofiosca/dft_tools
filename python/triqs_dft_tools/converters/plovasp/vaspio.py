
################################################################################
#
# TRIQS: a Toolbox for Research in Interacting Quantum Systems
#
# Copyright (C) 2011 by M. Ferrero, O. Parcollet
#
# DFT tools: Copyright (C) 2011 by M. Aichhorn, L. Pourovskii, V. Vildosola
#
# PLOVasp: Copyright (C) 2015 by O. E. Peil
#
# TRIQS is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# TRIQS is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# TRIQS. If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
r"""
    plovasp.vaspio
    ==============

    Input of required VASP data.

    Six VASP files are required:
      - PROJCAR
      - LOCPROJ
      - POSCAR
      - IBZKPT
      - EIGENVAL
      - DOSCAR
"""
import numpy as np
import re
#import plocar_io.c_plocar_io as c_plocar_io

def read_lines(filename):
    r"""
    Generator of lines for a file

    Parameters
    ----------

    filename (str) : name of the file
    """
    with open(filename, 'r') as f:
        for line in f:
            yield line

################################################################################
################################################################################
#
# class VaspData
#
################################################################################
################################################################################
class VaspData:
    """
    Container class for all VASP data.
    """
    def __init__(self, vasp_dir, read_all=True, efermi_required=True):
        self.vasp_dir = vasp_dir

        self.plocar = Plocar()
        self.poscar = Poscar()
        self.kpoints = Kpoints()
        self.eigenval = Eigenval()
        self.doscar = Doscar()

        if read_all:
            self.plocar.from_file(vasp_dir)
            self.poscar.from_file(vasp_dir)
            self.kpoints.from_file(vasp_dir)
            try:
                self.eigenval.from_file(vasp_dir)
            except (IOError, StopIteration):
                self.eigenval.eigs = None
                self.eigenval.ferw = None
                print("!!! WARNING !!!: Error reading from EIGENVAL, trying LOCPROJ")
            try:
                self.doscar.from_file(vasp_dir)
            except (IOError, StopIteration):
                if efermi_required:
                    print("!!! WARNING !!!: Error reading from Efermi from DOSCAR, trying LOCPROJ")
                    try:
                        self.plocar.efermi
                        self.doscar.efermi = self.plocar.efermi
                    except NameError:
                        raise Exception("Efermi cannot be read from DOSCAR or LOCPROJ")
                else:
# TODO: This a hack. Find out a way to determine ncdij without DOSCAR
                    print("!!! WARNING !!!: Error reading from DOSCAR, taking Efermi from config")
                    self.doscar.ncdij = self.plocar.nspin

################################################################################
################################################################################
#
# class Plocar
#
################################################################################
################################################################################
class Plocar:
    """
    Class containing raw PLO data from VASP.

    Properties:
        - *plo* (numpy.array((nion, ns, nk, nb, nlmmax))) : raw projectors
        - *params* (dict) : parameters read from PLOCAR
        - *ferw* (array(nion, ns, nk, nb)) : Fermi weights from VASP

    """
    def __init__(self):
        self.plo = None
        self.proj_params = None

    def from_file(self, vasp_dir='./', plocar_filename='PLOCAR'):
        r"""
        Reads non-normalized projectors from a binary file (`PLOCAR' by default)
        generated by VASP PLO interface.

        Parameters
        ----------

        vasp_dir (str) : path to the VASP working directory [default = `./']
        plocar_filename (str) : filename [default = `PLOCAR']

        """
# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

#        self.params, self.plo, self.ferw = c_plocar_io.read_plocar(vasp_dir + plocar_filename)
#        self.proj_params, self.plo = self.temp_parser(projcar_filename=vasp_dir + "PROJCAR", locproj_filename=vasp_dir + "LOCPROJ")
        self.proj_params, self.plo = self.locproj_parser(locproj_filename=vasp_dir + "LOCPROJ")


    def locproj_parser(self, locproj_filename='LOCPROJ'):
        r"""
        Parses LOCPROJ (for VASP >= 5.4.2) to get VASP projectors.

        This is a prototype parser that should eventually be written in C for
        better performance on large files.

        Returns projector parameters (site/orbital indices etc.) and an array
        with projectors.
        """
        orb_labels = ["s", "py", "pz", "px", "dxy", "dyz", "dz2", "dxz", "dx2-y2",
                      "fy(3x2-y2)", "fxyz", "fyz2", "fz3", "fxz2", "fz(x2-y2)", "fx(x2-3y2)"]

        def lm_to_l_m(lm):
            l = int(np.sqrt(lm))
            m = lm - l*l
            return l, m

# Read the first line of LOCPROJ to get the dimensions
        with open(locproj_filename, 'rt') as f:
            line = f.readline()
            line = line.split("#")[0]
            sline = line.split()
            self.ncdij, nk, self.nband, nproj = list(map(int, sline[0:4]))
            
            # VASP.6.
            self.nspin = self.ncdij if self.ncdij < 4 else 1
            print("ISPIN is {}".format(self.nspin))            
            
            self.nspin_band = 2 if self.ncdij == 2 else 1

            try:
                self.efermi = float(sline[4])
            except:
                print("!!! WARNING !!!: Error reading E-Fermi from LOCPROJ, trying DOSCAR")

            plo = np.zeros((nproj, self.nspin, nk, self.nband), dtype=np.complex128)
            proj_params = [{} for i in range(nproj)]

            iproj_site = 0
            is_first_read = True
            
            # VASP.6.
            if self.ncdij == 4:
                self.nc_flag = 1
                self.ncdij = 1
            else:
                self.nc_flag = 0
            print("NC FLAG : {}".format(self.nc_flag))

# First read the header block with orbital labels
            line = self.search_for(f, "^ *ISITE")
            ip = 0
            while line:
                sline = line.split(':')
                isite = int(sline[1].split()[0])
                label = sline[-1].strip()
                lm = orb_labels.index(label)
                l, m = lm_to_l_m(lm)
#                    ip_new = iproj_site * norb + il
#                    ip_prev = (iproj_site - 1) * norb + il
                proj_params[ip]['label'] = label
                proj_params[ip]['isite'] = isite
                proj_params[ip]['l'] = l
                if self.nc_flag == True:
                    if (ip % 2) == 0:
                        proj_params[ip]['m'] = 2*m
                    else:
                        proj_params[ip]['m'] = 2*m + 1
                else:
                    proj_params[ip]['m'] = m

                ip +=1
                
                line = f.readline().strip()
            
            assert ip == nproj, "Number of projectors in the header is wrong in LOCPROJ"

            self.eigs = np.zeros((nk, self.nband, self.nspin_band))
            self.ferw = np.zeros((nk, self.nband, self.nspin_band))

            patt = re.compile("^orbital")

            for ispin in range(self.nspin):
                for ik in range(nk):
                    for ib in range(self.nband):
                        line = ""
                        while not line:
                            line = f.readline().strip()
                        sline = line.split()
                        isp_, ik_, ib_ = list(map(int, sline[1:4]))
                        assert isp_ == ispin + 1 and ik_ == ik + 1 and ib_ == ib + 1, "Inconsistency in reading LOCPROJ"
                        self.eigs[ik, ib, ispin] = float(sline[4])
                        self.ferw[ik, ib, ispin] = float(sline[5])
                        for ip in range(nproj):
                            line = f.readline()
                            sline = line.split()
                            ctmp = complex(float(sline[1]), float(sline[2]))
                            plo[ip, ispin, ik, ib] = ctmp 

        print("Read parameters: LOCPROJ")
        for il, par in enumerate(proj_params):
            print(il, " -> ", par)

        return proj_params, plo


    def search_for(self, f, patt):
        r"""
        Reads file 'f' until pattern 'patt' is encountered and returns
        the corresponding line.
        """
        cpatt = re.compile(patt)
        line = "x"
        while not re.match(cpatt, line) and line:
            line = f.readline()

        return line


################################################################################
################################################################################
#
# class Poscar
#
################################################################################
################################################################################
class Poscar:
    """
    Class containing POSCAR data from VASP.

    Properties:
        - nq (int) : total number of ions
        - ntypes ([int]) : number of ion types
        - nions (int) : a list of number of ions of each type
        - a_brav (numpy.array((3, 3), dtype=float)) : lattice vectors
        - kpt_basis (numpy.array((3, 3), dtype=float)) : reciprocal lattice vectors
        - q_types ([numpy.array((nions, 3), dtype=float)]) : a list of
          arrays each containing fractional coordinates of ions of a given type
    """
    def __init__(self):
        self.q_cart = None

    def from_file(self, vasp_dir='./', poscar_filename='POSCAR'):
        """
        Reads POSCAR and returns a dictionary.

        Parameters
        ----------

        vasp_dir (str) : path to the VASP working directory [default = `./']
        plocar_filename (str) : filename [default = `POSCAR']

        """
# Convenince local function
        def readline_remove_comments():
            return next(f).split('!')[0].split('#')[0].strip()

# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

        f = read_lines(vasp_dir + poscar_filename)
# Comment line
        comment = next(f).rstrip()
        print("  Found POSCAR, title line: %s"%(comment))

# Read scale
        sline = readline_remove_comments()
        ascale = float(sline)
# Read lattice vectors
        self.a_brav = np.zeros((3, 3))
        for ia in range(3):
            sline = readline_remove_comments()
            self.a_brav[ia, :] = list(map(float, sline.split()))
# Negative scale means that it is a volume scale
        if ascale < 0:
            vscale = -ascale
            vol = np.linalg.det(self.a_brav)
            ascale = (vscale / vol)**(1.0/3)

        self.a_brav *= ascale

# Depending on the version of VASP there could be
# an extra line with element names
        sline = readline_remove_comments()
        try:
# Old v4.6 format: no element names
            self.nions = list(map(int, sline.split()))
            self.el_names = ['El%i'%(i) for i in range(len(self.nions))]
        except ValueError:
# New v5.x format: read element names first
            self.el_names = sline.split()
            sline = readline_remove_comments()
            self.nions = list(map(int, sline.split()))

# Set the number of atom sorts (types) and the total
# number of atoms in the unit cell
        self.ntypes = len(self.nions)
        self.nq = sum(self.nions)

# Check for the line 'Selective dynamics' (and ignore it)
        sline = readline_remove_comments()
        if sline[0].lower() == 's':
            sline = readline_remove_comments()

# Check whether coordinates are cartesian or fractional
        cartesian = (sline[0].lower() in 'ck')
        # determine reciprocal basis in units of 2*pi
        self.kpt_basis = np.linalg.inv(self.a_brav.T)

# Read atomic positions
        self.q_types = []
        self.type_of_ion = []
        for it in range(self.ntypes):
# Array mapping ion index to type
            self.type_of_ion += self.nions[it] * [it]

            q_at_it = np.zeros((self.nions[it], 3))
            for iq in range(self.nions[it]):
                sline = readline_remove_comments()
                qcoord = list(map(float, sline.split()[:3]))
                if cartesian:
                    qcoord = np.dot(self.kpt_basis, qcoord)
                q_at_it[iq, :] = qcoord

            self.q_types.append(q_at_it)

        print("  Total number of ions:", self.nq)
        print("  Number of types:", self.ntypes)
        print("  Number of ions for each type:", self.nions)

#        print
#        print "  Coords:"
#        for it in range(ntypes):
#            print "    Element:", el_names[it]
#            print q_at[it]

################################################################################
################################################################################
#
# class Kpoints
#
################################################################################
################################################################################
class Kpoints:
    """
    Class describing k-points and optionally tetrahedra.

    Properties:
        - nktot (int) : total number of k-points in the IBZ
        - kpts (numpy.array((nktot, 3), dtype=float)) : k-point vectors (fractional coordinates)
        - ntet (int) : total number of k-point tetrahedra
        - itet (numpy.array((ntet, 5), dtype=float) : array of tetrahedra
        - volt (float) : volume of a tetrahedron (the k-grid is assumed to
              be uniform)
    """
    def __init__(self):
        self.kpts = None
        self.nktot = None
        self.kwghts = None
#
# Reads IBZKPT file
#
    def from_file(self, vasp_dir='./', ibz_filename='IBZKPT'):
        """
        Reads from IBZKPT: k-points and optionally
        tetrahedra topology (if present).

        Parameters
        ----------

        vasp_dir (str) : path to the VASP working directory [default = `./']
        plocar_filename (str) : filename [default = `IBZKPT']

        """

# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

        ibz_file = read_lines(vasp_dir + ibz_filename)

#   Skip comment line
        line = next(ibz_file)
#   Number of k-points
        line = next(ibz_file)
        self.nktot = int(line.strip().split()[0])

        print()
        print("   {0:>26} {1:d}".format("Total number of k-points:", self.nktot))

        self.kpts = np.zeros((self.nktot, 3))
        self.kwghts = np.zeros((self.nktot))

#   Skip comment line
        line = next(ibz_file)
        for ik in range(self.nktot):
            line = next(ibz_file)
            sline = line.strip().split()
            self.kpts[ik, :] = list(map(float, sline[:3]))
            self.kwghts[ik] = float(sline[3])

        self.kwghts /= self.nktot

# Attempt to read tetrahedra
#   Skip comment line ("Tetrahedra")
        try:
            line = next(ibz_file)

#   Number of tetrahedra and volume = 1/(6*nkx*nky*nkz)
            line = next(ibz_file)
            sline = line.split()
            self.ntet = int(sline[0])
            self.volt = float(sline[1])

            print("   {0:>26} {1:d}".format("Total number of tetrahedra:", self.ntet))

#   Traditionally, itet[it, 0] contains multiplicity
            self.itet = np.zeros((self.ntet, 5), dtype=int)
            for it in range(self.ntet):
               line = next(ibz_file)
               self.itet[it, :] = list(map(int, line.split()[:5]))
        except StopIteration as ValueError:
            print("  No tetrahedron data found in %s. Skipping..."%(ibz_filename))
            self.ntet = 0

#        data = { 'nktot': nktot,
#                 'kpts': kpts,
#                 'ntet': ntet,
#                 'itet': itet,
#                 'volt': volt }
#
#        return data


################################################################################
################################################################################
#
# class Eigenval
#
################################################################################
################################################################################
class Eigenval:
    """
    Class containing Kohn-Sham-eigenvalues data from VASP (EIGENVAL file).
    """
    def __init__(self):
        self.eigs = None
        self.ferw = None

    def from_file(self, vasp_dir='./', eig_filename='EIGENVAL'):
        """
        Reads eigenvalues from EIGENVAL. Note that the file also
        contains k-points with weights. They are also stored and
        then used to check the consistency of files read.
        """

# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

        f = read_lines(vasp_dir + eig_filename)

# First line: only the first and the last number out of four
# are used; these are 'nions' and 'ispin'
        sline = next(f).split()
        self.nq = int(sline[0])
        self.ispin = int(sline[3])

# Second line: cell volume and lengths of lattice vectors (skip)
        sline = next(f)

# Third line: temperature (skip)
        sline = next(f)

# Fourth and fifth line: useless
        sline = next(f)
        sline = next(f)

# Sixth line: NELECT, NKTOT, NBTOT
        sline = next(f).split()
        self.nelect = int(sline[0])
        self.nktot = int(sline[1])
        self.nband = int(sline[2])

# Set of eigenvalues and k-points
        self.kpts = np.zeros((self.nktot, 3))
        self.kwghts = np.zeros((self.nktot,))
        self.eigs = np.zeros((self.nktot, self.nband, self.ispin))
        self.ferw = np.zeros((self.nktot, self.nband, self.ispin))

        for ik in range(self.nktot):
            sline = next(f) # Empty line
            sline = next(f) # k-point info
            tmp = list(map(float, sline.split()))
            self.kpts[ik, :] = tmp[:3]
            self.kwghts[ik] = tmp[3]

            for ib in range(self.nband):
                sline = next(f).split()
                tmp = list(map(float, sline))
                assert len(tmp) == 2 * self.ispin + 1, "EIGENVAL file is incorrect (probably from old versions of VASP)"
                self.eigs[ik, ib, :] = tmp[1:self.ispin+1]
                self.ferw[ik, ib, :] = tmp[self.ispin+1:]


################################################################################
################################################################################
#
# class Doscar
#
################################################################################
################################################################################
class Doscar:
    """
    Class containing some data from DOSCAR
    """
    def __init__(self):
        self.ncdij = None
        self.efermi = None

    def from_file(self, vasp_dir='./', dos_filename='DOSCAR'):
        """
        Reads only E_Fermi from DOSCAR.
        """

# Add a slash to the path name if necessary
        if vasp_dir[-1] != '/':
            vasp_dir += '/'

        f = read_lines(vasp_dir + dos_filename)

# First line: NION, NION, JOBPAR, NCDIJ
        sline = next(f).split()
    
# Skip next 4 lines
        for _ in range(4):
            sline = next(f)

# Sixth line: EMAX, EMIN, NEDOS, EFERMI, 1.0
        sline = next(f).split()
        self.efermi = float(sline[3])

# TODO: implement output of SYMMCAR in VASP and read it here
################################################################
#
# Reads SYMMCAR
#
################################################################
def read_symmcar(vasp_dir, symm_filename='SYMMCAR'):
    """
    Reads SYMMCAR.
    """
#   Shorthand for simple parsing
    def extract_int_par(parname):
        return int(re.findall(parname + '\s*=\s*(\d+)', line)[-1])

# Add a slash to the path name if necessary
    if vasp_dir[-1] != '/':
        vasp_dir += '/'

    symmcar_exist = False
    sym_file = read_lines(vasp_dir + symm_filename)
    line = next(sym_file)
    nrot = extract_int_par('NROT')

    line = next(sym_file)
    ntrans = extract_int_par('NPCELL')
#   Lmax
    line = next(sym_file)
    lmax = extract_int_par('LMAX')
    mmax = 2 * lmax + 1
#   Nion
    line = next(sym_file)
    nion = extract_int_par('NION')

    print("   {0:>26} {1:d}".format("Number of rotations:", nrot))
    print("   {0:>26} {1:d}".format("Number of translations:", ntrans))
    print("   {0:>26} {1:d}".format("Number of ions:", nion))
    print("   {0:>26} {1:d}".format("L_max:", lmax))

    rot_mats = np.zeros((nrot, lmax+1, mmax, mmax))
    rot_map = np.zeros((nrot, ntrans, nion), dtype=np.int32)

    for irot in range(nrot):
#   Empty line
        line = next(sym_file)
#   IROT index (skip it)
        line = next(sym_file)
#   ISYMOP matrix (can be also skipped)
        line = next(sym_file)
        line = next(sym_file)
        line = next(sym_file)

#   Skip comment "  Permutation map..."
        line = next(sym_file)
#   Permutations (in chunks of 20 indices per line)
        for it in range(ntrans):
            for ibl in range((nion - 1) // 20 + 1):
                i1 = ibl * 20
                i2 = (ibl + 1) * 20
                line = next(sym_file)
                rot_map[irot, it, i1:i2] = list(map(int, line.split()))

            for l in range(lmax + 1):
                mmax = 2 * l + 1
#   Comment: "L = ..."
            line = next(sym_file)
            for m in range(mmax):
                line = next(sym_file)
                rot_mats[irot, l, m, :mmax] = list(map(float, line.split()[:mmax]))

    data.update({ 'nrot': nrot, 'ntrans': ntrans,
                  'lmax': lmax, 'nion': nion,
                  'sym_rots': rot_mats, 'perm_map': rot_map })
