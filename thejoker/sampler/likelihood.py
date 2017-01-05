# Third-party
from astropy import log as logger
import numpy as np

# Package
from ..celestialmechanics import rv_from_elements
from .utils import get_ivar

__all__ = ['design_matrix', 'tensor_vector_scalar', 'marginal_ln_likelihood']

def design_matrix(nonlinear_p, data, jparams):
    """

    Parameters
    ----------
    nonlinear_p : array_like
        Array of non-linear parameter values. For the default case,
        these are P (period, day), phi0 (phase at pericenter, rad),
        ecc (eccentricity), omega (argument of perihelion, rad).
        May also contain log(jitter^2) as the last index.
    data :
    jparams :

    Returns
    -------
    A : `numpy.ndarray`

    """
    t = data._t_bmjd
    t_offset = data.t_offset
    P, phi0, ecc, omega = nonlinear_p[:4] # we don't need the jitter here

    zdot = rv_from_elements(times=t, P=P, K=1., e=ecc, omega=omega,
                            phi0=phi0-2*np.pi*((t_offset/P) % 1.))

    # TODO: right now, we only support a single, global velocity trend!
    A1 = np.vander(t, N=jparams.trends[0].n_terms, increasing=True)
    A = np.hstack((zdot[:,None], A1)).T

    return A

def tensor_vector_scalar(A, ivar, y):
    """

    Parameters
    ----------
    nonlinear_p : array_like
        Array of non-linear parameter values. For the default case,
        these are P (period, day), phi0 (phase at pericenter, rad),
        ecc (eccentricity), omega (argument of perihelion, rad).
        May also contain log(jitter^2) as the last index.
    data : `thejoker.sampler.RVData`
        Instance of `RVData` containing the data to fit.

    Returns
    -------
    ATCinvA : `numpy.ndarray`
        Value of A^T C^-1 A -- inverse of the covariance matrix
        of the linear parameters.
    p : `numpy.ndarray`
        Optimal values of linear parameters.
    chi2 : float
        Chi-squared value.

    """
    ATCinv = (A.T * ivar[None])
    ATCinvA = ATCinv.dot(A)

    # Note: this is unstable! if cond num is high, could do:
    # p,*_ = np.linalg.lstsq(A, y)
    p = np.linalg.solve(ATCinvA, ATCinv.dot(y))

    dy = A.dot(p) - y
    chi2 = np.sum(dy**2 * ivar) # don't need log term for the jitter b.c. in likelihood below

    return ATCinvA, p, chi2

def marginal_ln_likelihood(nonlinear_p, data):
    """

    Parameters
    ----------
    ATCinvA : array_like
        Should have shape `(N, M, M)` or `(M, M)` where `M`
        is the number of linear parameters in the model.
    chi2 : numeric, array_like
        Chi-squared value(s).

    Returns
    -------
    marg_ln_like : `numpy.ndarray`
        Marginal log-likelihood values.

    """
    A = design_matrix(nonlinear_p, data)

    # TODO: jitter must be in same units as the data RV's / ivar!
    s = nonlinear_p[4]
    ivar = get_ivar(data, s)

    ATCinvA,_,chi2 = tensor_vector_scalar(A, ivar, data.rv.value)

    sign,logdet = np.linalg.slogdet(ATCinvA)
    if not np.all(sign == 1.):
        logger.debug('logdet sign < 0')
        return np.nan

    logdet += np.sum(np.log(ivar/(2*np.pi))) # TODO: this needs a final audit, and is inconsistent with math in the paper

    return 0.5*logdet - 0.5*np.atleast_1d(chi2)