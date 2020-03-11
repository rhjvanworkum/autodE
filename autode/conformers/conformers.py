from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import rdMolAlign
from autode.config import Config
from autode.log import logger
from autode.geom import calc_distance_matrix
from autode.calculation import Calculation
from autode.exceptions import XYZsNotFound
from autode.methods import get_lmethod


def rdkit_conformer_geometries_are_resonable(conf_xyzs):
    """For a list of xyzs check that the conformers generated by RDKit are sensible. For unusual structures RDKit will
    place all the atoms in the xy plane... which is not very sensible. In this case we'll use conf_gen/cconf_gen
    to try and generate some conformers

    Arguments:
        conf_xyzs (list(list(list))): List of xyzs

    Returns:
        bool: if geoms are reasonable or not
    """
    if len(conf_xyzs) == 1:
        xyzs = conf_xyzs[0]
        n_atoms = len(xyzs)
        if n_atoms > 3:
            distance_matrix = calc_distance_matrix(xyzs)
            distance_matrix_flat = distance_matrix.reshape(int(n_atoms**2))
            if any([0.1 < dist < 0.7 for dist in distance_matrix_flat]):
                return False
            if all(xyzs[i][3] == 0.0 for i in range(n_atoms)):
                return False

    return True


def extract_xyzs_from_rdkit_mol_object(mol, conf_ids):
    """Generate xyz lists for all the conformers in mol.conf_ids

    Arguments:
        mol (mol obj): Molecule object
        conf_ids (list): list of conformer ids to convert to xyz

    Returns:
        list: list of xyz lists
    """
    xyzs = []

    for i in range(len(conf_ids)):
        mol_block_lines = Chem.MolToMolBlock(mol.mol_obj, confId=conf_ids[i]).split('\n')
        mol_file_xyzs = []

        for line in mol_block_lines:
            split_line = line.split()
            if len(split_line) == 16:
                atom_label, x, y, z = split_line[3], split_line[0], split_line[1], split_line[2]
                mol_file_xyzs.append([atom_label, float(x), float(y), float(z)])

        xyzs.append(mol_file_xyzs)

    if len(xyzs) == 0:
        logger.critical('Length of conformer xyz list was 0')
        exit()

    return xyzs


def generate_unique_rdkit_confs(mol_obj, n_rdkit_confs):
    """Prune the n_rdkit_confs conformers that are generated by the ETKDG algorithm to include only those with RMSD
    larger than 0.5 Å

    Arguments:
        mol_obj (rdkit mol obj): rdkit mol object
        n_rdkit_confs (int): number of rdkit conformers generated

    Returns:
        list: list of conf ids that are unique
    """
    conf_ids = list(AllChem.EmbedMultipleConfs(mol_obj, numConfs=n_rdkit_confs, params=AllChem.ETKDG()))
    unique_conf_ids = [0]

    for i in range(1, len(conf_ids)):
        is_unique = True

        for j in range(len(unique_conf_ids)):
            rmsd = rdMolAlign.AlignMol(mol_obj, mol_obj, prbCid=j, refCid=i)
            if rmsd < 0.5:
                is_unique = False
                break

        if is_unique:
            unique_conf_ids.append(i)

    if len(unique_conf_ids) == 1:
        logger.warning('RDKit only generated a single unique conformer')

    return unique_conf_ids


class Conformer(object):

    def optimise(self, method=None):
        logger.info(f'Running optimisation of {self.name}')

        if method is None:
            method = self.method

        opt = Calculation(name=self.name + '_opt', molecule=self, method=method, keywords=method.conf_opt_keywords,
                          n_cores=Config.n_cores, opt=True, distance_constraints=self.dist_consts,
                          constraints_already_met=True, max_core_mb=Config.max_core)
        opt.run()
        self.energy = opt.get_energy()

        try:
            self.xyzs = opt.get_final_xyzs()
        except XYZsNotFound:
            logger.error(f'xyzs not found for {self.name} but not critical')
            self.xyzs = None

    def __init__(self, name='conf', xyzs=None, energy=None, solvent=None, charge=0, mult=1, dist_consts=None):
        self.name = name
        self.xyzs = xyzs
        self.n_atoms = len(xyzs) if xyzs is not None else None
        self.energy = energy
        self.solvent = solvent
        self.charge = charge
        self.mult = mult
        self.method = get_lmethod()
        self.charges = None
        self.dist_consts = dist_consts
        self.qm_solvent_xyzs = None
