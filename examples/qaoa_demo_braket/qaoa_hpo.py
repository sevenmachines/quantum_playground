#!/usr/bin/python3

# A sample program that runs QAOA using the Amazon Braket SDK

from __future__ import print_function
import os
import json
import pickle
import sys
import traceback
import time
import numpy as np
import pandas as pd
from scipy.optimize import minimize
import pickle
import time

# AWS imports
import boto3
from braket.circuits import Circuit
from braket.aws import AwsQuantumSimulator, AwsSession
from botocore.session import get_session


########################
# CONTAINER PATH SETUP #
########################

# Braket file directory
prefix = '/opt/ml/'

# Data location
input_path = prefix + 'input/data'
param_path = os.path.join(prefix, 'input/config/hyperparameters.json')  # Passed parameters can be retrieved here
output_path = os.path.join(prefix, 'output')  # Failure output & error messages should be written here

# Model Results
model_path = os.path.join(prefix, 'model')  # All results should be written here

# This algorithm has a single channel of input data called 'training'. Since we run in
# File mode, the input files are copied to the directory specified here.
channel_name = 'training'
training_path = os.path.join(input_path, channel_name)  # The problem definition can be found here


# hand built function to implement ZZ gate on qubits q1, q2 with angle gamma
def ZZgate(q1, q2, gamma):
    """
    function that returns a circuit implementing exp(-i \gamma Z_i Z_j)
    """

    # get a circuit
    circ = Circuit()

    # construct diagonal elements (fourth element)
    gate = Circuit().cphaseshift(q1, q2, gamma)
    circ.add(gate)

    # construct third diagonal element
    gate = Circuit().x(q2)
    circ.add(gate)
    gate = Circuit().cphaseshift(q1, q2, -1 * gamma)
    circ.add(gate)
    gate = Circuit().x(q2)
    circ.add(gate)

    # construct second diagonal element
    gate = Circuit().x(q1)
    circ.add(gate)
    gate = Circuit().cphaseshift(q1, q2, -1 * gamma)
    circ.add(gate)
    gate = Circuit().x(q1)
    circ.add(gate)

    # construct first diagonal element
    gate = Circuit().x(q1)
    circ.add(gate)
    gate = Circuit().x(q2)
    circ.add(gate)
    gate = Circuit().cphaseshift(q1, q2, gamma)
    circ.add(gate)
    gate = Circuit().x(q1)
    circ.add(gate)
    gate = Circuit().x(q2)
    circ.add(gate)

    return circ


# function to implement evolution with driver Hamiltonian
def driver(beta):
    """
    Returns circuit for driver Hamiltonian U(Hb, beta)
    """
    # instantiate circuit object
    circ = Circuit()

    for qubit in range(N):
        gate = Circuit().rx(qubit, 2 * beta)
        circ.add(gate)
    return circ


# helper function for evolution with cost Hamiltonian
def cost_circuit(gamma):
    """
    returns circuit for evolution with cost Hamiltonian
    """
    # instantiate circuit object
    circ = Circuit()

    for ii in range(N):
        for jj in range(ii + 1, N):
            # gate = Circuit().zz([ii, jj], 2*gamma*J[ii, jj])
            gate = Circuit().zz(ii, jj, angle=2*gamma*J[ii, jj])
            # gate = ZZgate(ii, jj, gamma * J[ii, jj])
            circ.add(gate)
    return circ


# function to build the QAOA circuit with depth p
def circuit(params):
    """
    function to return full QAOA circuit
    """

    # initialize qaoa circuit with first Hadamard layer: for minimization start in |->
    circ = Circuit()
    X_on_all = Circuit().x(range(0, N))
    circ.add(X_on_all)
    H_on_all = Circuit().h(range(0, N))
    circ.add(H_on_all)

    # setup two parameter families
    circuit_length = int(len(params) / 2)
    gammas = params[:circuit_length]
    betas = params[circuit_length:]

    # add circuit layers
    for mm in range(circuit_length):
        circ.add(cost_circuit(gammas[mm]))
        circ.add(driver(betas[mm]))

    return circ


# function that computes cost function for given params
def objective_function(params):
    """
    objective function takes a list of variational parameters as input,
    and returns the cost associated with those parameters
    """

    print('==================================' * 2)
    global CYCLE
    CYCLE += 1
    print('Calling the quantum circuit. Cycle:', CYCLE)

    # obtain a quantum circuit instance from the parameters
    qaoa_circuit = circuit(params)

    # classically simulate the circuit
    result = device.run(qaoa_circuit, s3_folder, shots=SHOTS).result()

    # convert results (0 and 1) to ising (-1 and 1)
    meas_ising = result.measurements
    meas_ising[meas_ising == 0] = -1

    # get all energies (for every shot): (n_shots, 1) vector
    all_energies = np.diag(np.dot(meas_ising, np.dot(J, np.transpose(meas_ising))))

    # find minimum and corresponding classical string
    energy_min = np.min(all_energies)
    print('Minimal energy:', energy_min)
    optimal_string = meas_ising[np.argmin(all_energies)]
    print('Optimal classical string:', optimal_string)

    # store optimal (classical) result/bitstring
    global ENERGY_OPTIMAL
    global BITSTRING
    if energy_min < ENERGY_OPTIMAL:
        ENERGY_OPTIMAL = energy_min
        BITSTRING = optimal_string

    # energy expectation value
    energy_expect = np.sum(all_energies) / SHOTS
    print('Approx energy expectation value (cost):', energy_expect)
    # send metrics to CloudWatch
    print(f'cost_avg={energy_expect};')

    # NOTE: could consider other definitions of cost function
    cost = energy_expect

    return cost


# The function to execute the training: run classical minimization.
def train(options, p=5):
    """
    function to run QAOA algorithm for given, fixed circuit depth p
    """
    print('Starting the training.')
    try:

        print('==================================' * 3)
        print('OPTIMIZATION for circuit depth p={depth}'.format(depth=p))

        # initialize
        cost_energy = []
        angles = []

        # randomly initialize variational parameters within appropriate bounds
        gamma_initial = np.random.uniform(0, 2 * np.pi, p).tolist()
        beta_initial = np.random.uniform(0, np.pi, p).tolist()
        params0 = np.array(gamma_initial + beta_initial)
        params0[0] = 0.01
        params0[p] = 0.4
        # set bounds for search space
        bnds_gamma = [(0, 2 * np.pi) for _ in range(int(len(params0) / 2))]
        bnds_beta = [(0, np.pi) for _ in range(int(len(params0) / 2))]
        bnds = bnds_gamma + bnds_beta

        # run classical optimization
        result = minimize(objective_function, params0, options=options, method='SLSQP', bounds=bnds)
        # result = minimize(objective_function, params0, options=options, method='Nelder-Mead')

        # store result of classical optimization
        result_energy = result.fun
        cost_energy.append(result_energy)
        print('Optimal avg energy:', result_energy)
        result_angle = result.x
        angles.append(result_angle)
        print('Optimal angles:', result_angle)
        print('Training complete.')

        return result_energy, result_angle

    except Exception as err:
        # Write out an error file. This will be returned as the failureReason in the
        # DescribeTrainingJob result.
        trc = traceback.format_exc()
        with open(os.path.join(output_path, 'failure'), 'w') as s:
            s.write('Exception during training: ' + str(err) + '\n' + trc)
        # Printing this causes the exception to be in the training job logs, as well.
        print('Exception during training: ' + str(err) + '\n' + trc, file=sys.stderr)
        # A non-zero exit code causes the training job to be marked as Failed.
        sys.exit(255)


if __name__ == '__main__':

    # setup credentials and session
    creds = get_session().get_credentials()
    session = boto3.Session(aws_access_key_id=creds.access_key, aws_secret_access_key=creds.secret_key,
                            aws_session_token=creds.token, region_name="us-west-1")
    aws_session = AwsSession(boto_session=session)

    # setup device
    # device_arn = "arn:aws:aqx:::quantum-simulator:aqx:qs1" #Schroedinger
    device_arn = "arn:aws:aqx:::quantum-simulator:aqx:qs3"
    device = AwsQuantumSimulator(device_arn, aws_session)
    # setup s3 folder
    s3_folder = ("hybrid-job-mjas", "simulator-output")

    ##################################################################################
    # Retrieve hyper parameters
    ##################################################################################
    # Parameters that were defined in the hyperparameter dict in the notebook
    # (in our example: qaoa.hyperparam_dict = {'p': p})
    # can be retrieved from the param_path defined above.
    # Note that the parameters are stored as a JSON string, so it is required to
    # define the correct dtype upon reading (here: int).

    with open(param_path, 'r') as tc:
        trainingParams = json.load(tc)
    p = int(trainingParams.get('p', 5))  # circuit depth for QAOA
    print('Circuit depth hyperparameter:', p)

    # SHOTS = int(trainingParams.get('SHOTS', 5))
    SHOTS = 100

    ##################################################################################
    # Load and construct optimization problem
    ##################################################################################
    # You can pass on larger data structures to your program by placing them on S3 and
    # and point to the location at execution time.
    # (in our example: qaoa.fit("s3://qaoa/cluster/input")
    # It can be retrieved from the 'training_path' location defined above.

    # data_s3 = pd.read_csv(open(os.path.join(training_path, 'data_ising.csv')), header=None)
    s3_client = session.client("s3")
    s3_client.download_file('hybrid-job-mjas', 'data/data_ising.csv', 'data_ising.csv')
    data_s3 = pd.read_csv(open('data_ising.csv'), header=None)
    print('Data loaded from S3.')

    # set up the problem
    J = data_s3.values
    N = J.shape[0]
    print('Problem size:', N)
    CYCLE = 0
    # initialize reference solution (simple guess)
    BITSTRING = -1 * np.ones([N])
    ENERGY_OPTIMAL = np.dot(BITSTRING, np.dot(J, BITSTRING))
    # set options for classical optimization
    options = {'disp': True}
    # options = {}

    ##################################################################################
    # run QAOA optimization on graph loaded from S3
    ##################################################################################

    # kick off training
    start = time.time()
    result_energy, result_angle = train(options=options, p=p)
    end = time.time()
    # print execution time
    print('Code execution time [sec]:', end - start)

    # print optimized results
    print('Optimal energy:', ENERGY_OPTIMAL)
    print('Optimal classical bitstring:', BITSTRING)

    ##################################################################################
    # Compute output and dump to pickle
    ##################################################################################
    # Everything written into the 'model_path' location defined above will be
    # returned by Braket to the S3 location defined in the notebook
    # Note that the files will be returned as a tar.gz archive

    out = {'p': p, 'N': N,
           'ENERGY_OPTIMAL': ENERGY_OPTIMAL, 'BITSTRING': BITSTRING,
           'result_energy': result_energy, 'result_angle': result_angle}
    pickle.dump(out, open(os.path.join(model_path, 'out.pckl'), "wb"))

    # A zero exit code causes the job to be marked a Succeeded.
    sys.exit(0)
