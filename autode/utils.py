import os
from autode.log import logger
from autode.exceptions import NoAtomsInMolecule
from functools import wraps


def work_in(dir_ext):
    """Execute a function in a different directory"""

    def func_decorator(func):

        @wraps(func)
        def wrapped_function(*args, **kwargs):

            here = os.getcwd()
            dir_path = os.path.join(here, dir_ext)

            if not os.path.isdir(dir_path):
                logger.info(
                    f'Creating directory to store output files at {dir_path:}')
                os.mkdir(dir_path)

            os.chdir(dir_path)
            func(*args, **kwargs)
            os.chdir(here)

        return wrapped_function
    return func_decorator


def requires_atoms(func):
    """A function requiring a number of atoms to run"""

    @wraps(func)
    def wrapped_function(species, *args, **kwargs):

        if species.n_atoms == 0:
            raise NoAtomsInMolecule

        func(species, *args, **kwargs)

    return wrapped_function
