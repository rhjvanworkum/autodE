import numpy as np
from autode.log import logger
from autode.utils import work_in_tmp_dir
from autode.opt.optimisers.base import NDOptimiser
from autode.opt.coordinates import CartesianCoordinates
from autode.opt.optimisers.hessian_update import BFGSPDUpdate, NullUpdate


class RFOptimiser(NDOptimiser):
    """Rational function optimisation in delocalised internal coordinates"""

    def __init__(self, *args, init_alpha: float = 0.1, **kwargs):
        """
        Rational function optimiser (RFO) using a maximum step size of alpha

        -----------------------------------------------------------------------
        Arguments:
            init_alpha: Maximum step size, which controls the maximum component
                        of the step

            args: Additional arguments for ``NDOptimiser``

            kwargs: Additional keywords arguments for ``NDOptimiser``

        See Also:
            :py:meth:`NDOptimiser <autode.opt.optimisers.base.NDOptimiser.__init__>`
        """
        super().__init__(*args, **kwargs)

        self.alpha = init_alpha
        self._hessian_update_types = [BFGSPDUpdate, NullUpdate]

    def _step(self) -> None:
        """RFO step"""
        logger.info("Taking a RFO step")

        self._coords.h_inv = self._updated_h_inv()

        h_n, _ = self._coords.h.shape

        # Form the augmented Hessian, structure from ref [1], eqn. (56)
        aug_H = np.zeros(shape=(h_n + 1, h_n + 1))

        aug_H[:h_n, :h_n] = self._coords.h
        aug_H[-1, :h_n] = self._coords.g
        aug_H[:h_n, -1] = self._coords.g

        aug_H_lmda, aug_H_v = np.linalg.eigh(aug_H)
        # A RF step uses the eigenvector corresponding to the lowest non zero
        # eigenvalue
        mode = np.where(np.abs(aug_H_lmda) > 1e-16)[0][0]
        logger.info(f"Stepping along mode: {mode}")

        # and the step scaled by the final element of the eigenvector
        delta_s = aug_H_v[:-1, mode] / aug_H_v[-1, mode]

        self._take_step_within_trust_radius(delta_s)
        return None

    def _initialise_run(self) -> None:
        """
        Initialise the energy, gradient, and initial Hessian to use
        """

        self._coords = CartesianCoordinates(self._species.coordinates).to(
            "dic"
        )
        self._coords.update_h_from_cart_h(self._low_level_cart_hessian)
        self._coords.make_hessian_positive_definite()
        self._update_gradient_and_energy()

        return None

    @property
    @work_in_tmp_dir(use_ll_tmp=True)
    def _low_level_cart_hessian(self) -> np.ndarray:
        """
        Calculate a Hessian matrix using a low-level method, used as the
        estimate from which BFGS updates are applied. To ensure steps are taken
        in the minimising direction the Hessian MUST be positive definite
        see e.g. (https://manual.q-chem.com/5.2/A1.S2.html). To ensure this
        condition is satisfied
        """
        from autode.methods import get_lmethod

        logger.info("Calculating low-level Hessian")

        species = self._species.copy()
        species.calc_hessian(method=get_lmethod(), n_cores=self._n_cores)

        return species.hessian

    def _take_step_within_trust_radius(
        self, delta_s: np.ndarray, factor: float = 1.0
    ) -> float:
        """
        Update the coordinates while ensuring the step isn't too large in
        cartesian coordinates

        -----------------------------------------------------------------------
        Arguments:
            delta_s: Step in internal coordinates

        Returns:
            factor: The coefficient of the step taken
        """

        if len(delta_s) == 0:  # No need to sanitise a null step
            return 0.0

        new_coords = self._coords + factor * delta_s
        cartesian_delta = new_coords.to("cart") - self._coords.to("cart")
        max_component = np.max(np.abs(cartesian_delta))

        if max_component > self.alpha:
            logger.info(
                f"Calculated step is too large ({max_component:.3f} Å)"
                f" - scaling down"
            )

            # Note because the transformation is not linear this will not
            # generate a step exactly max(∆x) ≡ α, but is empirically close
            factor = self.alpha / max_component
            new_coords = self._coords + self.alpha / max_component * delta_s

        self._coords = new_coords
        return factor
