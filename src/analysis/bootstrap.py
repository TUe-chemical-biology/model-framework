# -*- coding: utf-8 -*-
"""
Created on Thu Jan  7 14:09:14 2021

@author: Lycolus
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
import random
import statistics
from collections import namedtuple
from src.analysis.helpers import timer
from datetime import datetime

GROUP_TUPLE = namedtuple('group_data', ['concentrations', 'values'])

def _randomise_data(groups, data):
    """
    This private function creates the setup for a new randomised 
    dataset for the bootstrap method, while retaining the original 
    grouping in the data.
    
    All the possible groups are contained in 'groups'
    The data argument is created in 'bootstrap_system_data' and has
    the following format:
    Data is a dictionary, with keys the numbers 0...n, with n the
    number of entries in the system. Each value has the format
    (group, index, value), in context: (condition, concentration, value)
    
    Return format: Dictionary, with keys the groups, values a tuple of two
    lists. The first lists contains all indexes, the second lists contains
    the value for that 'index' at equal index position.
    """
    new_data = {group: GROUP_TUPLE([],[]) for group in groups}
    for i in range(0,len(data)):
        condition, concentration, value = random.choice(data)
        new_data[condition].concentrations.append(concentration)
        new_data[condition].values.append(value)
    return new_data
        
def _bootstrap_system_data(measurement_data):
    """
    This private generator takes a dictionary created by 'bootstrap', which 
    contains all the originial data upon creation, and at every call to the
    generator a new bootstrap dataset is set to the fit_data.
    Because the keys in measurement_data are direct references to the
    conditions, no reference to the system is required.
    
    The bootstrap data is generated by calling _randomise_data.
    """
    i = 0
    combined_data = {}
    groups = []
    # Iterate over all conditions
    for condition, fit_data in measurement_data.items():
        # Keep track of all different conditions seperate
        groups.append(condition)
        
        # Iterate over all the measurements in the condition
        for index, value in fit_data.iteritems():
            # Add each measurement with an unique number
            combined_data[i] = (condition, index, value)
            i += 1
    # Generator setup complete 
    
    while True:
        new_data = _randomise_data(groups, combined_data)
        for condition, data  in new_data.items():
            new_series = pd.Series(data = data.values, 
                                   index = data.concentrations)
            new_series.sort_index(inplace=True)
            condition.fit_data = new_series
        yield

def bootstrap(system, n_repeats, alpha=0.05, bias_acceleration = True):
    """
    Uses a boostrap method to generate confidence intervals for the parameters
    that have been fitted in the last call to system.solve and using the
    current system fit_data.
    
    In order to get accurate confidence intervals, n_repeats of 1000 or
    greater can be taken as a baseline.

    Parameters
    ----------
    system : System object
        The system object to apply bootstrap to.
    n_repeats : int
        The number of bootstrap datasets that need to be generated.
    alpha : float, optional
        Significance level. The default is 0.05.
    bias_acceleration : Boolean
        Wether to calculate the acceleration parameter for bias correction.
        If false, the default value used is zero. The default is True.

    Raises
    ------
    ValueError
        If no solution has been determined before calling this function.

    Returns
    -------
    df : Dataframe
        Dataframe containing the parameters determined for each bootstrap
        run.

    """
    if system.solution is None:
        raise ValueError(
            'System solution is none, please solve the system before running '
            'bootstrap.')
    
    initial_solution = system.solution         
    original_data = {condition: condition.fit_data.copy() 
                     for condition in system}
    
    fit_variables = system.solution.variables
    variable_guess = system.solution.values
    fit_parameters = dict(zip(fit_variables, variable_guess))
    
    results = []
    
    bootstrap_generator = _bootstrap_system_data(original_data)
    # Start bootstrap iterations
    for n in range(0, n_repeats):
        print(f'Starting bootstrap run {n+1} / {n_repeats}')
        next(bootstrap_generator)
        system.solve(fit_parameters, solve_residuals = False)
        results.append(system.solution)
    print()
        
    per_parameter_results = (
        [[result.values[i] for result in results] 
         for i in range(len(fit_variables))])
    df = pd.DataFrame(per_parameter_results).transpose()
    df.columns = fit_variables
    
    # Restore original data and solution
    for condition, data in original_data.items():
        condition.fit_data = data
    system.solution = initial_solution
    system.set_solution_state()
    
    # Bias correction part
    correction = _bias_correction(theta_star = df,
                                  theta = initial_solution.values)
    # Jacknife is expensive for large number of datapoints, determine if
    # it should be calculated.
    if bias_acceleration:
        acceleration = _acceleration_parameter(system, fit_parameters)
    else:
        acceleration = 0
    quantiles = _corrected_quantiles(alpha, correction, acceleration)
    
    # Display the results
    print('--- Bootstrap results ---')
    print(f'Calculated a {(1-alpha)*100}% confidence interval based on ' 
          'bias corrected quantiles.')
    if not bias_acceleration:
        print('Without determining acceleration parameter.')
    print('    Parameter: lower bound - median - upper bound')
    for par, q in zip(df.columns, quantiles):
        lower = df[par].quantile(q[0], interpolation='nearest')
        median = df[par].quantile()
        upper = df[par].quantile(q[1], interpolation='nearest')
        print(f'    {par}: {lower:2E} - {median:2E} - {upper:2E}')
        histogram(df[par], lower, upper)
    print()
    return df    

def _bias_correction(theta_star, theta):
    """
    Determines a bias correction based on a collection of bootstrap determined
    parameters and the parameter from the originial sample.
    Based on 'computational statistics handbook with MATLAB (2002) - chapter 7
    
    Parameters
    ----------
    theta_star : matrix
        The bootstrap determined parameter values, each row represents a
        sample. Each column a parameter.
    theta : array
        The parameter determined for the original dataset, in the same order
        as the theta_star columns.
    """
    # Based on computational statistics handbook with MATLAB (2002)
    n_smaller = np.sum(theta_star < theta, axis=0)
    n_larger = np.sum(theta_star > theta, axis=0)
    fraction_smaller = n_smaller/(n_smaller + n_larger)
    correction = norm.ppf(fraction_smaller)
    return correction

def _corrected_quantiles(alpha, bias_correction, acceleration):
    """
    Determines the adjusted quantiles based on alpha value, bias_correction 
    and acceleration as defined in: 'Computational statistics handbook with 
    MATLAB' (2002) - chapter 7.4
    
    Returns
    -------
    list of tuples or matrix
        When input values are all numbers, returns a list containing a tuple
        where the first value is the lower bound and the second value upper
        bound.
        
        When input is a vector, returns a matrix where each row corresponds
        to a parameter and the first value is the lower bound and the second
        value is the upper bound.
    """
    z0 = bias_correction
    z_lower = norm.ppf(alpha/2)
    z_upper = norm.ppf(1-alpha/2)
    alpha_lower = norm.cdf(z0 + (z0 + z_lower) / 
                               (1 - acceleration * (z0 + z_lower)))
    alpha_upper = norm.cdf(z0 + (z0 + z_upper) / 
                               (1 - acceleration * (z0 + z_upper)))
    
    try:
        return np.stack((alpha_lower, alpha_upper), axis=1)
    except np.AxisError:
        return [(alpha_lower, alpha_upper)]

def _acceleration_parameter(system, fit_parameters):
    """
    Calculates the acceleration of the standard error in order to determine
    the bias corrected confidence intervals of the boostrap function.
    
    Based on:
   'Computational statistics handbook with MATLAB' (2002) - chapter 7.4

    Parameters
    ----------
    system : System object
        The system that has been bootstrapped
    fit_parameters : Dict
        Dictionary with keys the fit_variables and value the guess. Should
        have the found solution as guess in order to speed up the function.

    Returns
    -------
    acceleration : Array
        Acceleration parameter in order of fit_variables.

    """
    print('Calculating acceleration correction using jacknife...')
    n = sum((len(c.fit_data) for c in system))
    i = 0
    generator = _jacknife_generator(system)
    # Calculate all jacknife values:
    jacknife_results = []
    for _ in generator:
        i += 1
        print(f'Jacknife run {i}/{n}.')
        system.solve(fit_parameters, solve_residuals=False, verbose=0)
        jacknife_results.append(system.solution.values)
        
    J = np.array(jacknife_results)
    average = J.mean(axis=0)
    A = average - J
    
    upper = sum(A**3)
    lower = 6 * (sum(A**2)) **(1.5)
    acceleration = upper / lower 
    print()
    
    return acceleration

def _jacknife_generator(system):
    """
    A generator to create jacknife samples of a given system.
    Each next call on the generator removes a single measurement which is
    replaced at the next call. After the last call all values are restored.
    
    If the generator is interupted the fit_data of the system will not be
    restored.

    Parameters
    ----------
    system : System object
        The system object to create jacknife samples for.

    Returns
    -------
    (condition, measurment_index)

    """
    for condition in system:
        original_data = condition.fit_data
        n = len(original_data)
        index = np.arange(n)
        for i in range(n):
            condition.fit_data = original_data[index != i]
            yield (condition, i)
        # Return originial data
        condition.fit_data = original_data
        
def histogram(data, lower=None, upper=None):
    fig, ax, = plt.subplots()
    ax.hist(data, bins=np.geomspace(data.min(), data.max(), 50))
    
    # Add lines to indicate determined interval
    if lower is not None:
        ax.axvline(lower, color='r', linestyle='--')
    if upper is not None:
        ax.axvline(upper, color='r', linestyle='--')
    
    # Change graph looks
    ax.set_xscale('log')
    ax.tick_params(axis='x', labelsize=12)
    ax.tick_params(axis='y', labelsize=12)
    ax.set_xlabel('Parameter value', fontsize=12)
    ax.set_ylabel('Frequency', fontsize=12)
    ax.set_title(f'Bootstrap results: {data.name}', fontsize=12)
    time = datetime.now().strftime("%Y-%m-%d %H%M%S")
    fig.savefig(f'output\{time}-{data.name}-bootstrap-histogram.svg', 
                format='svg', dpi=1200)
    plt.show()
        
            
            
    