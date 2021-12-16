#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Nov 17 10:25:27 2021

@author: goette
"""
import numpy as np 
from misc import  __block, sinecosine_measures, random_fixed_variable_sum_system,random_homogenous_polynomial_sum_system,random_homogenous_polynomial_sum,zeros_homogenous_polynomial_sum_system,monomial_measures,legendre_measures,Gramian, HkinnerLegendre,random_full_system
from helpers import magneticDipolesSamples, selectionMatrix4,selectionMatrix3
from als_l1_test import ALSSystem
block = __block()

import warnings
warnings.filterwarnings("ignore")

order = 20
degree = 2
maxGroupSize = 2
interaction = [4]+ [5] + [6]+[7]*(order-6) +[6]+[5] + [4]
#interaction = [3]+ [4] + [5]*(order-4) +[4] + [3]
trainSampleSize = 10000
maxSweeps=10
ranks = [4]*(order-1)


M = np.ones(order)
I = np.ones(order)
x = np.linspace(0,1*(order-1),order)




train_points,train_values = magneticDipolesSamples(order,trainSampleSize,M,x,I)
train_points = train_points.T
train_values = train_values.T
print(train_points.shape,np.linalg.norm(train_points))
print(train_values.shape,np.linalg.norm(train_values))
#train_measures = legendre_measures(train_points, degree,-np.pi,np.pi)
train_measures = sinecosine_measures(train_points)
print(train_measures.shape)
augmented_train_measures = np.concatenate([train_measures, np.ones((1,trainSampleSize,degree+1))], axis=0)

#bstt = random_homogenous_polynomial_sum_system([degree]*order,interaction,degree,maxGroupSize,selectionMatrix3)
bstt = random_fixed_variable_sum_system([degree]*order,interaction,degree,maxGroupSize,selectionMatrix4)
print(f"DOFS: {bstt.dofs()}")
print(f"Ranks: {bstt.ranks}")
print(f"Interaction: {bstt.interaction}")

   
solver = ALSSystem(bstt, augmented_train_measures,  train_values,_verbosity=1)
solver.maxSweeps = maxSweeps
solver.targetResidual = 1e-6
solver.maxGroupSize=maxGroupSize
solver.run()

testSampleSize = int(2e4)
test_points,test_values = magneticDipolesSamples(order,testSampleSize,M,x,I)
test_points = test_points.T
test_values = test_values.T
#test_measures = legendre_measures(test_points, degree,-np.pi,np.pi)
test_measures = sinecosine_measures(test_points)
augmented_test_measures = np.concatenate([test_measures, np.ones((1,testSampleSize,degree+1))], axis=0)  # measures.shape == (order,N,degree+1)


values = bstt.evaluate(augmented_test_measures)
values2 = bstt.evaluate(augmented_train_measures)
print("L2: ",np.linalg.norm(values -  test_values) / np.linalg.norm(test_values)," on training data: ",np.linalg.norm(values2 -  train_values) / np.linalg.norm(train_values))
