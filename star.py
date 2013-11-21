import os
import numpy
import math
import matplotlib
matplotlib.use("Agg") # Uses Agg backend
import matplotlib.pyplot as plt
import interpolation
from scipy.signal import lombscargle
from math import modf
from re import split
from utils import raw_string, get_noise, get_signal, make_sure_path_exists

class Star:
    __slots__ = ['name', 'period', 'rephased', 'coefficients', 'PCA']
    
    def __init__(self, name, period, rephased, coefficients):
        self.name = name
        self.period = period
        self.rephased = rephased
        self.coefficients = coefficients

def lightcurve(filename, min_obs = 25,
               min_period = 0.2, max_period = 32., period_bins = 50000,
               interpolant = interpolation.trigonometric,
               evaluator = interpolation.trigonometric_evaluator,
               min_degree = 4, max_degree = 15,
               sigma = 1,
               **options):
    """Takes as input the filename for a data file containing the time,
    magnitude, and error for observations of a variable star. Uses a Lomb-
    Scargle periodogram to detect periodicities in the data within the
    specified bounds (discretized by the specified number of period bins).
    Rephases observations based on the star's primary period and normalizes the
    time domain to unit length. Creates a model of the star's light curve using
    the specified interpolant and its corresponding evaluation function.
    Searches for the best order of fit within the specified range
    using the unit-lag auto-correlation subject to Baart's criterion. Rejects
    points with a residual greater than sigma times the standard deviation
    if sigma is positive. Returns a star object containing the name, period,
    preprocessed data, and parameters to the fitted model."""
    name = filename.split(os.sep)[-1]
    data = numpy.ma.masked_array(data=numpy.loadtxt(filename), mask=None)
    while True: # Iteratively process and find models of the data
        if get_signal(data).shape[0] < min_obs:
            print(name + " has too few observations - None")
            return None
        period = find_period(data, min_period, max_period, period_bins)
        if not min_period <= period <= max_period:
            print("period of " + name + " not within range - None")
            return None
        rephased = rephase(data, period)
        coefficients = find_model(get_signal(rephased), min_degree, max_degree,
                                  interpolant, evaluator)
        if sigma:
            prev_mask = data.mask
            outliers = find_outliers(rephased, evaluator, coefficients, sigma)
            data.mask = numpy.ma.mask_or(data.mask, outliers)
            if not numpy.all(data.mask == prev_mask):
                continue
            rephased.mask = data.mask
        return rephased is not None and Star(name, period, rephased,
                                             coefficients)

def find_period(data, min_period, max_period, period_bins):
    """Uses the Lomb-Scargle Periodogram to discover the period."""
    if min_period >= max_period: return min_period
    time, mags = data.T[0:2]
    scaled_mags = (mags-mags.mean())/mags.std()
    minf, maxf = 2*numpy.pi/max_period, 2*numpy.pi/min_period
    freqs = numpy.linspace(minf, maxf, period_bins)
    pgram = lombscargle(time, scaled_mags, freqs)
    return 2*numpy.pi/freqs[numpy.argmax(pgram)]

def rephase(data, period, col=0):
    """Non-destructively rephases all of the values in the given column by the
    given period and scales to be between 0 and 1."""
    rephased = numpy.ma.copy(data)
    rephased.T[col] = [modf(x[col]/period)[0] for x in rephased]
    return rephased

def find_model(signal, min_degree, max_degree, interpolant, evaluator):
    """Iterates through the degree space to find the model that best fits the
    data with the fewest parameters as judged by the unit-lag auto-correlation
    method subject to Baart's criterion."""
    if min_degree >= max_degree: return interpolant(signal, min_degree)
    cutoff = (2 * (signal.shape[0] - 1)) ** (-1/2) # Baart's tolerance
    for degree in range(min_degree, max_degree+1):
        coefficients = interpolant(signal, degree)
        if auto_correlation(signal, evaluator, coefficients) <= cutoff:
            break
    return coefficients

def auto_correlation(signal, evaluator, coefficients):
    """Calculates trends in the residuals between the data and its model."""
    sorted = signal[signal[:,0].argsort()]
    residuals = sorted.T[1] - evaluator(coefficients, sorted.T[0])
    mean = residuals.mean()
    return sum((residuals[i  ] - mean) \
             * (residuals[i+1] - mean) for i in range(sorted.shape[0]-1)) \
         / sum((residuals[i  ] - mean) ** 2
                                       for i in range(sorted.shape[0]-1))

def find_outliers(rephased, evaluator, coefficients, sigma):
    """Finds rephased values that are too far from the light curve."""
    if sigma <= 0: return None
    phases, actual, error = rephased.T
    expected = evaluator(coefficients, phases)
    outliers = (expected - actual)**2 > (sigma * actual.std())**2 + error
    return numpy.tile(numpy.vstack(outliers), rephased.shape[1])

x = numpy.arange(0, 1.00, 0.01)  

def plot_lightcurves(star, evaluator, output, **options):
#    print("raw: {}\n\nPCA: {}".format(star.rephased.T[1],PCA))
    ax = plt.gca()
    ax.grid(True); ax.invert_yaxis()
    if "plot_lightcurves_observed" in options:
        #plt.scatter(star.rephased.T[0], star.rephased.T[1])
        plt.scatter(*star.rephased.T[0:2])
        #plt.errorbar(rephased.T[0], rephased.T[1], rephased.T[2], ls='none')
        outliers = get_noise(star.rephased)
        plt.scatter(outliers.T[0], outliers.T[1], color='r')
    if "plot_lightcurves_interpolated" in options:
        #plt.errorbar(outliers.T[0], outliers.T[1], outliers.T[2], ls='none')
        plt.plot(x, evaluator(star.coefficients, x), linewidth=2.5, color='g')
    if "plot_lightcurves_pca" in options:
        plt.plot(x, star.PCA, linewidth=1.5, color="yellow")
    #plt.errorbar(x, options['evaluator'](x, coefficients), rephased.T[1].std())
    plt.xlabel('Period ({0:0.5} days)'.format(star.period))
#    plt.xlabel('Period (' + str(star.period)[:5] + ' days)')
    plt.ylabel('Magnitude ({0}th order fit)'.format((star.coefficients.shape[0]-1)//2))
    plt.title(star.name)
#    plt.axis([0,1,1,0])
    out = os.path.join(output, split(raw_string(os.sep), star.name)[-1]+'.png')
    make_sure_path_exists(output)
    plt.savefig(out)
    plt.clf()

"""
def plot(star, evaluator, output, **options):
    plt.gca().grid(True)
    plt.scatter(star.T[0], star.T[1])
    out = split(raw_string(os.sep), str(star[0][0]))[-1]+'.png'
    plt.savefig(os.path.join(output, out))
    plt.clf()
"""

def plot_parameter(logP, parameter, parameter_name, output):
    plt.gca().grid(True)
    plt.scatter(logP, parameter)
    plt.xlabel("logP")
    plt.ylabel(parameter_name)
    title = parameter_name + " vs logP"
    plt.title(title)
    out = title + ".png"
    plt.savefig(os.path.join(output, out))
    plt.clf()


def trig_param_plot(stars, output):
    logP = numpy.fromiter((math.log(star.period, 10) for star in stars),
                                    numpy.float)
#    assert False, str([star.coefficients for star in stars])
#    assert False, str(tuple(
#        interpolation.ak_bk2Ak_Phik(star.coefficients).shape for star in stars))

    parameters = numpy.vstack(tuple(
        interpolation.ak_bk2Ak_Phik(star.coefficients) for star in stars))
#    assert False, parameters.shape
    (A0, A1, Phi1, A2, Phi2, A3, Phi3) = numpy.hsplit(parameters[:,:7], 7)
    (R21, R31, R32) = (A2/A1, A3/A1, A3/A2)
    (Phi21, Phi31, Phi32) = (Phi2/Phi1, Phi3/Phi1, Phi3/Phi2)
    plot_parameter(logP, R21,   "R21",   output)
    plot_parameter(logP, R31,   "R31",   output)
    plot_parameter(logP, R32,   "R32",   output)
    plot_parameter(logP, Phi21, "Phi21", output)
    plot_parameter(logP, Phi31, "Phi31", output)
    plot_parameter(logP, Phi32, "Phi32", output)
