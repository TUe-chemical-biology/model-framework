# -*- coding: utf-8 -*-
"""
Created on Fri May 21 11:11:58 2021

@author: N.H.J. Geertjens
"""

header = """# Config file for use with the framework for equilibrium models.
# This file was made using the config_generator. 

# This config file is used to set the total concentrations for species other
# than the titrate. Values under the DEFAULT section will be set for all 
# experiments. Values for individual experiments can be set by creating 
# sections with the specific experiment name (header name in the excel file,
# case sensitive).

# Section names are placed in [brackets]
# variables are defines as:
# key = value

# Note that Section names and keys are both case SeNsItIvE.
# Spaces in key names are allowed and will be taken into account.

# Example; to set the variable 'S_tot' for all conditions to 10 uM:
# [DEFAULT]
# S_tot = 10E-6
#

[DEFAULT]


"""