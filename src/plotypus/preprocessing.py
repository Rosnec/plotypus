import numpy
from numpy import pi
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from .utils import autocorrelation, rowvec

__all__ = [
    'Fourier'
]


class Fourier():
    def __init__(self, degree=3, degree_range=None,
                 regressor=LinearRegression()):
        self.degree = degree
        self.degree_range = degree_range
        self.regressor = regressor

    def fit(self, X, y=None):
        if self.degree_range is not None:
            self.degree = self.baart_criteria(X, y)
        return self

    def transform(self, X, y=None, **params):
        data = numpy.dstack((numpy.array(X).T[0], range(len(X))))[0]
        phase, order = data[data[:,0].argsort()].T
        coefficients = self.trigonometric_coefficient_matrix(phase,
                                                             self.degree)
        return coefficients[order.argsort()]

    def get_params(self, deep):
        return {'degree': self.degree}

    def set_params(self, **params):
        if 'degree' in params:
            self.degree = params['degree']

    def baart_criteria(self, X, y):
        try:
            min_degree, max_degree = self.degree_range
        except Exception:
            raise Exception("Degree range must be a length two sequence")

        cutoff = self.baart_tolerance(X)
        pipeline = Pipeline([('Fourier', Fourier()),
                             ('Regressor', self.regressor)])
        sorted_X = numpy.sort(X, axis=0)
        X_sorting = numpy.argsort(rowvec(X))
        for degree in range(min_degree, max_degree):
            pipeline.set_params(Fourier__degree=degree)
            pipeline.fit(X, y)
            lc = pipeline.predict(sorted_X)
            residuals = y[X_sorting] - lc
            p_c = autocorrelation(residuals)
            if abs(p_c) <= cutoff:
                return degree
        # reached max_degree without reaching cutoff
        return max_degree

    @staticmethod
    def baart_tolerance(X):
        return (2 * (len(X) - 1))**(-1/2)

    @staticmethod
    def trigonometric_coefficient_matrix(phases, degree):
        """Constructs an Nx2n+1 matrix of the form:
/ 1 sin(1*2*pi*phase[0]) cos(1*2*pi*phase[0]) ... cos(n*2*pi*phase[0]) \
| 1 sin(1*2*pi*phase[1]) cos(1*2*pi*phase[1]) ... cos(n*2*pi*phase[1]) |
| .         .                    .            .             .          |
| .         .                    .             .            .          |
| .         .                    .              .           .          |
\ 1 sin(1*2*pi*phase[N]) cos(1*2*pi*phase[N]) ... cos(n*2*pi*phase[N]) /
        """
        # initialize coefficient matrix
        M = numpy.empty((phases.size, 2*degree+1))
        # indices
        i = numpy.arange(1, degree+1)
        # initialize the Nxn matrix that is repeated within the
        # sine and cosine terms
        x = numpy.empty((phases.size, degree))
        # the Nxn matrix now has N copies of the same row, and each row is
        # integer multiples of pi counting from 1 to the degree
        x[:,:] = i*2*numpy.pi
        # multiply each row of x by the phases
        x.T[:,:] *= phases
        # place 1's in the first column of the coefficient matrix
        M[:,0]    = 1
        # the odd indices of the coefficient matrix have sine terms
        M[:,1::2] = numpy.sin(x)
        # the even indices of the coefficient matrix have cosine terms
        M[:,2::2] = numpy.cos(x)
        return M

    @staticmethod
    def phase_shifted_coefficients(amplitude_coefficients, form='cos',
                                   shift=0.0):
        """Converts Fourier coefficients from the form
        m(t) = A_0 + \Sum_{k=1}^n a_k \sin(k \omega t)
                                + b_k \cos(k \omega t)
        into the form
        m(t) = A_0 + \Sum_{k=1}^n A_k \sin(k \omega t + \Phi_k)
        """
        if 'cos' in form:
            pass  # this will do something once sine series are supported
        elif 'sin' in form:
            raise Exception('Fourier sine series not yet supported')
        else:
            raise Exception('Fourier series must have form sine or cosine')

        # separate array of coefficients into respective parts
        A_0 = amplitude_coefficients[0]
        a_k = amplitude_coefficients[1::2]
        b_k = amplitude_coefficients[2::2]

        degree = a_k.size
        k = numpy.arange(1, degree+1)
        # A_k and Phi_k are the angle and hypotenuse in the right triangle
        # pictured below. A_k is obtained with the Pythagorean theorem, and
        # Phi_k is obtained with the 2-argument inverse tangent.
        #
        #    b_k
        # ---------
        # \ Φ_k |_|
        #  \      |
        #   \     |
        #    \    | a_k
        # A_k \   |
        #      \  |
        #       \ |
        #        \|
        A_k   = numpy.sqrt(a_k**2 + b_k**2)
        # phase coefficients are shifted to the left by optional ``shift``
        Phi_k = numpy.arctan2(-a_k, b_k) - 2*pi*k*shift
        # values should range from 0 to 2*pi, but arctan2 ranges from -pi to pi
        # adding 2*pi to negative values will correct this
        Phi_k %= 2*pi

        phase_shifted_coefficients_ = numpy.empty(amplitude_coefficients.shape,
                                                  dtype=float)
        phase_shifted_coefficients_[0]    = A_0
        phase_shifted_coefficients_[1::2] = A_k
        phase_shifted_coefficients_[2::2] = Phi_k

        return phase_shifted_coefficients_

    @staticmethod
    def fourier_ratios(phase_shifted_coeffs, N):
        """Returns an array containing
        [ R_{N+1 N}, Phi_{N+1 N}, ..., R_{n N}, Phi_{n N} ],
        where R_{i j} is the amplitude ratio R_i / R_j,
        and Phi_{i j} is the phase delta Phi_i - Phi_j.
        """
        n_coeff = phase_shifted_coeffs.size
        # there are 2*order + 1 coefficients: A_0, A_1, Phi_1, A_2, Phi_2, ...
        order = (n_coeff - 1) / 2

        amplitudes = phase_shifted_coeffs[1::2]
        phases = phase_shifted_coeffs[2::2]

        # the number of ratios is 3 less than the number of coefficients
        # because the 0th coefficient is not used, and there are ratios of
        # two
        # TODO: finish writing this comment I apparently forgot about back when
        #       I understood its purpose
        ratios = numpy.empty(phase_shifted_coeffs.size-3, dtype=float)
        amplitude_ratios = ratios[::2]
        phase_deltas = ratios[1::2]

        amplitude_ratios[:] = amplitudes[1:]
        amplitude_ratios   /= amplitudes[0]

        # this isn't quite the right formula!!
        i = numpy.arange(2, order+1)
        phase_deltas[:] = phases[1:]
        phase_deltas   -= i*phases[0]

        return ratios

# @staticmethod
# def amplitude_ratios(amplitudes, N):
#     """Returns an array containing
#     [ R_{i N} for N < i < n ],
#     where n is the degree of the fit.
#     """
#     return amplitudes[N+1:] / amplitudes[N]

# @staticmethod
# def phase_deltas(phase_shifts, N):
#     """Returns an array containing
#     [ Phi_{i N} for N < i < n ],
#     where n is the degree of the fit.
#     """
#     return phase_shifts[N+1:] - phase_shifts[N]
