import numpy
from sys import stderr
from math import floor
from os import path
from .utils import make_sure_path_exists, get_signal, get_noise, colvec, mad
from .periodogram import find_period, rephase, get_phase
from .preprocessing import Fourier
from sklearn.cross_validation import cross_val_score
from sklearn.linear_model import LassoCV
from sklearn.pipeline import Pipeline
from sklearn.grid_search import GridSearchCV
import warnings
import matplotlib
matplotlib.use('Agg')
from matplotlib import rcParams
rcParams['axes.labelsize'] = 10
rcParams['xtick.labelsize'] = 10
rcParams['ytick.labelsize'] = 10
rcParams['legend.fontsize'] = 10
rcParams['font.family'] = 'serif'
rcParams['font.serif'] = ['Latin Modern']
rcParams['text.usetex'] = True
rcParams['figure.dpi'] = 300
rcParams['savefig.dpi'] = 300
import matplotlib.pyplot as plt

__all__ = [
    'make_predictor',
    'get_lightcurve',
    'find_outliers',
    'plot_lightcurve'
]

def make_predictor(regressor=LassoCV(cv=10),
                   Predictor=GridSearchCV,
                   fourier_degree=(3,15),
                   use_baart=False,
                   **kwargs):
    if use_baart:
        predictor = Pipeline([('Fourier', Fourier(degree_range=fourier_degree,
                                                  regressor=regressor)),
                              ('Regressor', regressor)])
    else:
        min_degree, max_degree = fourier_degree
        params = {'Fourier__degree':
                  list(range(min_degree, 1+max_degree))}
        pipeline = Pipeline([('Fourier',  Fourier()),
                            ('Regressor', regressor)])
        predictor = Predictor(pipeline, params)

    return predictor

def get_lightcurve(filename, period=None,
                   predictor=make_predictor(),
                   min_period=0.2, max_period=32,
                   coarse_precision=0.001, fine_precision=0.0000001,
                   sigma=10, robust_sigma_clipping=True, min_phase_cover=1/2,
                   phases=numpy.arange(0, 1, 0.01), use_cols=range(3), **ops):
    # Load file
    data = numpy.ma.array(data=numpy.loadtxt(filename, usecols=use_cols),
                          mask=None, dtype=float)

    while True:
        # Find the period of the inliers
        signal = get_signal(data)
        _period = period if period is not None else \
                  find_period(signal.T[0], signal.T[1],
                              min_period, max_period,
                              coarse_precision, fine_precision)
        phase, mag, err = rephase(signal, _period).T

        # Determine whether there is sufficient phase coverage
        coverage = numpy.zeros((100))
        for p in phase:
            coverage[int(floor(p*100))] = 1
        if sum(coverage)/100 < min_phase_cover:
            print(sum(coverage)/100, min_phase_cover,
                  file=stderr)
            print("Insufficient phase coverage",
                  file=stderr)
            return

        # Predict light curve
        with warnings.catch_warnings(record=True) as w:
            try:
                predictor = predictor.fit(colvec(phase), mag)
            except Warning:
                print(w, file=stderr)
                return

        # Reject outliers and repeat the process if there are any
        if sigma:
            outliers = find_outliers(data.data, _period, predictor, sigma,
                                     robust_sigma_clipping)
            num_outliers = sum(outliers)[0]
            if num_outliers == 0 or \
               set.issubset(set(numpy.nonzero(outliers.T[0])[0]),
                            set(numpy.nonzero(data.mask.T[0])[0])):
                data.mask = outliers
                if num_outliers > 0:
                    print("Rejecting", num_outliers, "outliers",
                          file=stderr)
                break
            if num_outliers > 0:
                print("Flagging", sum(outliers)[0], "outliers",
                      file=stderr)
            data.mask = numpy.ma.mask_or(data.mask, outliers)
    
    # Build light curve
    lc = predictor.predict([[i] for i in phases])
    
    # Shift to max light
    arg_max_light = lc.argmin()
    lc = numpy.concatenate((lc[arg_max_light:], lc[:arg_max_light]))

    data.T[0] = numpy.fromiter((get_phase(p, _period,
                                          arg_max_light / phases.size)
                                for p in data.data.T[0]),
                               numpy.float, len(data.data.T[0]))
    best_model = predictor.named_steps['Regressor'] \
                 if isinstance(predictor, Pipeline) \
                 else predictor.best_estimator_.named_steps['Regressor']
    coefficients = best_model.coef_
    coefficients[0] = best_model.intercept_
    R_squared = predictor.best_score_ \
                if hasattr(predictor, 'best_score_') \
                else cross_val_score(predictor, colvec(phase), mag,
                                     scoring='r2').mean()

    return _period, lc, data, coefficients, R_squared

def find_outliers(data, period, predictor, sigma,
                  robust_sigma_clipping=True):
    # determine sigma clipping function
    sigma_clipper = mad if robust_sigma_clipping else numpy.std
    
    phase, mag, err = rephase(data, period).T
    residuals = numpy.absolute(predictor.predict(colvec(phase)) - mag)
    outliers = numpy.logical_and(residuals > err,
                                 residuals > sigma * sigma_clipper(residuals))
    return numpy.tile(numpy.vstack(outliers), data.shape[1])

def plot_lightcurve(filename, lc, period, data, output='.', filetype='.png',
                    legend=False, phases = numpy.arange(0, 1, 0.01), **ops):
    ax = plt.gca()
    ax.grid(True)
    ax.invert_yaxis()
    plt.xlim(0,2)

    # Plot the fitted light curve
    signal, = plt.plot(numpy.hstack((phases,1+phases)),
                       numpy.hstack((lc, lc)),
                       linewidth=1.5, color='green')

    # Plot points used
    phase, mag, err = get_signal(data).T
    inliers = plt.errorbar(numpy.hstack((phase,1+phase)),
                           numpy.hstack((mag, mag)),
                           yerr=numpy.hstack((err,err)),
                           color='black', ls='None',
                           ms=.01, mew=.01, capsize=0)

    # Plot outliers rejected
    phase, mag, err = get_noise(data).T
    outliers = plt.errorbar(numpy.hstack((phase,1+phase)),
                            numpy.hstack((mag, mag)),
                            yerr=numpy.hstack((err,err)),
                            color='r', ls='None',
                            ms=.01, mew=.01, capsize=0)
    
    if legend:
        plt.legend([signal, inliers, outliers],
                   ["Light Curve", "Inliers", "Outliers"],
                   loc='best')
    
    plt.xlabel('Phase ({0:0.7} day period)'.format(period))
    plt.ylabel('Magnitude')
    
    name = filename.split('.')[0]
    plt.title(name)
    plt.tight_layout(pad=0.1)
    make_sure_path_exists(output)
    plt.savefig(path.join(output, name + filetype))
    plt.clf()
